"""Actual native App SDK host smoke test; optional heavy dependencies (Linux).

SKIPS unless agntcy-app-sdk is installed (CI's "native-agntcy" job installs it). Locally:

    uv run --with pytest --with-requirements requirements-agntcy.txt pytest -q tests/test_native_agntcy.py

That downloads the pinned SDK from PyPI; some of its dependencies build only on Linux.
"""
import contextlib
import importlib.util
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import URLError, HTTPError
from harvestnet_platform.http import request_json
from harvestnet_platform.moves import A2AMoveProvider
from harvestnet_platform.transport import ORGANIZATIONS, rpc_request
import json
from harvestnet_platform.transport_auth import pair_key
from test_transport import TEST_KEYS, envelope, signer
from test_moves import Fallback, QUIET, core_verifier, wire

AVAILABLE = importlib.util.find_spec('agntcy_app_sdk') is not None


@contextlib.contextmanager
def native_host(organization, **extra_env):
    """The native App SDK host for ``organization`` in its own process, with its own test keys."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = {**os.environ, 'ORGANIZATION_ID': organization, 'AGENT_PUBLIC_URL': base,
           'TRANSPORT_VERIFY_KEYS': json.dumps({s: pair_key(k, organization) for s, k in TEST_KEYS.items() if s != organization}),
           'PORT': str(port), 'AGENT_POLICY': '',
           'AGNTCY_DIRECTORY_ADDRESS': '', 'OTEL_SDK_DISABLED': 'true', 'RECEIPTS_DB': ':memory:', **extra_env}
    with tempfile.TemporaryFile(mode='w+') as log:
        # pip --target dependencies on Windows need their .pth hooks loaded.
        bootstrap = "import site,os,runpy; [site.addsitedir(p) for p in os.environ.get('PYTHONPATH','').split(os.pathsep) if p]; runpy.run_module('harvestnet_platform.agntcy_server',run_name='__main__')"
        process = subprocess.Popen([sys.executable, '-c', bootstrap], env=env,
                                   stdout=log, stderr=log, cwd=Path(__file__).parents[1])
        try:
            until = time.monotonic() + 30
            while time.monotonic() < until:
                if process.poll() is not None:
                    log.seek(0)
                    raise AssertionError('Native SDK startup failed: ' + log.read()[-4000:])
                try:
                    card = request_json(base + '/.well-known/agent-card.json', timeout=1)
                    break
                except (URLError, TimeoutError, OSError):
                    time.sleep(.1)
            else:
                log.seek(0)
                raise AssertionError('Native SDK startup timed out: ' + log.read()[-4000:])
            yield base, card
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@unittest.skipUnless(AVAILABLE, 'SKIPPED NATIVE AGNTCY: agntcy-app-sdk not installed; run: uv run --with pytest '
                                '--with-requirements requirements-agntcy.txt pytest -q tests/test_native_agntcy.py (Linux)')
class NativeAGNTCYTests(unittest.TestCase):
    def test_native_sdk_host_authenticates_and_returns_organization_move(self):
        with native_host('market') as (base, card):
            self.assertEqual(card['name'], 'HarvestNet market')
            with self.assertRaises(HTTPError) as denied:
                request_json(base + '/', rpc_request(envelope()))  # unsigned
            self.assertEqual(denied.exception.code, 401)
            response = request_json(base + '/', rpc_request(signer().sign(envelope(), 'market')))
            self.assertEqual(response['result']['parts'][0]['data']['move']['action'], 'ask_human')

    def test_native_sdk_host_answers_the_cores_move_request_with_a_signed_reply(self):
        # The same move request the live core sends (harvestnet_platform.moves), to a native host
        # that signs its reply with its own key; the core checks it as it checks a JSON-RPC host.
        with native_host('city', TRANSPORT_SIGNING_KEY=TEST_KEYS['city']) as (base, _card):
            endpoints = {org: 'http://127.0.0.1:9' for org in ORGANIZATIONS}
            fallback = Fallback()
            moves = A2AMoveProvider({**endpoints, 'city': base}, signer(), core_verifier(), fallback,
                                    timeout=10, retry_seconds=0, log=QUIET)
            move = moves('city', wire('city'))
            metadata = moves.pop_metadata()
            self.assertEqual(metadata['move_source'], 'a2a', metadata)
            self.assertEqual(metadata['transport'], 'agntcy_native')
            self.assertEqual(move['organization_id'], 'city')
            self.assertEqual(move['action'], 'ask_human')  # the labeled synthetic stand-in policy
            self.assertEqual(fallback.calls, [])
        # A native host without its own signing key cannot answer, and the core falls back, labeled.
        with native_host('city') as (base, _card):
            moves = A2AMoveProvider({**endpoints, 'city': base}, signer(), core_verifier(), fallback,
                                    timeout=10, retry_seconds=0, log=QUIET)
            moves('city', wire('city'))
            self.assertEqual(moves.pop_metadata()['move_source'], 'in_process_fallback')
            self.assertEqual(fallback.calls, ['city'])
