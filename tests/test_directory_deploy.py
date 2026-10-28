"""The AGNTCY Directory on the AWS instance (deploy/aws/compose.directory.yaml).

No network: the Directory client is replaced by an in-memory stand-in, and the Compose
checks use `docker compose config` when Docker is installed (text checks otherwise)."""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import subprocess
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from harvestnet_platform import directory as directory_module
from harvestnet_platform.directory import record_info, start_publisher
from harvestnet_platform.systems import Systems
from harvestnet_platform.transport import ORGANIZATIONS

ROOT = Path(__file__).resolve().parents[1]
AWS = ROOT / 'deploy' / 'aws'
COMPOSE_FILES = ['compose.platform.yaml', 'deploy/aws/compose.aws.yaml', 'deploy/aws/compose.directory.yaml']
ORG_SERVICES = ['donor', 'city', 'rural', 'eastside', 'advocate']
ENDPOINTS = {org: f'http://{org}:8020' for org in ORGANIZATIONS}


class MemoryDirectory:
    """Stands in for AgntcyDirectory: same calls, records kept in memory."""
    mode = 'agntcy_directory'
    store = {}

    def __init__(self, address=None):
        self.address = address

    def register(self, record):
        cid = f'cid-{len(self.store) + 1}'
        self.store[cid] = copy.deepcopy(record)
        return cid

    def unregister(self, cid):
        self.store.pop(cid, None)

    def records(self):
        return directory_module.latest_per_organization(list(self.store.values()))

    def search(self, **query):
        return {'mode': self.mode, 'records': directory_module.search_capability(self.records(), **query)}


class Unavailable(ConnectionError):
    """Stands in for the SDK's gRPC UNAVAILABLE error (a refused connection)."""

    def code(self):
        class Code:
            name = 'UNAVAILABLE'
        return Code


class DownDirectory(MemoryDirectory):
    def register(self, record):
        raise Unavailable('directory:8888 unreachable')

    def records(self):
        raise Unavailable('directory:8888 unreachable')


def run_cli(*args, env=None):
    out = io.StringIO()
    clean = {k: v for k, v in os.environ.items() if k not in ('SYSTEMS_URL', 'AGNTCY_DIRECTORY_ADDRESS', 'AGENT_ENDPOINTS')}
    with patch.dict(os.environ, {**clean, **(env or {})}, clear=True), \
         patch('sys.argv', ['directory', *args]), contextlib.redirect_stdout(out), \
         contextlib.redirect_stderr(io.StringIO()):
        code = directory_module.main()
    return code, json.loads(out.getvalue())


class HostRegistration(unittest.TestCase):
    def setUp(self):
        MemoryDirectory.store = {}

    def test_each_host_registers_its_own_record_in_the_background(self):
        stop = threading.Event()
        threads = []
        try:
            with patch.object(directory_module, 'AgntcyDirectory', MemoryDirectory):
                for org in ORGANIZATIONS:
                    publisher, thread = start_publisher(org, ENDPOINTS[org], 'directory:8888', Systems(), 60, stop)
                    threads.append(thread)
                    for _ in range(200):
                        if publisher.cid:
                            break
                        threading.Event().wait(0.01)
                    self.assertTrue(thread.daemon)
        finally:
            stop.set()
            for thread in threads:
                thread.join(timeout=1)
        registered = {record_info(r)['organization_id'] for r in MemoryDirectory.store.values()}
        self.assertEqual(registered, set(ORGANIZATIONS))

    def test_a_directory_that_is_down_does_not_stop_the_host(self):
        stop = threading.Event()
        try:
            with patch.object(directory_module, 'AgntcyDirectory', DownDirectory), contextlib.redirect_stdout(io.StringIO()):
                publisher, thread = start_publisher('city', ENDPOINTS['city'], 'directory:8888', Systems(), 0.01, stop)
                threading.Event().wait(0.05)
                self.assertTrue(thread.is_alive())  # still retrying
        finally:
            stop.set()
            thread.join(timeout=1)
        self.assertIsNone(publisher.cid)

    def test_a_bug_is_not_hidden_as_a_directory_outage(self):
        class Broken(MemoryDirectory):
            def register(self, record):
                raise TypeError('a programming error, not an outage')
        publisher = directory_module.DirectoryPublisher(Broken(), 'city', ENDPOINTS['city'], Systems())
        stop = threading.Event()
        with self.assertRaises(TypeError):
            publisher.run_forever(0.01, stop)


class DirectoryCli(unittest.TestCase):
    query = ['--cold-lb', '100', '--pickup-at', '2026-10-13T19:00:00-07:00']

    def setUp(self):
        MemoryDirectory.store = {}
        directory = MemoryDirectory()
        for org in ORGANIZATIONS:
            directory.register(directory_module.record_for(org, ENDPOINTS[org], Systems(), published_at='2026-10-11T15:00:00+00:00'))

    def test_list_and_capability_search_come_from_the_agntcy_directory(self):
        env = {'AGNTCY_DIRECTORY_ADDRESS': 'directory:8888'}
        with patch.object(directory_module, 'AgntcyDirectory', MemoryDirectory):
            code, listed = run_cli('--list', env=env)
            self.assertEqual((code, listed['mode']), (0, 'agntcy_directory'))
            self.assertEqual([row['organization_id'] for row in listed['registered']], list(ORGANIZATIONS))
            code, found = run_cli('--brief', *self.query, env=env)
        self.assertEqual((code, found['mode'], found['address']), (0, 'agntcy_directory', 'directory:8888'))
        self.assertEqual([row['organization_id'] for row in found['matches']], ['city', 'eastside'])  # synthetic fixture

    def test_unreachable_directory_falls_back_to_the_labeled_local_registry(self):
        env = {'AGNTCY_DIRECTORY_ADDRESS': 'directory:8888', 'AGENT_ENDPOINTS': json.dumps(ENDPOINTS)}
        with patch.object(directory_module, 'AgntcyDirectory', DownDirectory):
            code, found = run_cli('--brief', *self.query, env=env)
            self.assertEqual(code, 2)
            self.assertEqual(found['mode'], 'local_directory_fallback')
            self.assertEqual(found['agntcy_unreachable'], 'directory:8888: UNAVAILABLE')
            self.assertTrue(found['synthetic'])
            code, listed = run_cli('--list', env=env)
        self.assertEqual((code, listed['mode']), (2, 'local_directory_fallback'))

    def test_unreachable_directory_without_endpoints_fails_visibly(self):
        with patch.object(directory_module, 'AgntcyDirectory', DownDirectory), self.assertRaises(Unavailable):
            run_cli('--list', env={'AGNTCY_DIRECTORY_ADDRESS': 'directory:8888'})

    def test_no_address_uses_the_local_registry(self):
        code, found = run_cli('--brief', *self.query, env={'AGENT_ENDPOINTS': json.dumps(ENDPOINTS)})
        self.assertEqual((code, found['mode']), (0, 'local_directory_fallback'))


class DeployFiles(unittest.TestCase):
    text = (AWS / 'compose.directory.yaml').read_text()

    def test_every_script_uses_the_same_three_compose_files(self):
        wanted = ' '.join(f'-f {name}' for name in COMPOSE_FILES)
        for name in ('remote_deploy.sh', 'logs.sh', 'check_directory.sh'):
            script = re.sub(r'\s*\n\s*', ' ', (AWS / name).read_text())
            self.assertIn(wanted, script, name)

    def test_image_is_the_official_full_daemon_pinned_by_version_and_digest(self):
        self.assertRegex(self.text, r'image: ghcr\.io/agntcy/dir-ctl:v\d+\.\d+\.\d+@sha256:[0-9a-f]{64}\n')
        self.assertIn('command: [daemon, start, --data-dir, /home/nonroot/dir]', self.text)
        self.assertIn('DIRECTORY_DAEMON_SERVER_LISTEN_ADDRESS: 0.0.0.0:8888', self.text)

    def test_app_image_installs_the_pinned_directory_sdk(self):
        pins = [line for line in (ROOT / 'requirements-agntcy.txt').read_text().splitlines() if line.startswith('agntcy-dir==')]
        self.assertEqual(len(pins), 1)
        self.assertIn("grep -E '^agntcy-dir==' requirements-agntcy.txt", (AWS / 'Dockerfile').read_text())

    def test_check_script_only_reads_on_the_instance(self):
        script = (AWS / 'check_directory.sh').read_text()
        self.assertNotRegex(script, r'--register|/demo/|docker (rm|stop|restart|volume rm)|compose (up|down|restart)')

    def test_text_shape_without_docker(self):
        directory = self.text.split('\n  directory:\n', 1)[1].split('\n\n', 1)[0]
        self.assertNotIn('ports:', directory)
        self.assertRegex(directory, r'mem_limit: \d+m')
        self.assertIn('networks: [platform, egress]', directory)
        self.assertIn('directory-data:/home/nonroot', directory)
        for service in ORG_SERVICES:
            self.assertIn(f'\n  {service}:\n    environment: *directory-env', self.text)
        self.assertIn('AGNTCY_DIRECTORY_ADDRESS: directory:8888', self.text)


@unittest.skipUnless(shutil.which('docker') and subprocess.run(['docker', 'compose', 'version'],
                     capture_output=True).returncode == 0, 'docker compose not available')
class DirectoryComposeConfig(unittest.TestCase):
    def test_merged_config(self):
        from deploy_env import compose_env
        env = compose_env()
        args = ['docker', 'compose', '-p', 'harvestnet']
        for name in COMPOSE_FILES:
            args += ['-f', name]
        result = subprocess.run([*args, 'config', '--format', 'json'], capture_output=True, text=True, cwd=ROOT, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        services = config['services']
        directory = services['directory']
        self.assertNotIn('ports', directory)
        self.assertLessEqual(int(directory['mem_limit']), 256 * 1024 * 1024)
        self.assertEqual(set(directory['networks']), {'platform', 'egress'})
        self.assertTrue(config['networks']['platform']['internal'])
        self.assertEqual(directory['volumes'][0]['source'], 'directory-data')
        self.assertIn('healthcheck', directory)
        self.assertEqual(directory['command'], ['daemon', 'start', '--data-dir', '/home/nonroot/dir'])
        for name in ORG_SERVICES:
            environment = services[name]['environment']
            self.assertEqual(environment['AGNTCY_DIRECTORY_ADDRESS'], 'directory:8888', name)
            self.assertEqual(environment['SYSTEMS_URL'], 'http://systems:8010', name)
            self.assertEqual(environment['AGENT_POLICY'], 'harvestnet_core.join_adapter:policy', name)  # overlays merge
            self.assertIn('TRANSPORT_VERIFY_KEYS', environment, name)  # overlays keep the platform's own keys
        for name, service in services.items():
            if name != 'gateway':
                self.assertNotIn('ports', service, f'{name} must stay private')


if __name__ == '__main__':
    unittest.main()
