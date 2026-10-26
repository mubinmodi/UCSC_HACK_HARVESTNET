"""The core server's JSON responses: shared JSON handler, plus the core's own CORS headers."""
import json
import os
import threading
import unittest
import urllib.request
from unittest import mock

from harvestnet_core.api import API
from harvestnet_core.engine import Engine
from harvestnet_core.server import make_server

from test_core import fixture


class ServerHeaders(unittest.TestCase):
    def setUp(self):
        self.server = make_server(API(Engine(fixture())), port=0)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_responses_are_json_nosniff_nostore_and_carry_the_cors_origin(self):
        with mock.patch.dict(os.environ, {'HARVESTNET_ALLOWED_ORIGIN': 'https://households.example'}):
            with urllib.request.urlopen(self.base + '/health') as response:
                headers, body = response.headers, json.load(response)
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(headers['Content-Type'], 'application/json')
        self.assertEqual((headers['X-Content-Type-Options'], headers['Cache-Control']), ('nosniff', 'no-store'))
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'https://households.example')

    def test_preflight_answers_with_the_allowed_methods_and_headers(self):
        request = urllib.request.Request(self.base + '/requests', method='OPTIONS')
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 204)
            self.assertIn('PUT', response.headers['Access-Control-Allow-Methods'])
            self.assertIn('Authorization', response.headers['Access-Control-Allow-Headers'])

    def test_errors_keep_the_contract_shape_and_non_ascii_text_survives(self):
        request = urllib.request.Request(self.base + '/fair-share?household_size=4&language=es')
        with urllib.request.urlopen(request) as response:
            self.assertIn('hogar', json.load(response)['wording'].lower())
        bad = urllib.request.Request(self.base + '/requests', data=b'[1]', method='POST')
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(bad)
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.load(caught.exception)['error']['code'], 'bad_request')


if __name__ == '__main__':
    unittest.main()
