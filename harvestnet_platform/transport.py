"""Ordered A2A JSON-RPC exchange. Transport carries proposals, never commits."""
import argparse
import copy
import hashlib
import importlib
import json
import math
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from .http import JsonHandler, request_json, seconds, serve
from .transport_auth import TURN_PUBLISHER, AuthError, Signer, Verifier

from .roster import BANKS, ORGANIZATIONS, ROLES  # the one roster; re-exported for callers of this module
ACTIONS = {'accept', 'counter', 'reject', 'request_hold', 'ask_human', 'pass'}
# docs/contracts/agent-moves.md: amendment kinds and their fields, and hold resources.
AMENDMENTS = {'set_pounds': ('produce_id', 'food_bank_id', 'pounds'),
              'shift_pounds': ('produce_id', 'from_food_bank_id', 'to_food_bank_id', 'pounds'),
              'set_transport': ('food_bank_id', 'mover', 'departs_at', 'arrives_at')}
HOLD_RESOURCES = {'lot', 'drop_off', 'storage_cold', 'storage_dry', 'truck'}
# A move request asks one organization, the one whose turn it is, for its own move. Its signed
# reply is a ``move_reply`` from that organization to the turn publisher (``answer``).
MOVE_REQUEST, MOVE_REPLY = 'move_request', 'move_reply'
# What a policy may report about its own move (an LLM policy's source, calls and cost).
POLICY_METADATA = {'source': str, 'model_calls': int, 'number_check_failures': int, 'cost_usd': (int, float),
                   'fallback_reason': (str, type(None))}


def role_of(organization):
    return ROLES[organization]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    """Bare sha256 of canonical JSON, for internal receipt logs."""
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def terms_hash(terms):
    """The contract's terms hash: ``sha256:`` plus the hex digest of canonical JSON."""
    return 'sha256:' + digest(terms)


def _pounds(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_move(move, organization, version):
    if not isinstance(move, dict) or move.get('action') not in ACTIONS:
        raise ValueError('Only agent proposal moves are allowed; transport cannot commit')
    if move.get('organization_id') != organization or type(move.get('version')) is not int or move.get('version') != version:
        raise ValueError('Move must identify its own organization and the current version')
    if not isinstance(move.get('reason'), str) or not move['reason'].strip():
        raise ValueError('Every move must include a reason')
    action = move['action']
    if organization == 'advocate' and action not in ('counter', 'pass'):
        raise ValueError('Advocate proposes but cannot vote or hold others\' resources')
    # A counter carries exactly one amendment; other moves carry none.
    if action == 'counter':
        amendment = move.get('amendment')
        if not isinstance(amendment, dict) or amendment.get('kind') not in AMENDMENTS:
            raise ValueError('A counter requires one structured amendment')
        fields = AMENDMENTS[amendment['kind']]
        if any(amendment.get(key) is None or amendment.get(key) == '' for key in fields):
            raise ValueError(f"A {amendment['kind']} amendment requires {', '.join(fields)}")
        if 'pounds' in fields and not _pounds(amendment['pounds']):
            raise ValueError('Amendment pounds must be a finite, nonnegative number')
    elif 'amendment' in move:
        raise ValueError('Only a counter carries an amendment')
    # A hold request names at least one of its owner's own holds; other moves name none.
    if action == 'request_hold':
        holds = move.get('holds')
        if move.get('resource_owner') != organization:
            raise ValueError('Only the resource owner may request a hold')
        if not isinstance(holds, list) or not holds or any(
                not isinstance(h, dict) or h.get('resource') not in HOLD_RESOURCES or not h.get('start') or not h.get('end')
                or (h.get('pounds') is not None and not _pounds(h['pounds'])) for h in holds):
            raise ValueError('A hold request names at least one hold: resource, pounds or null, start, end')
    elif 'holds' in move or 'resource_owner' in move:
        raise ValueError('Only a hold request carries holds')
    return copy.deepcopy(move)


def turn_organization(agent_input):
    """The organization whose turn it is, from Lane B's AgentInput.

    Lane B's shape has ``turn: {organization_id, number, now, accepted_by}``. Lane A's
    earlier wire form (``turn`` as the ID, plus ``turn_context``) is still accepted.
    """
    if not isinstance(agent_input, dict):
        raise ValueError('Agent input object required')
    turn = agent_input.get('turn')
    if isinstance(turn, dict):
        return turn.get('organization_id')
    return turn


def for_organization(envelope, organization):
    """What one host receives: only the acting organization gets the facts."""
    if envelope['turn'] == organization:
        return envelope
    observed = dict(envelope)
    observed['input'] = {key: value for key, value in envelope['input'].items() if key != 'facts'}
    return observed


def stand_in(organization, agent_input):
    """Transport fixture only: this does not implement Lane B's negotiators."""
    result = {'organization_id': organization, 'version': agent_input['draft']['version'],
              'action': 'ask_human', 'reason': 'Synthetic stand-in requests its own human; no commitment.'}
    if organization == 'advocate':
        result.update(action='pass', reason='Synthetic advocate stand-in takes its turn without a change.')
    return result


def load_policy(spec):
    if not spec:
        return stand_in, 'synthetic_stand_in'
    module, separator, name = spec.partition(':')
    if not separator:
        raise ValueError('Policy must be module:function')
    function = getattr(importlib.import_module(module), name)
    if not callable(function):
        raise ValueError('Policy export is not callable')
    label = 'recorded_rules_stand_in_calculators' if getattr(function, 'uses_stand_in_calculators', False) else 'real_policy_adapter'
    return function, label


def known_policy_metadata(metadata):
    """Only the known fields of a policy's report about its move, each of its expected type."""
    if not isinstance(metadata, dict):
        return None
    return {key: value for key, value in metadata.items()
            if key in POLICY_METADATA and isinstance(value, POLICY_METADATA[key]) and type(value) is not bool}


def policy_metadata(policy):
    """What the policy reports about its last move (``pop_metadata``), limited to known fields."""
    pop = getattr(policy, 'pop_metadata', None)
    return known_policy_metadata(pop() if callable(pop) else None)


class Receiver:
    def __init__(self, organization, policy=stand_in, db_path=':memory:', policy_label=None):
        if organization not in ORGANIZATIONS:
            raise ValueError('Unknown organization')
        self.organization, self.policy = organization, policy
        self.policy_label = policy_label or ('synthetic_stand_in' if policy is stand_in else 'real_policy_adapter')
        self.lock = threading.RLock()
        if db_path != ':memory:':
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS receipts (event TEXT, sequence INTEGER, digest TEXT, result TEXT, PRIMARY KEY(event,sequence))')
        self.db.commit()

    def receive(self, envelope):
        if not isinstance(envelope, dict):
            raise ValueError('An organization event object is required')
        event, seq = envelope.get('event_id'), envelope.get('sequence')
        actor = envelope.get('turn')
        agent_input = envelope.get('input', {})
        if not isinstance(event, str) or not event or len(event) > 100 or type(seq) is not int or seq < 1:
            raise ValueError('Event and positive sequence required')
        kind = envelope.get('kind')
        if kind not in (None, MOVE_REQUEST):
            raise ValueError('Unknown organization message kind')
        if kind == MOVE_REQUEST and (actor != self.organization or seq != 1):
            raise ValueError('A move request goes only to the organization whose turn it is, as its own event')
        if not isinstance(agent_input, dict) or actor not in ORGANIZATIONS or turn_organization(agent_input) != actor:
            raise ValueError('Published turn must identify an organization')
        if 'role' in agent_input and agent_input['role'] != role_of(actor):
            raise ValueError('Agent input role does not match the organization whose turn it is')
        draft = agent_input.get('draft', {})
        if not isinstance(draft, dict) or type(draft.get('version')) is not int or draft['version'] < 1:
            raise ValueError('Current draft version required')
        if actor == self.organization:
            if not isinstance(agent_input.get('facts'), dict):
                raise ValueError('Calculator facts object required')
        elif 'facts' in agent_input:
            # agent-moves.md: facts are this organization's own, and nobody else's.
            raise ValueError("Another organization's facts must not be delivered here")
        received = digest(envelope)
        with self.lock:
            existing = self.db.execute('SELECT digest,result FROM receipts WHERE event=? AND sequence=?', (event,seq)).fetchone()
            if existing:
                if existing[0] != received:
                    raise ValueError('Conflicting replay for an existing sequence')
                return json.loads(existing[1])
            latest = self.db.execute('SELECT COALESCE(MAX(sequence),0) FROM receipts WHERE event=?', (event,)).fetchone()[0]
            if seq != latest + 1:
                raise ValueError('Out-of-order message; retry missing sequence first')
            move = metadata = None
            if actor == self.organization:
                move = validate_move(self.policy(self.organization, copy.deepcopy(agent_input)), self.organization, draft['version'])
                metadata = policy_metadata(self.policy)
            response = {'organization_id': self.organization, 'event_id': event, 'sequence': seq, 'move': move}
            if kind == MOVE_REQUEST:
                response.update(policy=self.policy_label, policy_metadata=metadata)
            self.db.execute('INSERT INTO receipts VALUES (?,?,?,?)', (event,seq,received,canonical(response)))
            self.db.commit()
            return response

    def observed_order(self, event):
        with self.lock:
            return [row[0] for row in self.db.execute('SELECT sequence FROM receipts WHERE event=? ORDER BY sequence', (event,))]


def agent_card(organization, endpoint, capabilities=None):
    tags = ['negotiation', organization]
    if organization in BANKS:
        tags += ['cold_space', 'pickup_hours']
    return {'name': f'HarvestNet {organization}', 'description': 'HarvestNet organization proposals; no external commitment authority',
            'url': endpoint.rstrip('/') + '/', 'version': '1.0.0', 'protocolVersion': '0.3.0',
            'preferredTransport': 'JSONRPC', 'capabilities': {'streaming': False},
            'defaultInputModes': ['application/json'], 'defaultOutputModes': ['application/json'],
            # No shared bearer: each envelope carries its sender's HMAC signature (transport_auth.py).
            'skills': [{'id': 'organization_move', 'name': 'Propose own organization move',
                        'description': 'Respond to versioned calculator facts on a published turn', 'tags': tags}],
            'supportsAuthenticatedExtendedCard': False}


def rpc_request(envelope):
    return {'jsonrpc': '2.0', 'id': str(uuid.uuid4()), 'method': 'message/send',
            'params': {'message': {'kind': 'message', 'role': 'user', 'messageId': str(uuid.uuid4()),
                'parts': [{'kind': 'data', 'data': envelope}]}, 'configuration': {'blocking': True}}}


def rpc_result(request, result):
    return {'jsonrpc': '2.0', 'id': request['id'], 'result': {
        'kind': 'message', 'role': 'agent', 'messageId': str(uuid.uuid4()),
        'parts': [{'kind': 'data', 'data': result}]}}


def answer(receiver, envelope, signer=None, transport='a2a_jsonrpc'):
    """What a host returns for an authenticated envelope.

    A broadcast turn gets the receiver's receipt, as before. A move request gets a reply signed
    with this organization's own key for the turn publisher: its own move, the request it
    answers, and which host and policy produced it. The core checks that signature, so a
    reply from another host, or an unsigned one, is refused."""
    if envelope.get('kind') == MOVE_REQUEST and (not isinstance(signer, Signer) or signer.sender != receiver.organization):
        raise ValueError('This host has no signing key of its own, so it cannot answer a move request')
    result = receiver.receive(envelope)
    if envelope.get('kind') != MOVE_REQUEST:
        return result
    reply = {'kind': MOVE_REPLY, 'event_id': f"{receiver.organization}:{envelope['event_id']}", 'sequence': 1,
             'turn': receiver.organization, 'in_reply_to': envelope['event_id'], 'move': result['move'],
             'host': {'organization_id': receiver.organization, 'transport': transport,
                      'policy': result['policy'], 'policy_metadata': result['policy_metadata']}}
    # A retry returns the saved move, signed again with a new nonce.
    return signer.sign(reply, TURN_PUBLISHER)


def handler_for(receiver, verifier, endpoint, signer=None):
    """The organization host. ``verifier`` checks each envelope's sender signature (transport_auth);
    ``signer``, this organization's own key, signs its replies to move requests."""
    if not isinstance(verifier, Verifier) or verifier.recipient != receiver.organization:
        raise ValueError("A host needs a verifier for its own organization's messages")
    if signer is not None and (not isinstance(signer, Signer) or signer.sender != receiver.organization):
        raise ValueError("A host signs its replies with its own organization's key")

    class Handler(JsonHandler):
        def do_GET(self):
            if self.path in ('/.well-known/agent-card.json', '/.well-known/agent.json'):
                return self.send_json(200, agent_card(receiver.organization, endpoint))
            if self.path == '/health':
                return self.send_json(200, {'status': 'ok', 'organization_id': receiver.organization})
            self.send_json(404, {'error': 'Not found'})

        def do_POST(self):
            if self.path != '/':
                return self.send_json(405, {'error': 'Transport cannot commit organizations'})
            request = {}
            try:
                request = self.read_json()
                if request.get('jsonrpc') != '2.0' or request.get('method') != 'message/send':
                    raise ValueError('Only A2A message/send is supported')
                params = request.get('params')
                if not isinstance(params, dict) or not isinstance(params.get('message'), dict):
                    raise ValueError('A2A message object required')
                message = params['message']
                parts = message.get('parts')
                if message.get('role') != 'user' or not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict) or parts[0].get('kind') != 'data':
                    raise ValueError('One A2A DataPart envelope required')
                try:
                    envelope = verifier.verify(parts[0].get('data'))
                except AuthError as exc:
                    return self.send_json(401, {'error': f'Authenticated organization message required: {exc}'})
                result = answer(receiver, envelope, signer)
                self.send_json(200, rpc_result(request, result))
            except (ValueError, KeyError, TypeError) as exc:
                self.send_json(200, {'jsonrpc': '2.0', 'id': request.get('id'),
                                     'error': {'code': -32602, 'message': str(exc)}})
    return Handler


class InProcess:
    mode = 'in_process_fallback'

    def __init__(self, receivers):
        self.receivers = receivers
        self.lock = threading.RLock()

    def broadcast(self, envelope):
        with self.lock:
            return [self.receivers[org].receive(for_organization(envelope, org)) for org in ORGANIZATIONS]


class A2ATransport:
    mode = 'a2a_jsonrpc'

    def __init__(self, endpoints, signer, timeout=None):
        if set(endpoints) != set(ORGANIZATIONS) or not isinstance(signer, Signer):
            raise ValueError("All organization endpoints and the sender's transport signer required")
        self.endpoints, self.signer = endpoints, signer
        # A live Claude turn can take far longer than a plain HTTP call.
        self.timeout = seconds(os.getenv('AGENT_TURN_TIMEOUT_SECONDS', '60') if timeout is None else timeout)
        self.lock = threading.RLock()

    def broadcast(self, envelope):
        # Caller must not advance until every organization has acknowledged.
        # A partial outage retries the SAME envelope, never switches modes silently.
        with self.lock:
            receipts = []
            for org in ORGANIZATIONS:
                # Signed per recipient: a fresh nonce each time, so a retry is a new message
                # carrying the SAME envelope (the receiver's receipts make it idempotent).
                signed = self.signer.sign(for_organization(envelope, org), org)
                response = request_json(self.endpoints[org].rstrip('/') + '/', rpc_request(signed), timeout=self.timeout)
                if 'error' in response:
                    raise ValueError(response['error']['message'])
                receipt = response['result']['parts'][0]['data']
                if (receipt.get('organization_id'), receipt.get('event_id'), receipt.get('sequence')) != (org, envelope['event_id'], envelope['sequence']):
                    raise ValueError('Mismatched organization receipt')
                receipts.append(receipt)
            return receipts


def host_arguments(description, default_host='127.0.0.1', argv=None):
    """The command line every organization host takes, whichever transport it runs, so a
    deployment can swap the host module and keep its arguments. ``ORGANIZATION_ID`` and
    ``PORT`` stand in for ``--organization`` and ``--port``."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--organization', choices=ORGANIZATIONS, default=os.getenv('ORGANIZATION_ID'),
                        required=not os.getenv('ORGANIZATION_ID'))
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8020')))
    parser.add_argument('--host', default=default_host)
    args = parser.parse_args(argv)
    if args.organization not in ORGANIZATIONS:  # argparse does not check a default against choices
        parser.error(f'unknown organization {args.organization!r}')
    return args


def own_signer(organization):
    """This host's own signing key, for its replies to move requests; ``None`` when unset."""
    if not os.getenv('TRANSPORT_SIGNING_KEY'):
        print('Move requests: refused, no TRANSPORT_SIGNING_KEY for this organization', flush=True)
        return None
    return Signer.from_env(organization)


def start_cooler_watch(organization):
    """A food bank's own agent watches its own cooler and proposes the change (#23), with
    ``COOLER_WATCH=1``. Only the AWS image carries harvestnet_core, so this stays off unless asked for."""
    if os.getenv('COOLER_WATCH') == '1':
        from harvestnet_core.cooler_watch import start_from_env
        start_from_env(organization)


def main():
    args = host_arguments('An organization host: A2A JSON-RPC, per-sender signed')
    policy, label = load_policy(os.getenv('AGENT_POLICY'))
    receipts_db = os.getenv('RECEIPTS_DB', ':memory:')
    receiver = Receiver(args.organization, policy, receipts_db, label)
    # Refuse to start without this host's own verification keys: there is no shared-token fallback.
    verifier = Verifier.from_env(args.organization, receipts_db)
    endpoint = os.getenv('AGENT_PUBLIC_URL', f'http://127.0.0.1:{args.port}')
    print(f'Policy: {label}; transport: A2A JSON-RPC, per-sender signed; approvals disabled', flush=True)
    signer = own_signer(args.organization)
    address = os.getenv('AGNTCY_DIRECTORY_ADDRESS')
    if address:
        # Register this organization's own card and capabilities, and keep them current.
        from .directory import start_publisher
        from .systems import organization_systems
        interval = seconds(os.getenv('DIRECTORY_REFRESH_SECONDS', '30'))
        start_publisher(args.organization, endpoint, address, organization_systems(), interval)
        print(f'Directory: AGNTCY Directory at {address}, refreshed every {interval:g}s', flush=True)
    else:
        print('Directory: none configured; searches use the labeled local registry fallback', flush=True)
    start_cooler_watch(args.organization)
    serve(handler_for(receiver, verifier, endpoint, signer), args.port, args.host)


if __name__ == '__main__':
    main()
