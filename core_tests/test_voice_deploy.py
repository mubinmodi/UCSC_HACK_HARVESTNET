"""#22: the deployed core attaches the capped Claude extractor only with a key and a cap.

All data is synthetic. No paid API is called: every extractor here has a fake client.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from harvestnet_core.api import API
from harvestnet_core.engine import Engine
from harvestnet_core.voice import CappedExtractor, extractor_from_env

from test_core import fixture
from test_followups import NOW, fake_claude


class VoiceFromEnv(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(Path('agents/tests/fixtures/front_desk/en_complete.json').read_text())
        self.body = {'transcript': self.data['transcript'], 'call_id': 'recorded'}
        self.calls = []
        self.client = fake_claude(self.data['extractor_output'], self.calls)

    def api(self, environ):
        return API(Engine(fixture()), clock=lambda: NOW, extractor=extractor_from_env(environ, client=self.client))

    def test_no_key_or_no_cap_keeps_the_503_fallback(self):
        for environ in ({}, {'ANTHROPIC_API_KEY': ''}, {'ANTHROPIC_API_KEY': '  ', 'CLAUDE_RUN_CAP_USD': '2'},
                        {'ANTHROPIC_API_KEY': 'k'}, {'ANTHROPIC_API_KEY': 'k', 'CLAUDE_RUN_CAP_USD': '0'},
                        {'ANTHROPIC_API_KEY': 'k', 'CLAUDE_RUN_CAP_USD': ''},
                        {'ANTHROPIC_API_KEY': 'k', 'CLAUDE_RUN_CAP_USD': 'lots'},
                        {'ANTHROPIC_API_KEY': 'k', 'CLAUDE_RUN_CAP_USD': 'nan'},
                        {'ANTHROPIC_API_KEY': 'k', 'CLAUDE_RUN_CAP_USD': '101'}):
            with self.subTest(environ=environ):
                self.assertIsNone(extractor_from_env(environ, client=self.client))
                status, body = self.api(environ).call('POST', '/voice-intake', self.body)
                self.assertEqual((status, body['error']['code']), (503, 'voice_unavailable'))
        self.assertEqual(self.calls, [])

    def test_key_and_cap_attach_the_capped_claude_extractor(self):
        from harvestnet_agents.front_desk import ClaudeExtractor
        extractor = extractor_from_env({'ANTHROPIC_API_KEY': 'k', 'CLAUDE_RUN_CAP_USD': '1.5'}, client=self.client)
        self.assertIsInstance(extractor, CappedExtractor)
        self.assertIsInstance(extractor.extractor, ClaudeExtractor)
        self.assertEqual(extractor.cap.limit_usd, 1.5)
        self.assertIs(extractor.extractor.cap, extractor.cap)  # one shared cap, charged once
        api = API(Engine(fixture()), clock=lambda: NOW, extractor=extractor)
        status, body = api.call('POST', '/voice-intake', self.body)
        self.assertEqual(status, 200, body)
        self.assertTrue(body['complete'])
        self.assertFalse(body['saved'])  # a draft; nothing is saved without consent
        self.assertEqual(len(self.calls), 1)

    def test_the_cap_stops_calls_and_the_rate_limit_still_applies(self):
        environ = {'ANTHROPIC_API_KEY': 'k', 'CLAUDE_RUN_CAP_USD': '1'}
        extractor = extractor_from_env(environ, client=self.client)
        api = API(Engine(fixture()), clock=lambda: NOW, extractor=extractor, voice_rate_limit=(2, 60), monotonic=lambda: 0.0)
        self.assertEqual(api.call('POST', '/voice-intake', self.body)[0], 200)
        self.assertEqual(api.call('POST', '/voice-intake', self.body)[0], 200)
        status, body = api.call('POST', '/voice-intake', self.body)
        self.assertEqual((status, body['error']['code']), (503, 'rate_limited'))
        self.assertEqual(len(self.calls), 2)
        extractor.cap.limit_usd = extractor.cap.spent_usd  # the cap is reached: no further call is made
        api = API(Engine(fixture()), clock=lambda: NOW, extractor=extractor)
        status, body = api.call('POST', '/voice-intake', self.body)
        self.assertEqual((status, body['error']['code']), (503, 'spending_cap_reached'))
        self.assertEqual(len(self.calls), 2)

    def test_missing_sdk_keeps_the_fallback_instead_of_failing_on_each_call(self):
        with mock.patch.dict(sys.modules, {'anthropic': None}):
            self.assertIsNone(extractor_from_env({'ANTHROPIC_API_KEY': 'k', 'CLAUDE_RUN_CAP_USD': '1'}))

    def test_the_key_is_never_printed(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            extractor_from_env({'ANTHROPIC_API_KEY': 'sk-secret-value', 'CLAUDE_RUN_CAP_USD': '1'}, client=self.client)
        self.assertIn('spending cap', out.getvalue())
        self.assertNotIn('sk-secret-value', out.getvalue())


if __name__ == '__main__':
    unittest.main()
