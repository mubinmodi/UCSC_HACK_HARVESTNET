"""Boundary, restart and concurrency checks beyond the happy-path rehearsal."""
import copy
import json
import math
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from harvestnet_platform.approvals import ApprovalStore, CoreAPI, handler_for, pickup_message
from harvestnet_platform.budget import Budget, BudgetExceeded
from harvestnet_platform.directory import search_capability
from harvestnet_platform.http import request_json
from harvestnet_platform.join import MoveBridge
from harvestnet_platform.systems import Systems, BANKS, SYSTEM_ORGANIZATIONS
from harvestnet_platform.transport import Receiver, handler_for as transport_handler, rpc_request


def envelope():
    return {'event_id': 'restart', 'sequence': 1, 'turn': 'market',
            'input': {'role': 'donor', 'draft': {'version': 1, 'terms': {}}, 'facts': {},
                      'turn': {'organization_id': 'market', 'number': 1, 'now': '2026-10-13T12:00:00-07:00', 'accepted_by': []}}}


def notice():
    return {'committed': True, 'food_bank': 'City', 'items': [{'name': 'apples', 'pounds': 8}],
            'window': {'start': '18:00', 'end': '20:00'}, 'request_code': 'TEST',
            'pickup_id': 'pickup-test', 'version': 1, 'release_url': 'https://example.invalid/release'}


class ResilienceTests(unittest.TestCase):
    def test_http_transport_rejects_bad_shapes_without_losing_next_valid_turn(self):
        receiver = Receiver('market')
        server = ThreadingHTTPServer(('127.0.0.1', 0), transport_handler(receiver, 'transport-test', 'http://localhost'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}/'
        try:
            with self.assertRaises(HTTPError) as unauthenticated:
                request_json(url, rpc_request(envelope()))
            self.assertEqual(unauthenticated.exception.code, 401)
            for params in (None, [], {'message': None}, {'message': {'role': 'user', 'parts': [None]}},
                           {'message': {'role': 'user', 'parts': [{'kind': 'data', 'data': []}]}}):
                response = request_json(url, {'jsonrpc': '2.0', 'id': 'bad', 'method': 'message/send', 'params': params}, token='transport-test')
                self.assertEqual(response['error']['code'], -32602)
            self.assertEqual(receiver.observed_order('restart'), [])
            response = request_json(url, rpc_request(envelope()), token='transport-test')
            self.assertEqual(response['result']['parts'][0]['data']['sequence'], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            receiver.db.close()

    def test_notification_validation_returns_400_before_any_delivery(self):
        store = ApprovalStore()
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(store, CoreAPI(), 'events', 'http://localhost'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}/notifications/prepare'
        try:
            with self.assertRaises(HTTPError) as failure:
                request_json(url, {**notice(), 'items': [None], 'to': '+18315550100'}, token='events')
            self.assertEqual(failure.exception.code, 400)
            result = request_json(url, {**notice(), 'to': '+18315550100'}, token='events')
            self.assertFalse(result['sent'])
            self.assertIn('8 lb apples', result['message'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            store.db.close()

    def test_n8n_workflow_graphs_are_inactive_authenticated_and_separate_human_decisions(self):
        root = Path(__file__).parents[1] / 'integrations' / 'n8n'
        workflows = {path.stem: json.loads(path.read_text()) for path in root.glob('*.json')}
        self.assertEqual(len(workflows), 4)
        for flow in workflows.values():
            self.assertFalse(flow['active'])
            nodes = {n['name']: n for n in flow['nodes']}
            event = nodes['Authenticated event']
            self.assertEqual(event['parameters']['authentication'], 'headerAuth')
            self.assertEqual(event['parameters']['responseMode'], 'responseNode')
            visited, name = set(), event['name']
            while name != 'Respond':
                self.assertNotIn(name, visited)
                visited.add(name)
                edge = flow['connections'][name]['main'][0]
                self.assertEqual(len(edge), 1)
                name = edge[0]['node']
                self.assertIn(name, nodes)
            self.assertEqual(visited | {'Respond'}, set(nodes))
            self.assertEqual(flow['settings']['saveDataSuccessExecution'], 'none')
            self.assertEqual(flow['settings']['saveDataErrorExecution'], 'none')
        decision = workflows['human-decisions']
        self.assertFalse(any(node['type'] == 'n8n-nodes-base.twilio' for node in decision['nodes']))
        api = next(node for node in decision['nodes'] if node['type'] == 'n8n-nodes-base.httpRequest')
        self.assertIn('HARVESTNET_CORE_URL', api['parameters']['url'])
        self.assertEqual(api['parameters']['jsonBody'], '={{ JSON.stringify($json.body) }}')

    def test_receiver_duplicate_threads_and_restart_do_not_repeat_policy(self):
        with TemporaryDirectory() as tmp:
            calls = []
            def policy(org, data):
                calls.append(1)
                return {'organization_id': org, 'version': 1, 'action': 'ask_human', 'reason': 'test'}
            path = str(Path(tmp) / 'receipts.sqlite')
            receiver = Receiver('market', policy, path)
            with ThreadPoolExecutor(max_workers=8) as pool:
                receipts = list(pool.map(lambda _: receiver.receive(envelope()), range(30)))
            self.assertEqual(len(calls), 1)
            self.assertTrue(all(r == receipts[0] for r in receipts))
            receiver.db.close()
            restarted = Receiver('market', policy, path)
            self.assertEqual(restarted.receive(envelope()), receipts[0])
            self.assertEqual(len(calls), 1)
            restarted.db.close()

    def test_malformed_nested_transport_inputs_are_validation_errors(self):
        for field, value in [('input', []), ('input', None)]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                Receiver('market').receive({**envelope(), field: value})
        for draft in ([], None, 'wrong'):
            data = envelope()
            data['input']['draft'] = draft
            with self.subTest(draft=draft), self.assertRaises(ValueError):
                Receiver('market').receive(data)

    def test_invalid_network_receipt_keeps_pending_turn_for_retry(self):
        class InvalidThenValid:
            def broadcast(self, data):
                return [{'organization_id': 'city', 'move': None}]
        bridge = MoveBridge(InvalidThenValid())
        data = envelope()['input']
        with self.assertRaises(ValueError):
            bridge('market', data)
        self.assertEqual(bridge.sequence, 0)
        self.assertIsNotNone(bridge.pending)

    def test_budget_shared_connections_enforce_global_cap_concurrently(self):
        with TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'budget.sqlite')
            budgets = [Budget(path, run_cap_usd=1, total_cap_usd=1) for _ in range(12)]
            def reserve(index):
                try:
                    budgets[index].reserve('same-run', str(index), .2)
                    return True
                except BudgetExceeded:
                    return False
            with ThreadPoolExecutor(max_workers=12) as pool:
                self.assertEqual(sum(pool.map(reserve, range(12))), 5)
            self.assertEqual(budgets[0].db.execute('SELECT SUM(cents) FROM charges').fetchone()[0], 100)
            for budget in budgets:
                budget.db.close()

    def test_approval_restart_preserves_receipt_and_independent_votes(self):
        with TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'approvals.sqlite')
            store = ApprovalStore(path)
            links = store.request('lot', 1, {'lb': 8}, ['market', 'city'])
            link = links[0]
            receipt = store.decide(link['token'], 'approve', 1, link['terms_hash'], True)
            store.db.close()
            restarted = ApprovalStore(path)
            self.assertEqual(restarted.decide(link['token'], 'approve', 1, link['terms_hash'], True), receipt)
            self.assertEqual(restarted.approved_organizations('lot'), ['market'])
            with self.assertRaises(ValueError):
                restarted.decide(link['token'], 'decline', 1, link['terms_hash'], True)
            restarted.db.close()

    def test_core_outage_returns_503_then_retries_same_human_receipt(self):
        store = ApprovalStore()
        link = store.request('lot', 1, {'lb': 8}, ['market'])[0]
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(store, CoreAPI('https://core.example', {'market': 'market-staff'}), 'events', 'http://localhost'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        body = {'token': link['token'], 'decision': 'approve', 'version': 1,
                'terms_hash': link['terms_hash'], 'human_confirmed': True}
        try:
            with patch('harvestnet_platform.approvals.request_json', side_effect=URLError('outage')):
                with self.assertRaises(HTTPError) as failure:
                    request_json(f'http://127.0.0.1:{server.server_port}/human/decision', body)
                self.assertEqual(failure.exception.code, 503)
            first_receipt = store.view(link['token'])['receipt_id']
            with patch('harvestnet_platform.approvals.request_json', return_value={'committed': False}) as call:
                result = request_json(f'http://127.0.0.1:{server.server_port}/human/decision', body)
                self.assertFalse(result['committed'])
                self.assertEqual(call.call_args.args[1]['receipt_id'], first_receipt)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            store.db.close()

    def test_pickup_malformed_empty_and_nonfinite_quantities_rejected(self):
        invalid = [[], [None], [{'name': 'apples', 'pounds': True}],
                   [{'name': 'apples', 'pounds': math.nan}], [{'name': '', 'pounds': 8}]]
        for items in invalid:
            with self.subTest(items=items), self.assertRaises(ValueError):
                pickup_message({**notice(), 'items': items})
        for key, value in [('window', []), ('release_url', ''), ('version', True)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                pickup_message({**notice(), key: value})

    def test_capacity_query_nonfinite_values_rejected(self):
        for amount in (math.nan, math.inf, -math.inf, True):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                search_capability([], min_cold_lb=amount)

    def test_all_system_resources_accept_mock_contract_and_failures_are_isolated(self):
        systems = Systems('https://mock.example')
        for org in SYSTEM_ORGANIZATIONS:
            for resource in systems.fixture[org]:
                recorded = systems.recorded(org, resource)
                with patch('harvestnet_platform.systems.request_json', return_value=copy.deepcopy(recorded)):
                    reading = systems.read(org, resource)
                    self.assertEqual(reading['source'], 'beeceptor')
                    self.assertTrue(reading['synthetic'])
        for bank in BANKS:
            offline = Systems()
            offline.switch(bank, True)
            self.assertEqual(offline.read(bank, 'storage')['data']['cold_available_lb'], 0)
            for other in set(BANKS) - {bank}:
                self.assertEqual(offline.read(other, 'cooler')['data']['status'], 'working')
