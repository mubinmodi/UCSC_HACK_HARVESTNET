"""Ticket #25: the backup replay matches what the code produces now.

``docs/demo/replay/recording.json`` and the copy embedded in ``docs/demo/replay.html`` must equal
a fresh recording. If this fails after a deliberate change, rerun
``python -m harvestnet_core.demo_replay`` and commit both files. All data is synthetic.
"""
import json
import re
import unittest

import platform_source  # noqa: F401  (Lane C on the import path)

from harvestnet_core import demo_replay


class DemoReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recording = demo_replay.record()

    def test_saved_recording_and_page_match_the_code(self):
        text, page = demo_replay.render(self.recording)
        self.assertEqual(demo_replay.RECORDING.read_text(encoding='utf-8'), text,
                         'stale recording: run python -m harvestnet_core.demo_replay')
        self.assertEqual(demo_replay.PAGE.read_text(encoding='utf-8'), page,
                         'stale replay page: run python -m harvestnet_core.demo_replay')

    def test_recording_is_labeled_and_synthetic(self):
        r = self.recording
        self.assertEqual(r['label'], 'Recorded replay')
        self.assertIs(r['synthetic'], True)
        self.assertEqual(r['mode'], 'synthetic')
        self.assertIn('RECORDED REPLAY', demo_replay.PAGE.read_text(encoding='utf-8'))
        for scenario in r['results']['shipped']:
            self.assertIs(scenario['synthetic'], True)
            llm = next(m for m in scenario['methods'] if m['method'] == 'llm')
            self.assertEqual(llm['status'], 'not_run')

    def test_variant_changes_only_the_eastside_reply_time(self):
        shipped = json.loads(demo_replay.FIXTURE.read_text(encoding='utf-8'))
        demo = demo_replay.demo_fixture(shipped)
        self.assertEqual({k: v for k, v in demo.items() if k != 'humans'}, {k: v for k, v in shipped.items() if k != 'humans'})
        changed = [(a, b) for a, b in zip(shipped['humans'], demo['humans']) if a != b]
        self.assertEqual([(a['organization_id'], a['after_minutes'], b['after_minutes']) for a, b in changed], [('eastside', 15, 10)])
        self.assertEqual(self.recording['variant']['humans'], demo['humans'])

    def test_the_demo_story_is_in_the_recording(self):
        r = self.recording
        self.assertEqual(r['household']['answers']['language'], 'es')
        self.assertTrue(r['household']['by_language']['es']['consent_question'])
        self.assertGreater(len(r['negotiation']['versions']), 1)
        self.assertTrue(all(m['reason'] for m in r['negotiation']['moves']))
        self.assertEqual(r['cooler_failure']['status'], 'committed')
        self.assertEqual({c['outcome'] for c in r['cooler_failure']['dashboard']['reason_cards']}, {'chosen', 'rejected'})
        self.assertTrue(r['household_emails'])
        spanish = [t for t in r['household_emails'] if t['language'] == 'es']
        self.assertTrue(spanish and all('lechuga romana' in t['message'] for t in spanish))
        # The shipped fixture's own outcome is kept: the late answer is refused.
        cooler = next(s for s in r['results']['shipped'] if s['scenario_id'] == 'cooler-failure')
        rules = next(m for m in cooler['methods'] if m['method'] == 'rules_based')
        self.assertEqual(rules['cooler_failure']['changes_committed'], 0)

    def test_recording_holds_no_contact_details(self):
        self.assertTrue(all(t['to'] is None for t in self.recording['household_emails']))
        self.assertIsNone(re.search(r'\+1\d{10}', json.dumps(self.recording)))
        self.assertIsNone(re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', json.dumps(self.recording)))


if __name__ == '__main__':
    unittest.main()
