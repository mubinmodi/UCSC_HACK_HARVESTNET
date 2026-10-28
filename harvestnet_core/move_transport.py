"""Where the live core's moves come from: each organization's own host over signed A2A, or in process.

``HARVESTNET_MOVE_TRANSPORT`` chooses, for the server (``harvestnet_core.server``):

- ``in_process`` (the default, and what tests and offline runs use): the core runs each owner's
  rules negotiator itself (``Engine.rules_for``).
- ``a2a``: the core asks the organization whose turn it is for its move, as a signed A2A move
  request to that organization's own host (``harvestnet_platform.moves.A2AMoveProvider``). It needs
  ``AGENT_ENDPOINTS`` (a JSON map of every organization to its host URL), the turn publisher's own
  key ``TRANSPORT_SIGNING_KEY`` (sender ``core``), and ``TRANSPORT_VERIFY_KEYS``, the keys the
  organizations derived for ``core`` (``TRANSPORT_VERIFY_KEYS_CORE``), to check their replies.

A turn the host cannot answer (timeout, unreachable, an error, a refused reply) is made by the same
in-process rules negotiator and recorded as ``move_source: in_process_fallback`` with the reason.
"""
import json
import os

from harvestnet_agents.lane_b_rule_checks import _facts_problems
from harvestnet_agents.negotiation import parse_agent_input

MODES = ('in_process', 'a2a')


def in_process_move(engine):
    """The core's own move for an organization's turn: its rules negotiator, as with no provider."""
    def move(organization, wire):
        role, typed = parse_agent_input({**wire, 'turn': wire['turn_context']})
        return engine.rules_for(role, organization).move(typed).to_dict()
    return move


def own_facts_problems(engine):
    """agent-moves.md: a turn carries only the acting organization's own facts, and no household's
    request code. The same rule the agents' ``no_central_decider`` check applies."""
    def problems(organization, wire):
        codes = [r['request_code'] for r in engine.records.all('request')]
        return _facts_problems(organization, wire['role'], wire['facts'], codes)
    return problems


def provider_from_env(engine, environ=None, log=print):
    """The live server's move provider, or ``None`` for in-process moves."""
    environ = os.environ if environ is None else environ
    mode = environ.get('HARVESTNET_MOVE_TRANSPORT', 'in_process') or 'in_process'
    if mode not in MODES:
        raise ValueError(f'HARVESTNET_MOVE_TRANSPORT must be one of {", ".join(MODES)}')
    if mode == 'in_process':
        log('Moves: in process (each owner\'s rules negotiator runs in the core); HARVESTNET_MOVE_TRANSPORT=a2a asks each host', flush=True)
        return None
    from harvestnet_platform.moves import DEFAULT_RETRY_SECONDS, A2AMoveProvider
    from harvestnet_platform.transport_auth import TURN_PUBLISHER, Signer, Verifier
    try:
        endpoints = json.loads(environ.get('AGENT_ENDPOINTS') or '')
    except ValueError:
        raise ValueError('AGENT_ENDPOINTS must be a JSON map of every organization to its host URL') from None
    if environ.get('TRANSPORT_SENDER', TURN_PUBLISHER) != TURN_PUBLISHER:
        raise ValueError('The core publishes turns as the turn publisher, core')
    provider = A2AMoveProvider(endpoints, Signer.from_env(TURN_PUBLISHER, environ),
                               Verifier.from_env(TURN_PUBLISHER, environ.get('MOVE_REPLIES_DB', ':memory:'), environ),
                               in_process_move(engine),
                               timeout=environ.get('AGENT_TURN_TIMEOUT_SECONDS', '60'),
                               retry_seconds=float(environ.get('MOVE_HOST_RETRY_SECONDS', DEFAULT_RETRY_SECONDS)),
                               facts_problems=own_facts_problems(engine), log=log)
    log(f"Moves: requested over signed A2A from each organization's own host ({', '.join(sorted(endpoints))}); "
        'a turn a host cannot answer is made in process and labeled in_process_fallback', flush=True)
    return provider
