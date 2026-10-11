"""Ordered A2A JSON-RPC exchange. Transport carries proposals, never commits."""
import argparse
import copy
import hashlib
import importlib
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from .http import JsonHandler, request_json, serve

ORGANIZATIONS = ('donor', 'city', 'rural', 'eastside', 'advocate')
ACTIONS = {'accept', 'counter', 'reject', 'request_hold', 'ask_human'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def terms_hash(terms):
    return hashlib.sha256(canonical(terms).encode()).hexdigest()


def validate_move(move, organization, version):
    if not isinstance(move, dict) or move.get('action') not in ACTIONS:
        raise ValueError('Only agent proposal moves are allowed; transport cannot commit')
    if move.get('organization_id') != organization or move.get('version') != version:
        raise ValueError('Move must identify its own organization and the current version')
    if not isinstance(move.get('reason'), str) or not move['reason'].strip():
        raise ValueError('Every move must include a reason')
    if organization == 'advocate' and move['action'] in ('accept', 'reject', 'request_hold'):
        raise ValueError('Advocate proposes but cannot vote or hold others\' resources')
    if move['action'] == 'counter' and not isinstance(move.get('amendment'), dict):
        raise ValueError('A counter requires one structured amendment')
    if move['action'] == 'request_hold' and move.get('resource_owner') != organization:
        raise ValueError('Only the resource owner may request a hold')
    return copy.deepcopy(move)


def stand_in(organization, agent_input):
    """Transport fixture only: this does not implement Lane B's negotiators."""
    result = {'organization_id': organization, 'version': agent_input['draft']['version'],
              'action': 'ask_human', 'reason': 'Synthetic stand-in requests its own human; no commitment.'}
    if organization == 'advocate':
        result.update(action='counter', reason='Synthetic advocate proposes review of the largest fair-share gap.',
                      amendment={'kind': 'review_fair_share_gap'})
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
    return function, 'real_policy_adapter'


class Receiver:
    def __init__(self, organization, policy=stand_in, db_path=':memory:'):
        if organization not in ORGANIZATIONS:
            raise ValueError('Unknown organization')
        self.organization, self.policy = organization, policy
        self.lock = threading.RLock()
        if db_path != ':memory:':
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS receipts (event TEXT, sequence INTEGER, digest TEXT, result TEXT, PRIMARY KEY(event,sequence))')
        self.db.commit()

    def receive(self, envelope):
        event, seq = envelope.get('event_id'), envelope.get('sequence')
        actor = envelope.get('turn')
        agent_input = envelope.get('input', {})
        if not isinstance(event, str) or not event or len(event) > 100 or type(seq) is not int or seq < 1:
            raise ValueError('Event and positive sequence required')
        if actor not in ORGANIZATIONS or agent_input.get('turn') != actor:
            raise ValueError('Published turn must identify an organization')
        draft = agent_input.get('draft', {})
        if type(draft.get('version')) is not int or draft['version'] < 1:
            raise ValueError('Current draft version required')
        if not isinstance(agent_input.get('facts'), dict):
            raise ValueError('Calculator facts object required')
        digest = terms_hash(envelope)
        with self.lock:
            existing = self.db.execute('SELECT digest,result FROM receipts WHERE event=? AND sequence=?', (event,seq)).fetchone()
            if existing:
                if existing[0] != digest:
                    raise ValueError('Conflicting replay for an existing sequence')
                return json.loads(existing[1])
            latest = self.db.execute('SELECT COALESCE(MAX(sequence),0) FROM receipts WHERE event=?', (event,)).fetchone()[0]
            if seq != latest + 1:
                raise ValueError('Out-of-order message; retry missing sequence first')
            move = None
            if actor == self.organization:
                move = validate_move(self.policy(self.organization, copy.deepcopy(agent_input)), self.organization, draft['version'])
            response = {'organization_id': self.organization, 'event_id': event, 'sequence': seq, 'move': move}
            self.db.execute('INSERT INTO receipts VALUES (?,?,?,?)', (event,seq,digest,canonical(response)))
            self.db.commit()
            return response

    def observed_order(self, event):
        with self.lock:
            return [row[0] for row in self.db.execute('SELECT sequence FROM receipts WHERE event=? ORDER BY sequence', (event,))]


def agent_card(organization, endpoint, capabilities=None):
    tags = ['negotiation', organization]
    if organization in ('city', 'rural', 'eastside'):
        tags += ['cold_space', 'pickup_hours']
    return {'name': f'HarvestNet {organization}', 'description': 'HarvestNet organization proposals; no external commitment authority',
            'url': endpoint.rstrip('/') + '/', 'version': '1.0.0', 'protocolVersion': '0.3.0',
            'preferredTransport': 'JSONRPC', 'capabilities': {'streaming': False},
            'defaultInputModes': ['application/json'], 'defaultOutputModes': ['application/json'],
            'securitySchemes': {'bearer': {'type': 'http', 'scheme': 'bearer'}}, 'security': [{'bearer': []}],
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


def handler_for(receiver, token, endpoint):
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
            if not self.authorized(token):
                return self.send_json(401, {'error': 'Authenticated message transport required'})
            request = {}
            try:
                request = self.read_json()
                if request.get('jsonrpc') != '2.0' or request.get('method') != 'message/send':
                    raise ValueError('Only A2A message/send is supported')
                message = request['params']['message']
                parts = message['parts']
                if message.get('role') != 'user' or len(parts) != 1 or parts[0].get('kind') != 'data':
                    raise ValueError('One A2A DataPart envelope required')
                result = receiver.receive(parts[0]['data'])
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
            return [self.receivers[org].receive(envelope) for org in ORGANIZATIONS]


class A2ATransport:
    mode = 'a2a_jsonrpc'

    def __init__(self, endpoints, token):
        if set(endpoints) != set(ORGANIZATIONS) or not token:
            raise ValueError('All organization endpoints and transport token required')
        self.endpoints, self.token = endpoints, token
        self.lock = threading.RLock()

    def broadcast(self, envelope):
        # Caller must not advance until every organization has acknowledged.
        # A partial outage retries the SAME envelope, never switches modes silently.
        with self.lock:
            receipts = []
            for org in ORGANIZATIONS:
                response = request_json(self.endpoints[org].rstrip('/') + '/', rpc_request(envelope), token=self.token)
                if 'error' in response:
                    raise ValueError(response['error']['message'])
                receipt = response['result']['parts'][0]['data']
                if (receipt.get('organization_id'), receipt.get('event_id'), receipt.get('sequence')) != (org, envelope['event_id'], envelope['sequence']):
                    raise ValueError('Mismatched organization receipt')
                receipts.append(receipt)
            return receipts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--organization', choices=ORGANIZATIONS, required=True)
    parser.add_argument('--port', type=int, default=8020)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    policy, label = load_policy(os.getenv('AGENT_POLICY'))
    receiver = Receiver(args.organization, policy, os.getenv('RECEIPTS_DB', ':memory:'))
    endpoint = os.getenv('AGENT_PUBLIC_URL', f'http://127.0.0.1:{args.port}')
    print(f'Policy: {label}; transport: A2A JSON-RPC; approvals disabled', flush=True)
    serve(handler_for(receiver, os.getenv('TRANSPORT_TOKEN'), endpoint), args.port, args.host)


if __name__ == '__main__':
    main()
