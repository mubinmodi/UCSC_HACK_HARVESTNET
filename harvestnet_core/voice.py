"""A hard spending cap for the voice line's Claude extractor (#22).

Lane B's ``ClaudeExtractor`` makes one model call per transcript and returns only the
extracted answers, not the token usage. So each call is charged at its **worst case**,
reserved before the call: every character of the prompt, schema and transcript counted as
an input token, plus the full ``max_tokens`` output, at the highest listed price (a
server-side fallback may answer with another model). Actual spend is at most this. When the
next call's worst case doesn't fit under the cap, no call is made and the API answers 503,
pointing the caller to the text form.

The cap is ``SpendingCap.from_env``: the run cap is the ``limit_usd`` given here (deployed:
``CLAUDE_RUN_CAP_USD``), and the total cap, ``CLAUDE_TOTAL_CAP_USD``, is checked against the persistent
spend ledger (``CLAUDE_SPEND_LEDGER``), so a core restart does not reset what has been spent.
"""
import json
import os
from harvestnet_agents.front_desk import EXTRACTION_PROMPT, EXTRACTION_SCHEMA
from harvestnet_agents.llm_negotiators import SpendingCapReached, PRICES_USD_PER_MTOK, CostEntry, SpendingCap, total_cap_usd_from_env
from .protocol import number

# Message framing and tool overhead, counted generously, in tokens.
OVERHEAD_TOKENS = 2000


class CappedExtractor:
    cost_basis = 'worst case reserved per call; actual usage is not reported by the extractor'

    def __init__(self, extractor, *, limit_usd, allow_paid=False, cap=None):
        limit_usd = number(limit_usd)
        if limit_usd > 100:
            raise ValueError('cap must be between zero and 100 USD')
        if limit_usd > 0 and not allow_paid:
            raise ValueError('paid calls require explicit authorization')
        self.extractor = extractor
        # Tests pass their own cap; deployed, the cap carries the total cap and the ledger from the environment.
        self.cap = cap if cap is not None else SpendingCap.from_env(run_cap_usd=limit_usd, caller='voice_line')
        # An extractor with its own spending cap (Lane B's ClaudeExtractor) shares this one
        # and charges actual usage itself, so this wrapper doesn't charge twice.
        self.shares_cap = hasattr(extractor, 'cap')
        if self.shares_cap:
            extractor.cap = self.cap

    def worst_case_usd(self, transcript):
        chars = len(EXTRACTION_PROMPT) + len(json.dumps(EXTRACTION_SCHEMA)) + len(transcript.render())
        rate = {k: max(p[k] for p in PRICES_USD_PER_MTOK.values()) for k in ('input', 'output')}
        return ((chars + OVERHEAD_TOKENS) * rate['input'] + self.extractor.max_tokens * rate['output']) / 1_000_000

    def __call__(self, transcript):
        if self.shares_cap:
            try:
                return self.extractor(transcript)
            except Exception as exc:
                if isinstance(exc.__cause__, SpendingCapReached):
                    raise exc.__cause__ from None  # report the cap, not a generic voice failure
                raise
        worst = self.worst_case_usd(transcript)
        self.cap.reserve(worst)  # raises SpendingCapReached before any call
        try:
            return self.extractor(transcript)
        finally:
            # Charged whether or not the call succeeded: a failed call may still have cost money.
            self.cap.settle(worst, CostEntry('voice_line', 'front_desk', self.extractor.model, 0, 0, 0, 0, worst, worst))


def extractor_from_env(environ=None, client=None):
    """The deployed voice extractor, or ``None`` (the API then answers 503 "use the text form").

    On only when ``ANTHROPIC_API_KEY`` is set and both ``CLAUDE_RUN_CAP_USD`` and the total cap
    (``CLAUDE_TOTAL_CAP_USD``, default: the run cap) are above zero. The caps are the explicit
    authorization for paid calls: Lane B's ``ClaudeExtractor`` is wrapped in ``CappedExtractor``,
    which holds each call to the run cap (per process) and to the total cap in the persistent
    spend ledger (shared across restarts and callers), and the API's own rate limit applies on
    top. ``client`` is for tests; deployed, the Anthropic SDK reads the key from the
    environment. The key is never printed.
    """
    environ = os.environ if environ is None else environ
    if not (environ.get('ANTHROPIC_API_KEY') or '').strip():
        return None
    try:
        cap = number(float(environ.get('CLAUDE_RUN_CAP_USD') or 0))
        total = total_cap_usd_from_env(environ, default=cap)
    except (TypeError, ValueError):
        print('voice intake: CLAUDE_RUN_CAP_USD or CLAUDE_TOTAL_CAP_USD is not a number; voice extraction stays off', flush=True)
        return None
    if cap <= 0 or total <= 0:
        return None
    if client is None:
        try:
            import anthropic  # noqa: F401 (the agents `claude` extra)
        except ImportError:
            print('voice intake: the anthropic package is not installed; voice extraction stays off', flush=True)
            return None
    from harvestnet_agents.front_desk import ClaudeExtractor
    try:
        spend_cap = SpendingCap.from_env(environ, run_cap_usd=cap, caller='voice_line')
        capped = CappedExtractor(ClaudeExtractor(client=client, cap=spend_cap), limit_usd=cap, allow_paid=True, cap=spend_cap)
    except ValueError as exc:
        print(f'voice intake: {exc}; voice extraction stays off', flush=True)
        return None
    print(f'voice intake: Claude extractor on, spending caps: run ${cap:g} per process, total ${total:g} in the spend ledger', flush=True)
    return capped
