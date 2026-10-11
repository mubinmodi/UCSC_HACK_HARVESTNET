"""A hard spending cap for the voice line's Claude extractor (#22).

Lane B's ``ClaudeExtractor`` makes one model call per transcript and returns only the
extracted answers, not the token usage. So each call is charged at its **worst case**,
reserved before the call: every character of the prompt, schema and transcript counted as
an input token, plus the full ``max_tokens`` output, at the highest listed price (a
server-side fallback may answer with another model). Actual spend is at most this. When the
next call's worst case doesn't fit under the cap, no call is made and the API answers 503,
pointing the caller to the text form.
"""
import json
from harvestnet_agents.front_desk import EXTRACTION_PROMPT, EXTRACTION_SCHEMA
from harvestnet_agents.llm_negotiators import SpendingCapReached, PRICES_USD_PER_MTOK, CostEntry, SpendingCap
from .protocol import number

# Message framing and tool overhead, counted generously, in tokens.
OVERHEAD_TOKENS = 2000


class CappedExtractor:
    cost_basis = 'worst case reserved per call; actual usage is not reported by the extractor'

    def __init__(self, extractor, *, limit_usd, allow_paid=False):
        limit_usd = number(limit_usd)
        if limit_usd > 100:
            raise ValueError('cap must be between zero and 100 USD')
        if limit_usd > 0 and not allow_paid:
            raise ValueError('paid calls require explicit authorization')
        self.extractor = extractor
        self.cap = SpendingCap(limit_usd)
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
