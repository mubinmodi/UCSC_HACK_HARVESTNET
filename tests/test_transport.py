import copy
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from harvestnet_platform.transport import Receiver, InProcess, A2ATransport, ORGANIZATIONS, handler_for, role_of, validate_move
from harvestnet_platform.directory import LocalDirectory, record_info
from harvestnet_platform.systems import Systems
from harvestnet_platform.http import request_json
from harvestnet_platform.transport_auth import SENDERS, Signer, Verifier, pair_key
from urllib.error import HTTPError

# Test placeholders only, never real keys.
TEST_KEYS = {sender: f'test-placeholder-transport-key-{sender}-0000000000' for sender in SENDERS}


def signer(sender='core', clock=None):
    return Signer(sender, TEST_KEYS[sender], **({'clock': clock} if clock else {}))


def verifier(organization, clock=None):
    keys = {sender: pair_key(key, organization) for sender, key in TEST_KEYS.items() if sender != organization}
    return Verifier(organization, keys, **({'clock': clock} if clock else {}))


def agent_input(actor='market', number=1, version=1, facts=None):
    """Lane B's AgentInput shape, unchanged: {role, draft, facts, turn}."""
    return {'role': role_of(actor), 'draft': {'version': version, 'terms': {}},
            'facts': {'own': actor} if facts is None else facts,
            'turn': {'organization_id': actor, 'number': number, 'now': '2026-10-13T12:00:00-07:00', 'accepted_by': []}}


def envelope(seq=1, actor='market', event='transport-fixture'):
    return {'event_id': event, 'sequence': seq, 'turn': actor, 'input': agent_input(actor, seq)}


def serve_hosts(receivers):
    servers, threads, endpoints = [], [], {}
    for org, receiver in receivers.items():
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(receiver, verifier(org), 'http://localhost'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        threads.append(thread)
        endpoints[org] = f'http://127.0.0.1:{server.server_port}'
    def stop():
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()
    return endpoints, stop


class Recording(Receiver):
    def __init__(self, organization, *args, **kwargs):
        super().__init__(organization, *args, **kwargs)
        self.seen = []

    def receive(self, envelope):
        self.seen.append(copy.deepcopy(envelope))
        return super().receive(envelope)


class TransportTests(unittest.TestCase):
    def test_organization_ids_are_names_not_roles(self):
        self.assertEqual(ORGANIZATIONS, ('market', 'city', 'rural', 'eastside', 'advocate'))
        self.assertEqual([role_of(o) for o in ORGANIZATIONS], ['donor', 'food_bank', 'food_bank', 'food_bank', 'advocate'])

    def test_same_order_and_moves_over_real_http_and_in_process(self):
        local = InProcess({org: Receiver(org) for org in ORGANIZATIONS})
        receivers = {org: Receiver(org) for org in ORGANIZATIONS}
        endpoints, stop = serve_hosts(receivers)
        try:
            network = A2ATransport(endpoints, signer())
            for seq, actor in enumerate(ORGANIZATIONS, 1):
                message = envelope(seq, actor)
                expected = local.broadcast(message)
                self.assertEqual(network.broadcast(message), expected)
                self.assertEqual(network.broadcast(message), expected)  # identical retry
            for org in ORGANIZATIONS:
                self.assertEqual(receivers[org].observed_order('transport-fixture'), [1,2,3,4,5])
            with self.assertRaises(HTTPError) as failure:
                request_json(endpoints['city'] + '/commit', {'version': 1})
            self.assertEqual(failure.exception.code, 405)
        finally:
            stop()

    def test_each_host_receives_only_its_own_facts(self):
        receivers = {org: Recording(org) for org in ORGANIZATIONS}
        endpoints, stop = serve_hosts(receivers)
        local = {org: Recording(org) for org in ORGANIZATIONS}
        try:
            network = A2ATransport(endpoints, signer())
            for seq, actor in enumerate(ORGANIZATIONS, 1):
                message = envelope(seq, actor)
                network.broadcast(message)
                InProcess(local).broadcast(message)
            for hosts in (receivers, local):
                for org, receiver in hosts.items():
                    self.assertEqual(len(receiver.seen), 5)
                    for seen in receiver.seen:
                        if seen['turn'] == org:
                            self.assertEqual(seen['input']['facts'], {'own': org})
                        else:
                            self.assertNotIn('facts', seen['input'])
                            self.assertNotIn(seen['turn'], repr(seen['input'].get('facts')))
            # A host that is handed someone else's facts refuses them.
            with self.assertRaises(ValueError):
                Receiver('city').receive(envelope(1, 'market'))
        finally:
            stop()

    def test_lane_b_agent_input_travels_unchanged(self):
        seen = {}
        def policy(org, data):
            seen['input'] = data
            return {'organization_id': org, 'version': 1, 'action': 'pass', 'reason': 'Nothing to change'}
        message = envelope(1, 'advocate')
        receipt = Receiver('advocate', policy).receive(message)
        self.assertEqual(seen['input'], message['input'])
        self.assertEqual(receipt['move']['action'], 'pass')
        # Lane A's earlier wire form (turn string plus turn_context) is still accepted.
        legacy = {**message, 'input': {**message['input'], 'turn': 'advocate', 'turn_context': message['input']['turn']}}
        self.assertEqual(Receiver('advocate', policy).receive(legacy)['move']['action'], 'pass')
        for wrong in ({**message['input'], 'turn': {**message['input']['turn'], 'organization_id': 'city'}},
                      {**message['input'], 'role': 'donor'}):
            with self.assertRaises(ValueError):
                Receiver('advocate', policy).receive({**message, 'input': wrong})

    def test_conflicts_gaps_unauthorized_commit_and_advocate_vote_fail(self):
        receiver = Receiver('market')
        with self.assertRaises(ValueError):
            receiver.receive(envelope(2))
        receiver.receive(envelope())
        changed = envelope()
        changed['input']['draft']['version'] = 2
        with self.assertRaises(ValueError):
            receiver.receive(changed)
        for action, org in [('commit', 'market'), ('accept', 'advocate')]:
            policy = lambda organization, data: {'organization_id': organization, 'version': 1, 'action': action, 'reason': 'Unauthorized'}
            with self.assertRaises(ValueError):
                Receiver(org, policy).receive(envelope(actor=org))

    def test_moves_follow_the_agent_move_contract(self):
        base = {'organization_id': 'city', 'version': 3, 'reason': 'Cold space is short'}
        amendments = [
            {'kind': 'set_pounds', 'produce_id': 'romaine', 'food_bank_id': 'city', 'pounds': 150},
            {'kind': 'shift_pounds', 'produce_id': 'potatoes', 'from_food_bank_id': 'city', 'to_food_bank_id': 'rural', 'pounds': 160},
            {'kind': 'set_transport', 'food_bank_id': 'city', 'mover': 'food_bank',
             'departs_at': '2026-10-13T13:00:00-07:00', 'arrives_at': '2026-10-13T13:20:00-07:00'}]
        for amendment in amendments:
            self.assertEqual(validate_move({**base, 'action': 'counter', 'amendment': amendment}, 'city', 3)['amendment'], amendment)
        hold = {**base, 'action': 'request_hold', 'resource_owner': 'city',
                'holds': [{'resource': 'storage_cold', 'pounds': 150, 'start': '2026-10-13T13:00:00-07:00', 'end': '2026-10-14T21:00:00-07:00'}]}
        self.assertEqual(validate_move(hold, 'city', 3), hold)
        for action in ('accept', 'reject', 'ask_human', 'pass'):
            self.assertEqual(validate_move({**base, 'action': action}, 'city', 3)['action'], action)
        invalid = [
            {**base, 'action': 'counter'},
            {**base, 'action': 'counter', 'amendment': {}},
            {**base, 'action': 'counter', 'amendment': {'kind': 'review_fair_share_gap'}},
            {**base, 'action': 'counter', 'amendment': {'kind': 'set_pounds', 'produce_id': 'romaine', 'food_bank_id': 'city'}},
            {**base, 'action': 'counter', 'amendment': {**amendments[0], 'pounds': -1}},
            {**base, 'action': 'request_hold', 'resource_owner': 'city', 'holds': []},
            {**base, 'action': 'request_hold', 'resource_owner': 'city', 'holds': [{'resource': 'freezer'}]},
            {**base, 'action': 'request_hold', 'resource_owner': 'rural', 'holds': hold['holds']},
            *({**base, 'action': action, 'amendment': amendments[0]} for action in ('accept', 'reject', 'ask_human', 'pass')),
            *({**base, 'action': action, 'holds': hold['holds']} for action in ('accept', 'pass')),
        ]
        for move in invalid:
            with self.subTest(move=move), self.assertRaises(ValueError):
                validate_move(move, 'city', 3)
        advocate = {'organization_id': 'advocate', 'version': 3, 'reason': 'No gap to close'}
        self.assertEqual(validate_move({**advocate, 'action': 'pass'}, 'advocate', 3)['action'], 'pass')
        with self.assertRaises(ValueError):
            validate_move({**advocate, 'action': 'pass', 'amendment': amendments[1]}, 'advocate', 3)

    def test_agent_turn_timeout_is_configurable_and_long_enough_for_claude(self):
        endpoints = {org: f'http://127.0.0.1:{port}' for port, org in enumerate(ORGANIZATIONS, 9001)}
        self.assertEqual(A2ATransport(endpoints, signer()).timeout, 60)
        with patch.dict(os.environ, {'AGENT_TURN_TIMEOUT_SECONDS': '90'}):
            self.assertEqual(A2ATransport(endpoints, signer()).timeout, 90)
        self.assertEqual(A2ATransport(endpoints, signer(), timeout=5).timeout, 5)
        for bad in ('0', 'nan', '-3', 'soon'):
            with patch.dict(os.environ, {'AGENT_TURN_TIMEOUT_SECONDS': bad}), self.assertRaises(ValueError):
                A2ATransport(endpoints, signer())
        calls = []
        def fake(url, body=None, **kwargs):
            calls.append(kwargs['timeout'])
            org = next(o for o, e in endpoints.items() if url == e + '/')
            data = {'organization_id': org, 'event_id': body['params']['message']['parts'][0]['data']['event_id'], 'sequence': 1, 'move': None}
            return {'result': {'parts': [{'data': data}]}}
        with patch('harvestnet_platform.transport.request_json', side_effect=fake):
            A2ATransport(endpoints, signer(), timeout=75).broadcast(envelope(1, 'market'))
        self.assertEqual(calls, [75] * 5)

    def test_discovery_filters_cold_space_hours_and_changed_state(self):
        systems = Systems()
        directory = LocalDirectory(systems, {org: 'http://localhost' for org in ORGANIZATIONS})
        query = dict(min_cold_lb=100, pickup_at='2026-10-13T19:00:00-07:00')
        result = directory.search(**query)
        self.assertEqual(result['mode'], 'local_directory_fallback')
        self.assertEqual([record_info(r)['organization_id'] for r in result['records']], ['city','eastside'])
        systems.switch('city', True)
        self.assertEqual([record_info(r)['organization_id'] for r in directory.search(**query)['records']], ['eastside'])
        equivalent = dict(min_cold_lb=100, pickup_at='2026-10-14T02:00:00Z')
        self.assertEqual(len(directory.search(**equivalent)['records']),1)
        roles = {record_info(r)['organization_id']: record_info(r)['capabilities']['role'] for r in directory.records()}
        self.assertEqual(roles['market'], 'donor')


class ContractExampleTests(unittest.TestCase):
    def test_agreed_agent_move_examples_travel_and_validate_unchanged(self):
        import json
        from pathlib import Path
        pairs = json.loads((Path(__file__).parents[1] / 'docs' / 'contracts' / 'examples' / 'agent-moves.json').read_text())['pairs']
        self.assertEqual(len(pairs), 4)
        for pair in pairs:
            actor = pair['input']['turn']['organization_id']
            with self.subTest(pair=pair.get('name', actor)):
                policy = lambda org, data, out=pair['output']: copy.deepcopy(out)
                message = {'event_id': 'lot-market-1013', 'sequence': 1, 'turn': actor, 'input': pair['input']}
                receipt = Receiver(actor, policy).receive(message)
                self.assertEqual(receipt['move'], pair['output'])


def observed(message):
    """The copy an observer receives: no facts."""
    return {**message, 'input': {k: v for k, v in message['input'].items() if k != 'facts'}}


class TransportAuthenticationTests(unittest.TestCase):
    """Per-sender HMAC signatures: no shared token, no trusted turn field."""

    def test_unsigned_wrong_recipient_tampered_and_forged_messages_get_401(self):
        from harvestnet_platform.transport import rpc_request
        receivers = {org: Receiver(org) for org in ORGANIZATIONS}
        endpoints, stop = serve_hosts(receivers)
        try:
            def post(org, data):
                return request_json(endpoints[org] + '/', rpc_request(data))
            for name, data in (('unsigned', envelope(1, 'market')),
                               ('for rural', signer().sign(envelope(1, 'market'), 'rural')),
                               ('tampered', {**signer().sign(envelope(1, 'market'), 'market'), 'sequence': 2})):
                with self.subTest(name), self.assertRaises(HTTPError) as denied:
                    post('market', data)
                self.assertEqual(denied.exception.code, 401)
            # City holds only keys derived for itself: with them it cannot speak as the core to rural.
            forged = signer()
            forged.key = verifier('city').keys['core'] + 'x'  # the best city can do: reuse what it was given
            with self.assertRaises(HTTPError) as denied:
                post('rural', forged.sign(observed(envelope(1, 'market')), 'rural'))
            self.assertEqual(denied.exception.code, 401)
            self.assertEqual(receivers['rural'].observed_order('transport-fixture'), [])
        finally:
            stop()

    def test_an_organization_may_publish_only_its_own_turn_in_its_own_events(self):
        check = verifier('rural')
        mine = observed(envelope(1, 'city', event='city:offer-1'))
        self.assertEqual(check.verify(signer('city').sign(mine, 'rural')), mine)
        other_turn = {**mine, 'turn': 'market'}
        for name, bad in (('another turn', other_turn), ('not its namespace', {**mine, 'event_id': 'offer-2'})):
            with self.subTest(name), self.assertRaises(ValueError):
                check.verify(signer('city').sign(bad, 'rural'))
        with self.assertRaises(ValueError):  # the publisher cannot use an organization's event names
            check.verify(signer().sign({**mine, 'event_id': 'city:offer-3'}, 'rural'))
        self.assertEqual(check.verify(signer().sign({**mine, 'event_id': 'lot-1'}, 'rural'))['event_id'], 'lot-1')

    def test_stale_and_replayed_messages_are_refused_but_a_resigned_retry_is_idempotent(self):
        now = [1_800_000_000]
        check = verifier('market', clock=lambda: now[0])
        send = signer(clock=lambda: now[0])
        message = send.sign(envelope(), 'market')
        receiver = Receiver('market')
        receipt = receiver.receive(check.verify(message))
        with self.assertRaises(ValueError) as replay:
            check.verify(message)
        self.assertIn('Replayed', str(replay.exception))
        self.assertEqual(receiver.receive(check.verify(send.sign(envelope(), 'market'))), receipt)
        old = send.sign(envelope(2), 'market')
        now[0] += 121
        with self.assertRaises(ValueError) as stale:
            check.verify(old)
        self.assertIn('Stale', str(stale.exception))

    def test_keys_are_per_sender_and_each_host_gets_only_its_own(self):
        import json
        from harvestnet_platform.transport_auth import generate_keys, host_env
        keys = generate_keys()
        self.assertEqual(set(keys), set(SENDERS))
        self.assertEqual(len(set(keys.values())), len(SENDERS))
        env = host_env(keys)
        for host in SENDERS:
            given = json.loads(env[f'TRANSPORT_VERIFY_KEYS_{host.upper()}'])
            self.assertEqual(set(given), set(SENDERS) - {host})
            # A host never receives any sender's own signing key, only keys derived for itself.
            self.assertFalse(set(given.values()) & set(keys.values()))
        with self.assertRaises(ValueError):
            Verifier.from_env('city', environ={})
        with self.assertRaises(ValueError):
            A2ATransport({org: 'http://localhost' for org in ORGANIZATIONS}, 'shared-token')
