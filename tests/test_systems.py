import json
import threading
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from harvestnet_platform.systems import Systems, handler_for
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
                reading = systems.read('donor', 'inventory')
                self.assertEqual(reading['mode'], 'replay')
                self.assertIn('fallback_reason', reading)

    def test_real_http_read_switch_and_exported_examples(self):
        systems = Systems()
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(systems, 'test-switch'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            self.assertTrue(request_json(base + '/systems/donor/inventory')['synthetic'])
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


if __name__ == '__main__':
    unittest.main()
