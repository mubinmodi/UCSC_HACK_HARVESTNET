import copy
import json
import threading
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from datetime import datetime
from harvestnet_platform.systems import Systems, handler_for, SYSTEM_ORGANIZATIONS
from harvestnet_platform.directory import DirectoryPublisher, latest_per_organization, record_for, record_info, search_capability
from harvestnet_platform.http import request_json
from urllib.error import HTTPError, URLError


class SystemsTests(unittest.TestCase):
    def test_failure_is_isolated_persists_and_disables_cold_storage(self):
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / 'coolers.json'
            systems = Systems(state_path=file)
            failed = systems.switch('city', True)
            self.assertTrue(failed['synthetic'])
            self.assertEqual(failed['data']['status'], 'failed')
            self.assertEqual(systems.read('city', 'storage')['data']['cold_available_lb'], 0)
            self.assertEqual(systems.read('rural', 'cooler')['data']['status'], 'working')
            self.assertEqual(Systems(state_path=file).read('city', 'cooler')['data']['status'], 'failed')
            systems.switch('city', False)
            self.assertEqual(systems.read('city', 'storage')['data']['cold_available_lb'], 250)

    def test_outage_and_unlabeled_responses_use_labeled_recordings(self):
        systems = Systems('https://demo.free.beeceptor.com')
        for response in (URLError('offline'), {'data': {}}, {'synthetic': True, 'organization_id': 'wrong'}):
            kwargs = {'side_effect': response} if isinstance(response, Exception) else {'return_value': response}
            with patch('harvestnet_platform.systems.request_json', **kwargs):
                reading = systems.read('market', 'inventory')
                self.assertEqual(reading['mode'], 'replay')
                self.assertIn('fallback_reason', reading)

    def test_real_http_read_switch_and_exported_examples(self):
        systems = Systems()
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(systems, 'test-switch'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            self.assertTrue(request_json(base + '/systems/market/inventory')['synthetic'])
            with self.assertRaises(HTTPError) as failure:
                request_json(base + '/demo/city/cooler', {'failed': True})
            self.assertEqual(failure.exception.code, 401)
            reading = request_json(base + '/demo/city/cooler', {'failed': True}, token='test-switch')
            self.assertEqual(reading['data']['temperature_c'], 14)
            for path, route in systems.openapi()['paths'].items():
                self.assertTrue(route['get']['responses']['200']['content']['application/json']['example']['synthetic'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_donor_is_market_and_times_are_october_13_pacific(self):
        systems = Systems()
        self.assertEqual(SYSTEM_ORGANIZATIONS, ('market', 'city', 'rural', 'eastside'))
        self.assertNotIn('donor', systems.fixture)
        self.assertEqual(systems.read('market', 'inventory')['organization_id'], 'market')
        with self.assertRaises(ValueError):
            systems.read('donor', 'inventory')
        def times(value):
            if isinstance(value, dict):
                for v in value.values():
                    yield from times(v)
            elif isinstance(value, list):
                for v in value:
                    yield from times(v)
            elif isinstance(value, str) and value[:4] == '2026':
                yield value
        found = list(times(systems.fixture))
        self.assertGreater(len(found), 15)
        for value in found:
            self.assertTrue(value.endswith('-07:00'), value)
            self.assertIn(datetime.fromisoformat(value).date().isoformat(), ('2026-10-13', '2026-10-14'))
        # The core's normal afternoon: the same lot and deadline.
        core = json.loads((Path(__file__).parents[1] / 'core_fixtures' / 'normal-afternoon.json').read_text())
        offer = core['surplus_offers'][0]
        inventory = systems.fixture['market']['inventory']
        self.assertEqual((inventory['lot_id'], inventory['deadline']), (offer['lot_id'], offer['deadline']))
        for bank in core['food_banks']:
            ours = systems.fixture[bank['organization_id']]
            self.assertEqual(ours['pickup-hours']['windows'], bank['pickup_windows'])
            self.assertEqual(ours['storage']['cold_available_lb'], bank['storage'][0]['cold_free_lb'])

    def test_older_exports_keyed_by_role_still_read_as_market(self):
        systems = Systems()
        legacy = copy.deepcopy(systems.fixture)
        legacy['donor'] = legacy.pop('market')
        systems.fixture = legacy
        self.assertEqual(systems.read('market', 'truck')['data']['capacity_lb'], 700)
        self.assertIn('/systems/market/inventory', systems.openapi()['paths'])

    def test_agent_hosts_read_the_switched_state_from_the_systems_service(self):
        service = Systems()
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(service, 'switch'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host = Systems(f'http://127.0.0.1:{server.server_port}', upstream='harvestnet_systems')
            self.assertEqual(host.read('city', 'storage')['data']['cold_available_lb'], 250)
            service.switch('city', True)
            storage, cooler = host.read('city', 'storage'), host.read('city', 'cooler')
            self.assertEqual(storage['data']['cold_available_lb'], 0)
            self.assertEqual(cooler['data']['status'], 'failed')
            self.assertEqual(cooler['disruption'], 'synthetic_cooler_failure')
            self.assertEqual(cooler['mode'], 'replay')  # the service's own label, not relabeled
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class FakeDirectory:
    def __init__(self):
        self.store, self.next = {}, 0

    def register(self, record):
        self.next += 1
        self.store[f'cid-{self.next}'] = copy.deepcopy(record)
        return f'cid-{self.next}'

    def unregister(self, cid):
        del self.store[cid]


class DirectoryRefreshTests(unittest.TestCase):
    def test_cooler_failure_republishes_capabilities_and_removes_stale_record(self):
        systems, directory = Systems(), FakeDirectory()
        ticks = iter(f'2026-10-13T1{n}:00:00-07:00' for n in range(10))
        publisher = DirectoryPublisher(directory, 'city', 'http://city.example', systems, clock=lambda: next(ticks))
        self.assertEqual(publisher.refresh()['status'], 'published')
        self.assertEqual(publisher.refresh()['status'], 'unchanged')
        self.assertEqual(len(directory.store), 1)
        query = dict(min_cold_lb=100, pickup_at='2026-10-13T19:00:00-07:00')
        self.assertEqual(len(search_capability(list(directory.store.values()), **query)), 1)
        systems.switch('city', True)
        result = publisher.refresh()
        self.assertEqual((result['status'], result['replaced_cid']), ('published', 'cid-1'))
        self.assertEqual(list(directory.store), ['cid-2'])
        caps = record_info(directory.store['cid-2'])['capabilities']
        self.assertEqual(caps['cold_space_lb'], 0)
        self.assertEqual(search_capability(list(directory.store.values()), **query), [])

    def test_search_prefers_the_newest_record_when_a_stale_one_remains(self):
        systems = Systems()
        old = record_for('city', 'http://city.example', systems, published_at='2026-10-13T12:00:00-07:00')
        systems.switch('city', True)
        new = record_for('city', 'http://city.example', systems, published_at='2026-10-13T13:00:00-07:00')
        for records in ([old, new], [new, old]):
            latest = latest_per_organization(records)
            self.assertEqual(len(latest), 1)
            self.assertEqual(record_info(latest[0])['capabilities']['cold_space_lb'], 0)

    def test_refresh_loop_survives_a_directory_outage(self):
        class Down(FakeDirectory):
            def register(self, record):
                raise OSError('directory unavailable')
        stop = threading.Event()
        publisher = DirectoryPublisher(Down(), 'rural', 'http://rural.example', Systems())
        thread = threading.Thread(target=publisher.run_forever, args=(0.01, stop), daemon=True)
        thread.start()
        stop.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())


if __name__ == '__main__':
    unittest.main()
