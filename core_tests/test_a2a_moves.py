"""The live path over A2A: the core API asks each organization's own host for its move.

Everything runs on localhost in threads: the core's HTTP server and the five organization hosts
(harvestnet_platform.transport), each with its own transport keys (throwaway test keys from
``generate_keys``). A surplus offer is created through the API, as the donor page does.
"""
import copy
import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import platform_source  # noqa: F401  (Lane C on the import path)

from harvestnet_core.api import API
from harvestnet_core.engine import Engine
from harvestnet_core.join_adapter import LLMPolicy, policy
from harvestnet_core.move_transport import provider_from_env
from harvestnet_core.server import make_server
from harvestnet_platform.http import JsonHandler
from harvestnet_platform.transport import MOVE_REPLY, ORGANIZATIONS, Receiver, handler_for, rpc_result
from harvestnet_platform.transport_auth import Signer, Verifier, generate_keys, host_env, pair_key, strip_auth

NOW = '2026-10-13T12:00:00-07:00'
STAFF = {org: f'test-staff-{org}' for org in ORGANIZATIONS}
QUIET = lambda *args, **kwargs: None  # noqa: E731


FIXTURES = sorted(Path('core_fixtures').glob('*.json'))


def scenario(path='core_fixtures/normal-afternoon.json'):
    return json.loads(Path(path).read_text())


def serve(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def stop():
        server.shutdown()
        server.server_close()
        thread.join()
    return f'http://127.0.0.1:{server.server_port}', stop


def http(base, method, path, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.load(response)


def tampering_host(make_reply):
    """A host that answers every move request with ``make_reply(request_envelope)``, unchecked."""
    class Handler(JsonHandler):
        def do_POST(self):
            request = self.read_json()
            self.send_json(200, rpc_result(request, make_reply(strip_auth(request['params']['message']['parts'][0]['data']))))
    return Handler


def reply_body(org, envelope, move):
    return {'kind': MOVE_REPLY, 'event_id': f"{org}:{envelope['event_id']}", 'sequence': 1, 'turn': org,
            'in_reply_to': envelope['event_id'], 'move': move,
            'host': {'organization_id': org, 'transport': 'a2a_jsonrpc', 'policy': 'tampered', 'policy_metadata': None}}


class LiveStack:
    """The core API server and the five organization hosts, on localhost ports."""

    def __init__(self, policies=None, replace=None, fixture=None):
        self.fixture = fixture or scenario()
        self.keys = generate_keys()  # throwaway per-sender transport keys for this test
        self.env = host_env(self.keys)
        self.stops, self.receivers, endpoints = [], {}, {}
        for org in ORGANIZATIONS:
            if replace and org in replace:
                handler = replace[org](self)
            else:
                own = {s: pair_key(k, org) for s, k in self.keys.items() if s != org}
                self.receivers[org] = Receiver(org, (policies or {}).get(org, policy))
                handler = handler_for(self.receivers[org], Verifier(org, own), 'http://localhost', Signer(org, self.keys[org]))
            endpoints[org], stop = serve(handler)
            self.stops.append(stop)
        self.engine = Engine(copy.deepcopy(self.fixture))
        environ = {'HARVESTNET_MOVE_TRANSPORT': 'a2a', 'AGENT_ENDPOINTS': json.dumps(endpoints),
                   'TRANSPORT_SIGNING_KEY': self.env['TRANSPORT_SIGNING_KEY_CORE'],
                   'TRANSPORT_VERIFY_KEYS': self.env['TRANSPORT_VERIFY_KEYS_CORE'],
                   'AGENT_TURN_TIMEOUT_SECONDS': '10', 'MOVE_HOST_RETRY_SECONDS': '0'}
        self.provider = provider_from_env(self.engine, environ, log=QUIET)
        self.api = API(self.engine, clock=lambda: NOW, staff_tokens=STAFF, move_provider=self.provider)
        server = make_server(self.api, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.base = f'http://127.0.0.1:{server.server_port}'
        self.stops.append(lambda: (server.shutdown(), server.server_close(), thread.join()))

    def offer(self, offer=None):
        offer = copy.deepcopy(offer or self.fixture['surplus_offers'][0])
        status, created = http(self.base, 'POST', '/surplus-offers', offer, STAFF[offer['donor_id']])
        assert status == 201, created
        return created['lot_id']

    def events(self, lot_id):
        return self.engine.records.events(lot_id)

    def close(self):
        for stop in self.stops:
            stop()
        for receiver in self.receivers.values():
            receiver.db.close()
        self.provider.verifier.db.close()
        self.engine.records.close()


def in_process_lot():
    """The same offer through the API with no provider: every owner's negotiator runs in the core."""
    engine = Engine(scenario())
    api = API(engine, clock=lambda: NOW, staff_tokens=STAFF)
    status, created = api.call('POST', '/surplus-offers', copy.deepcopy(scenario()['surplus_offers'][0]), token=STAFF['market'])
    assert status == 201, created
    lot = engine.records.get('lot', created['lot_id'])
    moves = [e['data'] for e in engine.records.events(created['lot_id']) if e['kind'] == 'move']
    sources = [e['data']['move_source'] for e in engine.records.events(created['lot_id']) if e['kind'] == 'move_source']
    engine.records.close()
    return lot, moves, sources


def sources_of(events):
    """Each move with the move_source event recorded just before it."""
    pairs, source = [], None
    for e in events:
        if e['kind'] == 'move_source':
            source = e['data']
        elif e['kind'] == 'move':
            pairs.append((e['data'], source))
            source = None
    return pairs


class LiveA2AMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected_lot, cls.expected_moves, cls.expected_sources = in_process_lot()

    def test_every_move_comes_from_its_own_host_over_signed_a2a(self):
        stack = LiveStack()
        try:
            lot_id = stack.offer()
            pairs = sources_of(stack.events(lot_id))
            self.assertTrue(pairs)
            for move, source in pairs:
                self.assertEqual(source['move_source'], 'a2a', (move, source))
                self.assertEqual(source['transport'], 'a2a_jsonrpc')
                self.assertEqual((source['organization_id'], source['version'], source['action']),
                                 (move['organization_id'], move['version'], move['action']))
            provenance = [e['data'] for e in stack.events(lot_id) if e['kind'] == 'policy_provenance']
            self.assertEqual(len(provenance), len(pairs))
            self.assertEqual({(p['move_source'], p['host_policy']) for p in provenance}, {('a2a', 'real_policy_adapter')})
            # Each organization's own host received exactly its own turns, one move request each.
            for org, receiver in stack.receivers.items():
                requests = receiver.db.execute("SELECT COUNT(*) FROM receipts WHERE event LIKE 'move-%'").fetchone()[0]
                self.assertEqual(requests, sum(1 for move, _ in pairs if move['organization_id'] == org), org)
            # Same negotiators, so the same moves and the same lot as the in-process run.
            self.assertEqual([move for move, _ in pairs], self.expected_moves)
            lot = stack.engine.records.get('lot', lot_id)
            self.assertEqual((lot['status'], {**lot['draft'], 'lot_id': None}), (self.expected_lot['status'], {**self.expected_lot['draft'], 'lot_id': None}))
            self.assertEqual(set(self.expected_sources), {'in_process'})
            # The public version list and the food bank's dashboard say which transport made each move.
            status, versions = http(stack.base, 'GET', f'/lots/{lot_id}/versions')
            self.assertEqual(status, 200)
            self.assertEqual({m['move_source'] for m in versions['moves']}, {'a2a'})
            self.assertEqual({v['move_source'] for v in versions['versions'][1:]}, {'a2a'})
            self.assertIsNone(versions['versions'][0]['move_source'])  # the offer is not a move
            status, board = http(stack.base, 'GET', '/food-banks/city/dashboard', token=STAFF['city'])
            offer = next(o for o in board['incoming_offers'] if o['lot_id'] == lot_id)
            self.assertEqual(offer['move_sources'], {'a2a': len(pairs)})
            self.assertEqual(offer['our_fallbacks'], [])
        finally:
            stack.close()

    def check_fallback(self, replace, org, expected_reason):
        stack = LiveStack(replace={org: replace})
        try:
            lot_id = stack.offer()
            pairs = sources_of(stack.events(lot_id))
            for move, source in pairs:
                if move['organization_id'] == org:
                    self.assertEqual(source['move_source'], 'in_process_fallback', move)
                    self.assertIn(expected_reason, source['reason'])
                else:
                    self.assertEqual(source['move_source'], 'a2a', move)
            # The fallback is the same rules negotiator, so the outcome does not change; it is only labeled.
            self.assertEqual([move for move, _ in pairs], self.expected_moves)
            provenance = [e['data'] for e in stack.events(lot_id) if e['kind'] == 'policy_provenance' and e['data']['organization_id'] == org]
            self.assertTrue(provenance)
            self.assertTrue(all(p['move_source'] == 'in_process_fallback' and expected_reason in p['reason'] for p in provenance))
            if org != 'market' and org != 'advocate':
                status, board = http(stack.base, 'GET', f'/food-banks/{org}/dashboard', token=STAFF[org])
                offer = next(o for o in board['incoming_offers'] if o['lot_id'] == lot_id)
                self.assertGreater(offer['move_sources']['in_process_fallback'], 0)
                self.assertTrue(offer['our_fallbacks'])
                self.assertTrue(all(expected_reason in f['reason'] for f in offer['our_fallbacks']))
            status, versions = http(stack.base, 'GET', f'/lots/{lot_id}/versions')
            self.assertTrue(all('reason' not in m for m in versions['moves']))  # the error text stays off the public list
        finally:
            stack.close()

    def test_forged_reply_is_refused_and_falls_back_labeled(self):
        def forged(stack):
            # city's reply, signed with a key that is not city's.
            return tampering_host(lambda env: Signer('city', 'forged-key-that-is-not-city-s-own-0000000').sign(
                reply_body('city', env, {'organization_id': 'city', 'version': env['input']['draft']['version'],
                                         'action': 'accept', 'reason': 'Forged accept'}), 'core'))
        self.check_fallback(forged, 'city', 'Signature does not match')

    def test_unsigned_reply_is_refused_and_falls_back_labeled(self):
        def unsigned(stack):
            return tampering_host(lambda env: reply_body('eastside', env, {'organization_id': 'eastside', 'version': env['input']['draft']['version'],
                                                                           'action': 'pass', 'reason': 'Unsigned pass'}))
        self.check_fallback(unsigned, 'eastside', 'not signed')

    def test_an_organization_answering_for_another_is_refused(self):
        def city_answers_for_rural(stack):
            # rural's address leads to a host holding city's own key: it signs a genuine city reply.
            return tampering_host(lambda env: Signer('city', stack.keys['city']).sign(
                reply_body('city', env, {'organization_id': 'city', 'version': env['input']['draft']['version'],
                                         'action': 'accept', 'reason': 'City speaking for rural'}), 'core'))
        self.check_fallback(city_answers_for_rural, 'rural', "signed as 'city', not 'rural'")

        def rural_moves_for_city(stack):
            # rural's own key, signed as rural, but the move is city's.
            return tampering_host(lambda env: Signer('rural', stack.keys['rural']).sign(
                reply_body('rural', env, {'organization_id': 'city', 'version': env['input']['draft']['version'],
                                          'action': 'accept', 'reason': 'Rural voting for city'}), 'core'))
        self.check_fallback(rural_moves_for_city, 'rural', 'must identify its own organization')

    def test_a_hosts_own_claude_policy_reports_its_source_with_each_move(self):
        from harvestnet_agents.llm_negotiators import SpendingCap
        # A zero cap: the host's Claude negotiator makes no model call and uses its rules move, labeled.
        stack = LiveStack(policies={'city': LLMPolicy(cap=SpendingCap(0))})
        try:
            lot_id = stack.offer()
            city = [e['data'] for e in stack.events(lot_id) if e['kind'] == 'policy_provenance' and e['data']['organization_id'] == 'city']
            self.assertTrue(city)
            for p in city:
                self.assertEqual((p['move_source'], p['source'], p['model_calls'], p['cost_usd']), ('a2a', 'fallback', 0, 0))
                self.assertIn('spending cap', p['fallback_reason'])
            self.assertEqual([move for move, _ in sources_of(stack.events(lot_id))], self.expected_moves)
        finally:
            stack.close()


class EveryFixtureTests(unittest.TestCase):
    """The five core fixtures, every offer: the same moves, numbers and evaluation either way."""

    def test_every_offer_gets_the_same_moves_over_a2a_as_in_process(self):
        for path in FIXTURES:
            with self.subTest(fixture=path.name):
                f = scenario(path)
                stack = LiveStack(fixture=f)
                engine = Engine(copy.deepcopy(f))
                api = API(engine, clock=lambda: NOW, staff_tokens=STAFF)
                try:
                    for offer in f['surplus_offers']:
                        if offer.get('recall_notice'):
                            continue
                        lot_id = stack.offer(offer)
                        status, created = api.call('POST', '/surplus-offers', copy.deepcopy(offer), token=STAFF[offer['donor_id']])
                        pairs = sources_of(stack.events(lot_id))
                        self.assertEqual([m for m, _ in pairs], [m for m, _ in sources_of(engine.records.events(created['lot_id']))])
                        self.assertEqual({s['move_source'] for _, s in pairs}, {'a2a'})
                        # The hosts' calculations are re-run by the core, so no reason fails the number check.
                        self.assertEqual(stack.engine.records.get('lot', lot_id).get('number_check_failures', 0),
                                         engine.records.get('lot', created['lot_id']).get('number_check_failures', 0))
                finally:
                    stack.close()
                    engine.records.close()

    def test_evaluation_numbers_are_the_same_with_moves_from_the_hosts(self):
        from harvestnet_core.engine import run_fixture
        from harvestnet_core.evaluation import metrics
        from harvestnet_core.records import Records
        stack = LiveStack()  # its five hosts; the harness runs without the API
        try:
            for path in FIXTURES:
                with self.subTest(fixture=path.name):
                    f = scenario(path)
                    results = []
                    for provider in (None, stack.provider):
                        records = Records()
                        run = run_fixture(copy.deepcopy(f), provider, records=records)
                        results.append(metrics(f, run, records))
                        records.close()
                    self.assertEqual(results[0], results[1])
        finally:
            stack.close()


class ReplayCalculationsTests(unittest.TestCase):
    def test_only_calculations_from_known_numbers_reach_the_number_check(self):
        from harvestnet_agents.llm_negotiators import NumberPool
        from harvestnet_agents.negotiation import parse_agent_input
        from harvestnet_core.workflows import replay_calculations
        engine = Engine(scenario())
        try:
            draft = engine.create_offer(copy.deepcopy(scenario()['surplus_offers'][0]))
            raw = {'role': 'food_bank', 'draft': draft, 'facts': engine.facts('city', draft),
                   'turn': {'organization_id': 'city', 'number': 2, 'now': NOW, 'accepted_by': []}}
            _role, typed = parse_agent_input(raw)
            pool = NumberPool()
            pool.add(typed)
            gap = raw['facts']['demand']['below_fair_share_lb']
            self.assertFalse(pool.has_number(987.0))
            replay_calculations(engine, typed, pool, [
                {'name': 'adjust_pounds', 'args': {'current_lb': 0.0, 'change_lb': 987.0}},  # 987 is in nothing it was given
                {'name': 'gap_after_plan', 'args': {'gap_lb': gap, 'planned_lb': draft['items'][0]['pounds']}},
                {'name': 'no_such_calculator', 'args': {}},
            ])
            self.assertFalse(pool.has_number(987.0))  # a manufactured number never becomes a calculator result
            self.assertEqual(engine.calc.calls[-1].name, 'gap_after_plan')  # the core's own calculator ran it
        finally:
            engine.records.close()


class MoveTransportConfigTests(unittest.TestCase):
    def test_in_process_is_the_default_and_a2a_needs_endpoints_and_keys(self):
        engine = Engine(scenario())
        try:
            self.assertIsNone(provider_from_env(engine, {}, log=QUIET))
            self.assertIsNone(provider_from_env(engine, {'HARVESTNET_MOVE_TRANSPORT': 'in_process'}, log=QUIET))
            with self.assertRaises(ValueError):
                provider_from_env(engine, {'HARVESTNET_MOVE_TRANSPORT': 'carrier_pigeon'}, log=QUIET)
            env = host_env(generate_keys())
            endpoints = json.dumps({org: f'http://127.0.0.1:{port}' for port, org in enumerate(ORGANIZATIONS, 9001)})
            good = {'HARVESTNET_MOVE_TRANSPORT': 'a2a', 'AGENT_ENDPOINTS': endpoints,
                    'TRANSPORT_SIGNING_KEY': env['TRANSPORT_SIGNING_KEY_CORE'], 'TRANSPORT_VERIFY_KEYS': env['TRANSPORT_VERIFY_KEYS_CORE']}
            self.assertIsNotNone(provider_from_env(engine, good, log=QUIET))
            for missing in ('AGENT_ENDPOINTS', 'TRANSPORT_SIGNING_KEY', 'TRANSPORT_VERIFY_KEYS'):
                with self.subTest(missing=missing), self.assertRaises(ValueError):
                    provider_from_env(engine, {k: v for k, v in good.items() if k != missing}, log=QUIET)
            with self.assertRaises(ValueError):
                provider_from_env(engine, {**good, 'TRANSPORT_SENDER': 'city'}, log=QUIET)
        finally:
            engine.records.close()

    def test_a_turn_with_another_organizations_facts_is_never_sent(self):
        engine = Engine(scenario())
        try:
            env = host_env(generate_keys())
            endpoints = json.dumps({org: f'http://127.0.0.1:{port}' for port, org in enumerate(ORGANIZATIONS, 9001)})
            provider = provider_from_env(engine, {'HARVESTNET_MOVE_TRANSPORT': 'a2a', 'AGENT_ENDPOINTS': endpoints,
                                                  'TRANSPORT_SIGNING_KEY': env['TRANSPORT_SIGNING_KEY_CORE'],
                                                  'TRANSPORT_VERIFY_KEYS': env['TRANSPORT_VERIFY_KEYS_CORE']}, log=QUIET)
            draft = engine.create_offer(copy.deepcopy(scenario()['surplus_offers'][0]))
            turn = {'organization_id': 'city', 'number': 2, 'now': NOW, 'accepted_by': []}
            rural = {'role': 'food_bank', 'draft': draft, 'facts': engine.facts('rural', draft), 'turn': 'city',
                     'turn_context': turn, 'policy_session': engine.policy_session}
            with self.assertRaisesRegex(ValueError, 'not its own'):
                provider('city', rural)
        finally:
            engine.records.close()


if __name__ == '__main__':
    unittest.main()
