"""Live cooler failure and voice intake wiring on the AWS stack (#22, #23). No network, no AWS.

- The gateway exposes only the demo cooler switch (POST /systems/demo/<bank>/cooler), behind
  the DEMO_SWITCH_TOKEN bearer; the systems service answers 401 without it.
- The three food bank hosts, and only they, run their own cooler watcher.
- The core receives the Anthropic key, and the image carries the SDK.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError

from harvestnet_platform.http import request_json
from harvestnet_platform.systems import Systems, handler_for

ROOT = Path(__file__).resolve().parents[1]
AWS = ROOT / 'deploy' / 'aws'


class DemoSwitchRoute(unittest.TestCase):
    def test_caddy_exposes_only_the_post_switch_and_keeps_systems_private(self):
        caddy = (AWS / 'Caddyfile').read_text()
        # One proxy to the systems service in the whole gateway, inside the switch handler.
        self.assertEqual(caddy.count('systems:8010'), 1)
        block = re.search(r'@coolerswitch \{(.*?)\n\t\}\n\thandle @coolerswitch \{(.*?)\n\t\}', caddy, re.S)
        self.assertIsNotNone(block, 'the switch matcher and handler')
        matcher, handler = block.groups()
        self.assertIn('method POST', matcher)
        self.assertIn(r'path_regexp ^/systems/demo/(city|rural|eastside)/cooler$', matcher)
        self.assertIn('uri strip_prefix /systems', handler)
        self.assertIn('reverse_proxy systems:8010', handler)
        # No wildcard route onto the readings (/systems/<org>/<resource>).
        self.assertNotRegex(caddy, r'handle(_path)? /systems/\*')
        self.assertNotRegex(caddy, r'handle(_path)? /demo')

    def test_the_regexp_matches_exactly_the_three_switch_paths(self):
        caddy = (AWS / 'Caddyfile').read_text()
        pattern = re.search(r'path_regexp (\^/systems/demo/.*\$)', caddy).group(1)
        for ok in ('/systems/demo/city/cooler', '/systems/demo/rural/cooler', '/systems/demo/eastside/cooler'):
            self.assertRegex(ok, pattern)
        for bad in ('/systems/demo/market/cooler', '/systems/city/cooler', '/systems/demo/city/storage', '/systems/demo/city/cooler/x',
                    '/systems/demo/../city/storage', '/systems/demo/city/cooler?x=1', '/systems/demo/'):
            self.assertNotRegex(bad, pattern)

    def test_the_systems_service_answers_401_without_the_right_token_and_the_stripped_path_works(self):
        systems = Systems()
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(systems, 'switch-token'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            # What Caddy forwards: /systems/demo/city/cooler with the prefix /systems removed.
            for token in (None, 'wrong-token', ''):
                with self.assertRaises(HTTPError) as refused:
                    request_json(base + '/demo/city/cooler', {'failed': True}, token=token)
                self.assertEqual(refused.exception.code, 401)
            self.assertEqual(systems.failed, set())  # nothing changed
            failed = request_json(base + '/demo/city/cooler', {'failed': True}, token='switch-token')
            self.assertEqual((failed['data']['status'], failed['synthetic']), ('failed', True))
            self.assertEqual(request_json(base + '/systems/city/cooler')['data']['status'], 'failed')
            reset = request_json(base + '/demo/city/cooler', {'failed': False}, token='switch-token')
            self.assertEqual(reset['data']['status'], 'working')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_a_service_without_a_configured_token_refuses_everyone(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(Systems(), None))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for token in (None, '', 'None'):
                with self.assertRaises(HTTPError) as refused:
                    request_json(f'http://127.0.0.1:{server.server_port}/demo/city/cooler', {'failed': True}, token=token)
                self.assertEqual(refused.exception.code, 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class DeployWiring(unittest.TestCase):
    def test_the_secret_allowlist_and_setup_carry_the_anthropic_key(self):
        loader = (ROOT / 'deploy' / 'load_secrets.py').read_text()
        self.assertIn("'ANTHROPIC_API_KEY'", loader)
        self.assertIn("'CLAUDE_RUN_CAP_USD'", loader)
        self.assertIn('"ANTHROPIC_API_KEY"', (AWS / 'setup.sh').read_text())

    def test_the_image_installs_the_anthropic_sdk_through_the_agents_claude_extra(self):
        self.assertRegex((AWS / 'Dockerfile').read_text(), r'pip install [^\n]*"\./agents\[claude\]"')
        self.assertIn('claude = ["anthropic', (ROOT / 'agents' / 'pyproject.toml').read_text())


@unittest.skipUnless(shutil.which('docker') and subprocess.run(['docker', 'compose', 'version'],
                     capture_output=True).returncode == 0, 'docker compose not available')
class ComposeServices(unittest.TestCase):
    def config(self, *overlays):
        env = {'PATH': os.environ['PATH'], 'HOME': os.environ.get('HOME', '/tmp'), 'HARVESTNET_RELEASE': 'test',
               'TRANSPORT_TOKEN': 'x', 'API_EVENTS_TOKEN': 'events', 'DEMO_SWITCH_TOKEN': 'x', 'ANTHROPIC_API_KEY': 'k',
               'APPROVAL_PUBLIC_URL': 'https://example.invalid', 'HARVESTNET_ALLOWED_ORIGIN': 'https://example.invalid',
               'HARVESTNET_STAFF_TOKENS': '{"city":"x"}', 'HARVESTNET_DOMAIN': 'example.invalid'}
        files = ['compose.platform.yaml', 'deploy/aws/compose.aws.yaml', *overlays]
        args = [a for f in files for a in ('-f', f)]
        result = subprocess.run(['docker', 'compose', '-p', 'harvestnet', *args, 'config', '--format', 'json'],
                                capture_output=True, text=True, cwd=ROOT, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)['services']

    def test_only_the_food_bank_hosts_run_a_watcher_with_what_it_needs(self):
        for overlays in ((), ('deploy/aws/compose.directory.yaml',)):
            services = self.config(*overlays)
            for bank in ('city', 'rural', 'eastside'):
                env = services[bank]['environment']
                self.assertEqual(env['COOLER_WATCH'], '1', bank)
                self.assertEqual((env['SYSTEMS_URL'], env['APPROVALS_URL']), ('http://systems:8010', 'http://approvals:8030'))
                self.assertEqual((env['API_EVENTS_TOKEN'], env['AGENT_POLICY']), ('events', 'harvestnet_core.join_adapter:policy'))
                self.assertIn('HARVESTNET_STAFF_TOKENS', env)
                self.assertIn('/app/runtime', json.dumps(services[bank]['volumes']))  # the saved episode survives a restart
            for other in ('donor', 'advocate'):
                env = services[other]['environment']
                for name in ('COOLER_WATCH', 'HARVESTNET_STAFF_TOKENS', 'API_EVENTS_TOKEN'):
                    self.assertNotIn(name, env, f'{other} has no cooler watcher and no core or approval credentials')

    def test_the_core_gets_the_key_and_cap_and_nothing_new_is_published(self):
        services = self.config()
        env = services['core']['environment']
        self.assertEqual(env['ANTHROPIC_API_KEY'], 'k')
        self.assertIn('CLAUDE_RUN_CAP_USD', env)
        for name, service in services.items():
            if name != 'gateway':
                self.assertNotIn('ports', service, f'{name} must stay private')


if __name__ == '__main__':
    unittest.main()
