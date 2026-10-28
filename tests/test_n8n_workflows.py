"""The n8n email workflows are not open mail relays: each checks its recipient itself.

Runs each Code node's JavaScript under Node with stand-ins for n8n's ``$vars`` and ``$json``.
Placeholder addresses and tokens only. Skips when Node is not installed.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'integrations' / 'n8n'
NODE = shutil.which('node')
VARS = {'HARVESTNET_EMAIL_ALLOWLIST': 'staff@example.org, Other@Example.org',
        'HARVESTNET_REVIEW_BASE_URL': 'https://demo.example/'}
REVIEW = {'to': 'staff@example.org', 'organization_id': 'city', 'lot_id': 'lot-market-1013', 'version': 2,
          'terms_hash': 'sha256:' + 'a' * 64, 'decision_url': 'https://demo.example/human/review?token=' + 'T' * 43}
PREPARED = {'to': 'other@example.org', 'kind': 'pickup_ready', 'language': 'en', 'subject': 'HarvestNet: ready',
            'text': 'Your produce is ready.', 'mode': 'prepared_email', 'sent': False}


def code_node(name, node_name):
    flow = json.loads((ROOT / f'{name}.json').read_text())
    return next(n for n in flow['nodes'] if n['name'] == node_name)['parameters']['jsCode']


def run(code, item, variables=VARS):
    script = ('const $vars = %s; const $json = %s; const f = new Function("$vars", "$json", %s);'
              'try { console.log(JSON.stringify({ok: f($vars, $json)})); } catch (e) { console.log(JSON.stringify({error: e.message})); }'
              % (json.dumps(variables), json.dumps(item), json.dumps(code)))
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@unittest.skipUnless(NODE, 'SKIPPED n8n JS check: node is not installed')
class EmailWorkflows(unittest.TestCase):
    def test_review_email_is_a_fixed_template_for_an_allowed_recipient_only(self):
        code = code_node('approval-requests', 'Check recipient and write review email')
        out = run(code, {'body': {**REVIEW, 'message': 'free text from the caller', 'subject': 'Win a prize'}})['ok'][0]['json']
        self.assertEqual(set(out), {'to', 'subject', 'message'})
        self.assertEqual(out['subject'], 'HarvestNet: review draft version 2 for lot lot-market-1013')
        self.assertIn(REVIEW['decision_url'], out['message'])
        self.assertNotIn('free text', out['message'])
        self.assertNotIn('prize', out['subject'])
        bad = [{**REVIEW, 'to': 'anyone@elsewhere.example'},
               {**REVIEW, 'decision_url': 'https://phish.example/human/review?token=' + 'T' * 43},
               {**REVIEW, 'decision_url': REVIEW['decision_url'] + '&next=https://phish.example'},
               {**REVIEW, 'version': '2'}, {**REVIEW, 'terms_hash': 'anything'},
               {**REVIEW, 'lot_id': 'lot 1\nBcc: x@example.org'}]
        for body in bad:
            with self.subTest(body=body):
                self.assertIn('error', run(code, {'body': body}))
        self.assertIn('error', run(code, {'body': REVIEW}, {**VARS, 'HARVESTNET_EMAIL_ALLOWLIST': ''}))  # fails closed

    def test_pickup_and_release_emails_check_the_recipient_themselves(self):
        for name in ('pickup-emails', 'cannot-make-it'):
            code = code_node(name, 'Check recipient allowlist')
            with self.subTest(name):
                self.assertEqual(run(code, PREPARED)['ok'][0]['json'],
                                 {'to': 'other@example.org', 'subject': PREPARED['subject'], 'text': PREPARED['text']})
                self.assertIn('error', run(code, {**PREPARED, 'to': 'household@elsewhere.example'}))
                self.assertIn('error', run(code, {**PREPARED, 'mode': 'raw'}))
                self.assertIn('error', run(code, PREPARED, {}))  # no allowlist variable: nothing is sent

    def test_every_email_workflow_checks_before_it_sends(self):
        for path in ROOT.glob('*.json'):
            flow = json.loads(path.read_text())
            order = [n['type'] for n in flow['nodes']]
            if 'n8n-nodes-base.emailSend' in order:
                before = flow['nodes'][order.index('n8n-nodes-base.emailSend') - 1]
                self.assertEqual(before['type'], 'n8n-nodes-base.code', path.name)
                self.assertIn('HARVESTNET_EMAIL_ALLOWLIST', before['parameters']['jsCode'], path.name)


if __name__ == '__main__':
    unittest.main()
