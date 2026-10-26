"""Beeceptor organization systems with recorded, synthetic copies.

The switch selects a failed mock reading; it never alters actual cold storage.
"""
import argparse
import copy
import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit
from urllib.error import URLError
from .http import JsonHandler, request_json, serve
from .roster import BANKS, SYSTEM_ORGANIZATIONS

FIXTURE = Path(__file__).parent / 'fixtures' / 'systems.json'
UPSTREAMS = ('beeceptor', 'harvestnet_systems')


class Systems:
    """Organization systems. ``upstream`` says what ``base_url`` is:

    - ``beeceptor``: the Beeceptor mock. The cooler switch is applied here.
    - ``harvestnet_systems``: this module's own service (``SYSTEMS_URL``), which already
      applied the switch. Its labels (mode, source, disruption) are kept as they are.
    """

    def __init__(self, base_url=None, state_path=None, upstream='beeceptor'):
        if upstream not in UPSTREAMS:
            raise ValueError(f'Upstream must be one of {UPSTREAMS}')
        self.upstream = upstream
        self.base_url = base_url.rstrip('/') if base_url else None
        self.fixture = json.loads(FIXTURE.read_text())
        self.state_path = Path(state_path) if state_path else None
        self.lock = threading.RLock()
        self.failed = set()
        if self.state_path and self.state_path.exists():
            self.failed = set(json.loads(self.state_path.read_text()))
            if self.failed - set(BANKS):
                raise ValueError('Invalid saved cooler state')

    def switch(self, organization, failed):
        if organization not in BANKS or type(failed) is not bool:
            raise ValueError('Select city, rural, or eastside and a boolean failed flag')
        with self.lock:
            if failed:
                self.failed.add(organization)
            else:
                self.failed.discard(organization)
            if self.state_path:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.state_path.with_suffix('.tmp')
                tmp.write_text(json.dumps(sorted(self.failed)))
                tmp.replace(self.state_path)
            return self.read(organization, 'cooler')

    def systems_of(self, organization):
        if organization not in SYSTEM_ORGANIZATIONS:
            raise ValueError('Unknown organization system')
        return self.fixture[organization]

    def recorded(self, organization, resource):
        try:
            data = copy.deepcopy(self.systems_of(organization)[resource])
        except KeyError as exc:
            raise ValueError('Unknown organization system') from exc
        return {'organization_id': organization, 'resource': resource,
                'synthetic': True, 'mode': 'replay', 'source': 'recorded_fixture',
                'fixture_version': self.fixture['fixture_version'],
                'observed_at': self.fixture['observed_at'], 'data': data}

    def read(self, organization, resource):
        with self.lock:
            local_switch = self.upstream == 'beeceptor'
            selected = 'cooler-failed' if local_switch and resource == 'cooler' and organization in self.failed else resource
            fallback = self.recorded(organization, selected)
            if self.base_url:
                try:
                    live = request_json(f'{self.base_url}/systems/{organization}/{selected}')
                    if not isinstance(live, dict) or live.get('synthetic') is not True or live.get('organization_id') != organization or live.get('resource') != selected or live.get('fixture_version') != self.fixture['fixture_version'] or not live.get('observed_at'):
                        raise ValueError('Unlabeled or mismatched Beeceptor reading')
                    expected = fallback['data']
                    if not isinstance(live.get('data'), dict) or set(live['data']) != set(expected):
                        raise ValueError('Beeceptor response does not match the documented contract')
                    for key, value in expected.items():
                        if type(live['data'][key]) is not type(value):
                            raise ValueError('Beeceptor response has an invalid field type')
                    if local_switch:
                        fallback = {**live, 'mode': 'synthetic', 'source': 'beeceptor'}
                    else:
                        fallback = {**live, 'via': 'harvestnet_systems'}
                except (URLError, TimeoutError, ValueError, OSError):
                    fallback['fallback_reason'] = f'{self.upstream} unavailable or incompatible; recorded synthetic copy'
            fallback['resource'] = resource
            if local_switch and resource == 'storage' and organization in self.failed:
                fallback['data']['cold_available_lb'] = 0
                fallback['disruption'] = 'synthetic_cooler_failure'
            if selected == 'cooler-failed':
                fallback['disruption'] = 'synthetic_cooler_failure'
            return fallback

    def openapi(self):
        paths = {}
        for org in SYSTEM_ORGANIZATIONS:
            for resource in self.systems_of(org):
                example = self.recorded(org, resource)
                paths[f'/systems/{org}/{resource}'] = {'get': {
                    'summary': f'Synthetic {org} {resource}',
                    'responses': {'200': {'description': 'Synthetic organization system, never authoritative',
                        'content': {'application/json': {'schema': {'type': 'object'}, 'example': example}}}}}}
        return {'openapi': '3.0.3', 'info': {'title': 'HarvestNet synthetic organization systems', 'version': 'synthetic-v1'}, 'paths': paths}


def organization_systems():
    """An organization host's own systems: the HarvestNet systems service (which applies the
    demo cooler switch) when ``SYSTEMS_URL`` is set, else Beeceptor or recorded copies."""
    if os.getenv('SYSTEMS_URL'):
        return Systems(os.environ['SYSTEMS_URL'], upstream='harvestnet_systems')
    return Systems(os.getenv('BEECEPTOR_BASE_URL'))


def handler_for(systems, token):
    class Handler(JsonHandler):
        def do_GET(self):
            parts = urlsplit(self.path).path.strip('/').split('/')
            try:
                if parts == ['health']:
                    return self.send_json(200, {'status': 'ok', 'synthetic': True})
                if parts == ['openapi.json']:
                    return self.send_json(200, systems.openapi())
                if len(parts) != 3 or parts[0] != 'systems':
                    return self.send_json(404, {'error': 'Not found'})
                self.send_json(200, systems.read(parts[1], parts[2]))
            except ValueError as exc:
                self.send_json(400, {'error': str(exc)})

        def do_POST(self):
            if not self.authorized(token):
                return self.send_json(401, {'error': 'Authorized demo switch token required'})
            parts = urlsplit(self.path).path.strip('/').split('/')
            try:
                if len(parts) != 3 or parts[0] != 'demo' or parts[2] != 'cooler':
                    return self.send_json(404, {'error': 'Not found'})
                self.send_json(200, systems.switch(parts[1], self.read_json()['failed']))
            except (ValueError, KeyError) as exc:
                self.send_json(400, {'error': str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--export-openapi')
    parser.add_argument('--port', type=int, default=8010)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    systems = Systems(os.getenv('BEECEPTOR_BASE_URL'), os.getenv('COOLER_STATE_PATH'))
    if args.export_openapi:
        Path(args.export_openapi).write_text(json.dumps(systems.openapi(), indent=2))
        return
    serve(handler_for(systems, os.getenv('DEMO_SWITCH_TOKEN')), args.port, args.host)


if __name__ == '__main__':
    main()
