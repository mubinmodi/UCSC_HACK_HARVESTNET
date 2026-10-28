"""The turn publisher's side of a move request: ask the organization whose turn it is, over signed A2A.

``A2AMoveProvider(organization, input) -> move`` is the core's move provider (``harvestnet_core.
workflows.negotiate_pending``). For each turn it signs a ``move_request`` as ``core`` for that one
organization, sends it to that organization's own host, and accepts the reply only when:

- it is signed with that organization's own key, for ``core``, fresh and not replayed
  (``transport_auth.Verifier``), so another host, an unsigned receipt or a forged one is refused;
- it answers this request (``in_reply_to``) and names that organization as host and turn;
- its move is one valid proposal of that organization's, on the current version (``validate_move``).

Anything else (a timeout, an unreachable host, an error, a refused reply) uses ``fallback``, the
core's own in-process rules negotiator for that turn, and says so: the metadata ``pop_metadata``
returns is ``move_source: in_process_fallback`` with the reason. It is never silent.
"""
import copy
import http.client
import os
import threading
import time
import uuid
from .http import request_json, seconds
from .transport import (MOVE_REPLY, MOVE_REQUEST, ORGANIZATIONS, calculator_calls, known_policy_metadata,
                        rpc_request, turn_organization, validate_move)
from .transport_auth import TURN_PUBLISHER, AuthError, Signer, Verifier

HOST_TRANSPORTS = ('a2a_jsonrpc', 'agntcy_native')
DEFAULT_RETRY_SECONDS = 30


class MoveRefused(ValueError):
    """A host's reply that the core does not accept as that organization's move."""


def _short(exc):
    text = f'{type(exc).__name__}: {exc}'
    return text if len(text) <= 300 else text[:297] + '...'


class A2AMoveProvider:
    """Each organization's move, requested from its own host over signed A2A, with a labeled fallback.

    ``endpoints`` maps every organization to its host URL. ``signer`` is the turn publisher's own
    key; ``verifier`` holds the keys the organizations derived for ``core``. ``fallback(org, input)``
    is the in-process move for a turn the host could not answer. After a failure, that organization's
    turns use the fallback (each labeled) for ``retry_seconds`` before its host is asked again, so a
    host that hangs does not hold every later turn for the whole timeout. ``facts_problems(org,
    input)`` may refuse to send a turn whose facts are not that organization's own.
    """
    label = "organization negotiators on their own hosts over signed A2A; in-process fallback labeled"

    def __init__(self, endpoints, signer, verifier, fallback, *, timeout=None, retry_seconds=DEFAULT_RETRY_SECONDS,
                 facts_problems=None, clock=time.monotonic, log=print):
        if not isinstance(endpoints, dict) or set(endpoints) != set(ORGANIZATIONS) \
                or not all(isinstance(url, str) and url for url in endpoints.values()):
            raise ValueError('An endpoint for every organization is required')
        if not isinstance(signer, Signer) or signer.sender != TURN_PUBLISHER:
            raise ValueError("Move requests are signed with the turn publisher's own key")
        if not isinstance(verifier, Verifier) or verifier.recipient != TURN_PUBLISHER:
            raise ValueError("Replies are checked with the keys the organizations derived for the turn publisher")
        if not callable(fallback):
            raise ValueError('An in-process fallback move is required')
        self.endpoints, self.signer, self.verifier, self.fallback = dict(endpoints), signer, verifier, fallback
        self.timeout = seconds(os.getenv('AGENT_TURN_TIMEOUT_SECONDS', '60') if timeout is None else timeout)
        self.retry_seconds = float(retry_seconds)
        self.facts_problems, self.clock, self.log = facts_problems, clock, log
        self.down = {}  # organization -> (until, reason)
        self.lock = threading.Lock()
        self.local = threading.local()

    def request(self, organization, agent_input):
        """Ask ``organization``'s host for its move. Returns ``(move, host)`` or raises."""
        version = agent_input['draft']['version']
        event = 'move-' + uuid.uuid4().hex
        envelope = {'kind': MOVE_REQUEST, 'event_id': event, 'sequence': 1, 'turn': organization,
                    'input': copy.deepcopy(agent_input)}
        signed = self.signer.sign(envelope, organization)
        response = request_json(self.endpoints[organization].rstrip('/') + '/', rpc_request(signed), timeout=self.timeout)
        if not isinstance(response, dict):
            raise MoveRefused('The host did not answer with a JSON-RPC object')
        if 'error' in response:
            error = response['error']
            raise MoveRefused(f"The host refused the request: {error.get('message') if isinstance(error, dict) else error}")
        result = response.get('result')
        parts = result.get('parts') if isinstance(result, dict) else None
        if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict) or not isinstance(parts[0].get('data'), dict):
            raise MoveRefused('The reply must be one A2A DataPart')
        reply = parts[0]['data']
        auth = reply.get('auth')
        if not isinstance(auth, dict):
            raise MoveRefused('The reply is not signed')
        if auth.get('sender') != organization:
            raise MoveRefused(f"The reply is signed as {auth.get('sender')!r}, not {organization!r}")
        try:
            body = self.verifier.verify(reply)
        except AuthError as exc:
            raise MoveRefused(f'The reply signature was refused: {exc}') from None
        if body.get('kind') != MOVE_REPLY or body.get('in_reply_to') != event or body.get('event_id') != f'{organization}:{event}' \
                or body.get('turn') != organization or body.get('sequence') != 1:
            raise MoveRefused('The reply does not answer this move request')
        host = body.get('host')
        if not isinstance(host, dict) or host.get('organization_id') != organization or host.get('transport') not in HOST_TRANSPORTS:
            raise MoveRefused("The reply does not come from this organization's own host")
        try:
            move = validate_move(body.get('move'), organization, version)
        except ValueError as exc:
            raise MoveRefused(f"The reply's move was refused: {exc}") from None
        return move, host

    def __call__(self, organization, agent_input):
        if organization not in ORGANIZATIONS or turn_organization(agent_input) != organization:
            raise ValueError('A move request follows the published organization turn')
        if self.facts_problems:
            problems = self.facts_problems(organization, agent_input)
            if problems:
                # The core's own bug, not a transport failure: nothing is sent and nothing falls back.
                raise ValueError(f"Not sent: {organization}'s turn carries facts that are not its own: {problems}")
        version = agent_input['draft']['version']
        with self.lock:
            down = self.down.get(organization)
        if down and self.clock() < down[0]:
            reason = f"{organization}'s host failed within the last {self.retry_seconds:g}s ({down[1]}); asked again after that"
            return self._fall_back(organization, agent_input, reason)
        try:
            move, host = self.request(organization, agent_input)
        except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError) as exc:  # URLError, timeouts, HTTP 401, refused replies
            reason = _short(exc)
            with self.lock:
                self.down[organization] = (self.clock() + self.retry_seconds, reason)
            return self._fall_back(organization, agent_input, reason)
        with self.lock:
            self.down.pop(organization, None)
        metadata = {'move_source': 'a2a', 'transport': host['transport'], 'host_policy': host.get('policy')}
        # The host's own report (a Claude policy's source, calls and cost), known fields only.
        metadata.update(known_policy_metadata(host.get('policy_metadata')) or {})
        # The calculations the host made for its move, named only; the core re-runs them itself.
        calls = calculator_calls(host.get('calculator_calls'))
        if calls:
            metadata['calculator_calls'] = calls
        self.local.metadata = metadata
        self.log(f"move: {organization} {move['action']} on version {version}, from its own host over {host['transport']}", flush=True)
        return move

    def _fall_back(self, organization, agent_input, reason):
        move = validate_move(self.fallback(organization, copy.deepcopy(agent_input)), organization, agent_input['draft']['version'])
        self.local.metadata = {'move_source': 'in_process_fallback', 'reason': reason}
        self.log(f"move: {organization} {move['action']} on version {agent_input['draft']['version']}, "
                 f"IN-PROCESS FALLBACK: {reason}", flush=True)
        return move

    def pop_metadata(self):
        """Where the last move on this thread came from; each call returns it once."""
        metadata = getattr(self.local, 'metadata', None)
        self.local.metadata = None
        return metadata
