"""The route table: OPERATIONS names each operation, and each has one ``op_<name>`` handler."""
import unittest
from harvestnet_core.api import API, CONTRACT_VERSION, OPERATIONS, match_route
from harvestnet_core.engine import Engine

from test_core import fixture


class RouteTable(unittest.TestCase):
    def setUp(self):
        self.api = API(Engine(fixture()), clock=lambda: '2026-10-13T12:00:00-07:00', staff_tokens={'market': 'donor-test', 'city': 'city-test'})

    def test_every_operation_has_exactly_one_handler_and_a_unique_route(self):
        self.assertEqual(len({(method, path) for _, method, path, _ in OPERATIONS}), len(OPERATIONS))
        self.assertEqual(len({name for name, *_ in OPERATIONS}), len(OPERATIONS))
        for name, *_ in OPERATIONS:
            self.assertTrue(callable(getattr(self.api, 'op_' + name, None)), name)

    def test_the_agreed_contract_operations_are_all_listed(self):
        agreed = [name for name, _, _, status in OPERATIONS if status == 'agreed']
        self.assertEqual(len(agreed), 20)
        status, index = self.api.call('GET', '/')
        self.assertEqual(status, 200)
        self.assertEqual(index['contract_version'], CONTRACT_VERSION)
        self.assertEqual([o['operation'] for o in index['operations']], [name for name, *_ in OPERATIONS])

    def test_templates_capture_their_named_parts_and_only_fit_their_own_shape(self):
        self.assertEqual(match_route('/requests/{request_code}/food-banks', ['requests', 'K7P4', 'food-banks']), {'request_code': 'K7P4'})
        self.assertEqual(match_route('/health', ['health']), {})
        self.assertIsNone(match_route('/requests/{request_code}', ['requests']))
        self.assertIsNone(match_route('/requests/{request_code}', ['requests', 'K7P4', 'food-banks']))
        self.assertIsNone(match_route('/lots/{lot_id}/versions', ['lots', 'L', 'counters']))

    def test_unknown_paths_and_wrong_methods_are_404_and_trailing_slashes_are_ignored(self):
        for method, target in (('GET', '/nope'), ('POST', '/health'), ('DELETE', '/requests/ABC'), ('GET', '/lots'), ('PUT', '/results')):
            status, body = self.api.call(method, target)
            self.assertEqual((status, body['error']['code']), (404, 'not_found'), (method, target))
        self.assertEqual(self.api.call('GET', '/health/')[0], 200)

    def test_a_path_value_is_looked_up_and_an_unknown_record_is_404(self):
        for target in ('/lots/none', '/lots/none/versions', '/requests/none'):
            self.assertEqual(self.api.call('GET', target)[0], 404, target)


if __name__ == '__main__':
    unittest.main()
