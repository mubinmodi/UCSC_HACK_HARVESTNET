"""Move requests over signed A2A: each organization's own host makes its own move (harvestnet_platform.moves).

Test placeholder keys only (test_transport.TEST_KEYS). Every host runs on localhost in a thread.
"""
import threading
import unittest
from http.server import ThreadingHTTPServer
from harvestnet_platform.http import JsonHandler
from harvestnet_platform.moves import A2AMoveProvider
from harvestnet_platform.transport import (MOVE_REPLY, MOVE_REQUEST, ORGANIZATIONS, Receiver, answer, handler_for,
                                           rpc_result)
from harvestnet_platform.transport_auth import Signer, Verifier, pair_key, strip_auth
from test_transport import TEST_KEYS, agent_input, signer, verifier

QUIET = lambda *args, **kwargs: None  # noqa: E731


def core_verifier():
    """The keys each organization derived for the turn publisher, ``core`` (TRANSPORT_VERIFY_KEYS_CORE)."""
    return Verifier('core', {sender: pair_key(key, 'core') for sender, key in TEST_KEYS.items() if sender != 'core'})


def wire(org='city', version=1, facts=None):
    """The core's wire form: ``turn`` as the organization ID, the turn object in ``turn_context``."""
    data = agent_input(org, 1, version, facts)
    return {**data, 'turn': org, 'turn_context': data['turn'], 'policy_session': 'test-session'}


def own_move(org, data):
    return {'organization_id': org, 'version': data['draft']['version'], 'action': 'pass' if org == 'advocate' else 'ask_human',
            'reason': 'Synthetic test move from its own host'}


class Fallback:
    """The core's in-process move, counted."""
    def __init__(self):
        self.calls = []

    def __call__(self, org, data):
        self.calls.append(org)
        return {**own_move(org, data), 'reason': 'In-process fallback test move'}


def serve(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def stop():
        server.shutdown()
        server.server_close()
        thread.join()
    return f'http://127.0.0.1:{server.server_port}', stop


def fake_host(reply_for):
    """A host that answers every request with ``reply_for(signed_request_envelope)``, checking nothing."""
    class Handler(JsonHandler):
        def do_POST(self):
            request = self.read_json()
            data = request['params']['message']['parts'][0]['data']
            self.send_json(200, rpc_result(request, reply_for(data)))
    return Handler


class Hosts:
    """Five real organization hosts, each with its own verifier and its own signing key."""
    def __init__(self, policy=own_move, replace=None):
        self.receivers, self.stops, self.endpoints = {}, [], {}
        for org in ORGANIZATIONS:
            if replace and org in replace:
                handler = replace[org]
            else:
                self.receivers[org] = Receiver(org, policy)
                handler = handler_for(self.receivers[org], verifier(org), 'http://localhost', signer(org))
            self.endpoints[org], stop = serve(handler)
            self.stops.append(stop)

    def close(self):
        for stop in self.stops:
            stop()


def provider(endpoints, fallback, **kwargs):
    return A2AMoveProvider(endpoints, signer(), core_verifier(), fallback, timeout=5, retry_seconds=0, log=QUIET, **kwargs)


class MoveRequestTests(unittest.TestCase):
    def test_each_move_comes_from_its_own_host_signed_by_that_organization(self):
        hosts = Hosts()
        fallback = Fallback()
        try:
            moves = provider(hosts.endpoints, fallback)
            for org in ORGANIZATIONS:
                move = moves(org, wire(org))
                self.assertEqual(move, own_move(org, wire(org)))
                self.assertEqual(moves.pop_metadata(), {'move_source': 'a2a', 'transport': 'a2a_jsonrpc', 'host_policy': 'real_policy_adapter'})
                self.assertIsNone(moves.pop_metadata())  # returned once
            self.assertEqual(fallback.calls, [])
            # Only the organization whose turn it was got the request, as its own event.
            for org, receiver in hosts.receivers.items():
                events = [row[0] for row in receiver.db.execute('SELECT event FROM receipts')]
                self.assertEqual(len(events), 1)
                self.assertTrue(events[0].startswith('move-'))
        finally:
            hosts.close()

    def test_host_answers_only_its_own_move_requests_and_signs_the_reply(self):
        receiver = Receiver('city', own_move)
        request = {'kind': MOVE_REQUEST, 'event_id': 'move-1', 'sequence': 1, 'turn': 'city', 'input': wire('city')}
        reply = answer(receiver, request, signer('city'))
        body = core_verifier().verify(reply)
        self.assertEqual((body['kind'], body['in_reply_to'], body['event_id'], body['turn']), (MOVE_REPLY, 'move-1', 'city:move-1', 'city'))
        self.assertEqual(body['host'], {'organization_id': 'city', 'transport': 'a2a_jsonrpc', 'policy': 'real_policy_adapter', 'policy_metadata': None})
        # An identical retry returns the saved move, signed again (a new nonce the core has not seen).
        again = answer(receiver, request, signer('city'))
        self.assertEqual(strip_auth(again), body)
        self.assertNotEqual(again['auth']['nonce'], reply['auth']['nonce'])
        # Another organization's turn, a later sequence, or no signing key of its own: refused.
        for wrong in ({**request, 'turn': 'rural', 'input': wire('rural')}, {**request, 'event_id': 'move-2', 'sequence': 2}):
            with self.assertRaises(ValueError):
                answer(Receiver('city', own_move), wrong, signer('city'))
        for key in (None, signer('rural')):
            with self.assertRaises(ValueError):
                answer(Receiver('city', own_move), request, key)
        with self.assertRaises(ValueError):
            handler_for(receiver, verifier('city'), 'http://localhost', signer('rural'))

    def test_policy_metadata_travels_with_the_move(self):
        class Reporting:
            def __call__(self, org, data):
                return own_move(org, data)
            def pop_metadata(self):
                return {'source': 'fallback', 'model_calls': 0, 'number_check_failures': 0, 'cost_usd': 0.0,
                        'fallback_reason': 'spending cap', 'prompt': 'never forwarded'}
        hosts = Hosts(policy=Reporting())
        try:
            moves = provider(hosts.endpoints, Fallback())
            moves('rural', wire('rural'))
            self.assertEqual(moves.pop_metadata(), {'move_source': 'a2a', 'transport': 'a2a_jsonrpc', 'host_policy': 'real_policy_adapter',
                                                    'source': 'fallback', 'model_calls': 0, 'number_check_failures': 0,
                                                    'cost_usd': 0.0, 'fallback_reason': 'spending cap'})
        finally:
            hosts.close()

    def refused(self, replace, expected, org='city', endpoints=None):
        """``org``'s move falls back to the core, labeled with a reason containing ``expected``."""
        hosts = Hosts(replace=replace)
        fallback = Fallback()
        try:
            moves = provider(endpoints(hosts.endpoints) if endpoints else hosts.endpoints, fallback)
            move = moves(org, wire(org))
            self.assertEqual(move['reason'], 'In-process fallback test move')
            self.assertEqual(fallback.calls, [org])
            metadata = moves.pop_metadata()
            self.assertEqual(metadata['move_source'], 'in_process_fallback')
            self.assertIn(expected, metadata['reason'])
            return metadata
        finally:
            hosts.close()

    def test_unsigned_reply_is_refused(self):
        def unsigned(request):
            envelope = strip_auth(request)
            return {'kind': MOVE_REPLY, 'event_id': 'city:' + envelope['event_id'], 'sequence': 1, 'turn': 'city',
                    'in_reply_to': envelope['event_id'], 'move': own_move('city', envelope['input']),
                    'host': {'organization_id': 'city', 'transport': 'a2a_jsonrpc'}}
        self.refused({'city': fake_host(unsigned)}, 'not signed')

    def test_forged_reply_is_refused(self):
        def forged(request):
            envelope = strip_auth(request)
            body = {'kind': MOVE_REPLY, 'event_id': 'city:' + envelope['event_id'], 'sequence': 1, 'turn': 'city',
                    'in_reply_to': envelope['event_id'], 'move': own_move('city', envelope['input']),
                    'host': {'organization_id': 'city', 'transport': 'a2a_jsonrpc'}}
            return Signer('city', 'not-city-s-key-but-long-enough-0000000000').sign(body, 'core')
        self.refused({'city': fake_host(forged)}, 'Signature does not match')

    def test_another_organizations_host_cannot_answer_for_it(self):
        # rural's address leads to city's real host: city refuses a request addressed to rural (401).
        self.refused(None, 'HTTP Error 401', org='rural', endpoints=lambda e: {**e, 'rural': e['city']})

        # A host that signs its own (valid) reply to a request meant for another organization.
        def answers_for_rural(request):
            envelope = strip_auth(request)
            body = {'kind': MOVE_REPLY, 'event_id': 'city:' + envelope['event_id'], 'sequence': 1, 'turn': 'city',
                    'in_reply_to': envelope['event_id'], 'move': own_move('city', envelope['input']),
                    'host': {'organization_id': 'city', 'transport': 'a2a_jsonrpc'}}
            return signer('city').sign(body, 'core')
        self.refused({'rural': fake_host(answers_for_rural)}, "signed as 'city', not 'rural'", org='rural')

    def test_a_move_for_another_organization_or_another_request_is_refused(self):
        def body(envelope, **change):
            return {'kind': MOVE_REPLY, 'event_id': 'city:' + envelope['event_id'], 'sequence': 1, 'turn': 'city',
                    'in_reply_to': envelope['event_id'], 'move': own_move('city', envelope['input']),
                    'host': {'organization_id': 'city', 'transport': 'a2a_jsonrpc'}, **change}
        cases = [
            (lambda e: {'move': {**own_move('rural', e['input'])}}, 'must identify its own organization'),
            (lambda e: {'move': {**own_move('city', e['input']), 'version': 7}}, 'current version'),
            (lambda e: {'move': {**own_move('city', e['input']), 'action': 'commit'}}, 'transport cannot commit'),
            (lambda e: {'in_reply_to': 'move-0', 'event_id': 'city:move-0'}, 'does not answer this move request'),
            (lambda e: {'host': {'organization_id': 'rural', 'transport': 'a2a_jsonrpc'}}, "own host"),
        ]
        for change, expected in cases:
            with self.subTest(expected=expected):
                def reply(request, change=change):
                    envelope = strip_auth(request)
                    return signer('city').sign(body(envelope, **change(envelope)), 'core')
                self.refused({'city': fake_host(reply)}, expected)

    def test_replayed_reply_is_refused(self):
        saved = {}
        def replay(request):
            envelope = strip_auth(request)
            if 'reply' not in saved:
                saved['reply'] = signer('city').sign({'kind': MOVE_REPLY, 'event_id': 'city:' + envelope['event_id'], 'sequence': 1,
                                                      'turn': 'city', 'in_reply_to': envelope['event_id'],
                                                      'move': own_move('city', envelope['input']),
                                                      'host': {'organization_id': 'city', 'transport': 'a2a_jsonrpc'}}, 'core')
            return saved['reply']
        hosts = Hosts(replace={'city': fake_host(replay)})
        try:
            moves = provider(hosts.endpoints, Fallback())
            moves('city', wire('city'))
            self.assertEqual(moves.pop_metadata()['move_source'], 'a2a')
            moves('city', wire('city'))  # the same signed reply again
            metadata = moves.pop_metadata()
            self.assertEqual(metadata['move_source'], 'in_process_fallback')
            self.assertIn('Replayed', metadata['reason'])
        finally:
            hosts.close()

    def test_unreachable_host_falls_back_then_waits_before_asking_again(self):
        hosts = Hosts()
        now = [0.0]
        fallback = Fallback()
        try:
            endpoints = {**hosts.endpoints, 'eastside': 'http://127.0.0.1:9'}  # nothing listens there
            moves = A2AMoveProvider(endpoints, signer(), core_verifier(), fallback, timeout=2, retry_seconds=30,
                                    clock=lambda: now[0], log=QUIET)
            moves('eastside', wire('eastside'))
            first = moves.pop_metadata()
            self.assertEqual(first['move_source'], 'in_process_fallback')
            self.assertIn('URLError', first['reason'])
            now[0] = 10
            moves('eastside', wire('eastside'))
            self.assertIn('failed within the last 30s', moves.pop_metadata()['reason'])
            moves('city', wire('city'))  # another organization's host is still asked
            self.assertEqual(moves.pop_metadata()['move_source'], 'a2a')
            now[0] = 31
            moves.endpoints['eastside'] = hosts.endpoints['eastside']  # it is back
            moves('eastside', wire('eastside'))
            self.assertEqual(moves.pop_metadata()['move_source'], 'a2a')
            self.assertEqual(fallback.calls, ['eastside', 'eastside'])
        finally:
            hosts.close()

    def test_host_without_its_own_signing_key_is_a_labeled_fallback(self):
        receiver = Receiver('city', own_move)
        self.refused({'city': handler_for(receiver, verifier('city'), 'http://localhost')}, 'no signing key of its own')

    def test_facts_that_are_not_the_organizations_own_are_never_sent(self):
        hosts = Hosts()
        try:
            moves = provider(hosts.endpoints, Fallback(), facts_problems=lambda org, data: ['given the food bank facts of rural'])
            with self.assertRaises(ValueError):
                moves('city', wire('city'))
            self.assertEqual(list(hosts.receivers['city'].db.execute('SELECT event FROM receipts')), [])
        finally:
            hosts.close()

    def test_provider_requires_every_endpoint_and_the_right_keys(self):
        endpoints = {org: f'http://127.0.0.1:{port}' for port, org in enumerate(ORGANIZATIONS, 9001)}
        A2AMoveProvider(endpoints, signer(), core_verifier(), Fallback(), log=QUIET)
        for bad in ({**endpoints, 'city': ''}, {k: v for k, v in endpoints.items() if k != 'city'}):
            with self.assertRaises(ValueError):
                A2AMoveProvider(bad, signer(), core_verifier(), Fallback(), log=QUIET)
        with self.assertRaises(ValueError):
            A2AMoveProvider(endpoints, signer('city'), core_verifier(), Fallback(), log=QUIET)
        with self.assertRaises(ValueError):
            A2AMoveProvider(endpoints, signer(), verifier('city'), Fallback(), log=QUIET)
        with self.assertRaises(ValueError):
            A2AMoveProvider(endpoints, signer(), core_verifier(), None, log=QUIET)


if __name__ == '__main__':
    unittest.main()
