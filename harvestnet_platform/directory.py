"""AGNTCY Directory adapter and explicitly separate local registry fallback."""
import argparse
import asyncio
import json
import math
import os
import threading
from datetime import datetime, timezone
from .systems import Systems, BANKS
from .transport import ORGANIZATIONS, agent_card, role_of


def capabilities(organization, systems):
    if organization not in BANKS:
        return {'role': role_of(organization), 'synthetic': True}
    storage = systems.read(organization, 'storage')
    hours = systems.read(organization, 'pickup-hours')
    return {'role': 'food_bank', 'cold_space_lb': storage['data']['cold_available_lb'],
            'pickup_hours': hours['data']['windows'], 'synthetic': True,
            'fixture_version': storage['fixture_version'], 'observed_at': storage['observed_at']}


def record_for(organization, endpoint, systems, published_at=None):
    card = agent_card(organization, endpoint)
    info = {'organization_id': organization, 'capabilities': capabilities(organization, systems)}
    if published_at:
        info['published_at'] = published_at
    # OASF A2A envelope follows the official app-sdk converter.
    # Values are declared capabilities; actual reservations need owner rechecks.
    return {'name': f'harvestnet.org/agents/{organization}', 'schema_version': '1.0.0', 'version': '1.0.0',
            'description': card['description'], 'authors': [card['name']],
            'created_at': systems.fixture['observed_at'], 'skills': [{'id': 101}], 'domains': [],
            'modules': [{'id': 203, 'name': 'integration/a2a', 'data': {'card_data': card, 'card_schema_version': 'v1.0.0'}}],
            'annotations': {'harvestnet': json.dumps(info, sort_keys=True)}}


def record_info(record):
    return json.loads(record.get('annotations', {}).get('harvestnet', '{}'))


def latest_per_organization(records):
    """One record per organization: the most recently published one.

    A capability change publishes a new record (a new CID). If removing the old one
    failed, search may still return it; the newest snapshot wins.
    """
    latest = {}
    for record in records:
        info = record_info(record)
        org = info.get('organization_id')
        if org and (org not in latest or info.get('published_at', '') >= record_info(latest[org]).get('published_at', '')):
            latest[org] = record
    return [latest[org] for org in ORGANIZATIONS if org in latest]


def instant(value):
    time = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if time.tzinfo is None:
        raise ValueError('Capability query/window timestamps require timezone')
    return time


def search_capability(records, *, min_cold_lb=0, pickup_at=None):
    if type(min_cold_lb) not in (int, float) or not math.isfinite(min_cold_lb) or min_cold_lb < 0:
        raise ValueError('Nonnegative cold capacity required')
    matches = []
    for record in records:
        caps = record_info(record).get('capabilities', {})
        if caps.get('role') != 'food_bank' or caps.get('cold_space_lb', 0) < min_cold_lb:
            continue
        if pickup_at and not any(instant(window['start']) <= instant(pickup_at) < instant(window['end']) for window in caps.get('pickup_hours', [])):
            continue
        matches.append(record)
    return matches


class LocalDirectory:
    mode = 'local_directory_fallback'

    def __init__(self, systems, endpoints):
        self.systems, self.endpoints = systems, endpoints

    def records(self):
        return [record_for(org, self.endpoints[org], self.systems) for org in ORGANIZATIONS]

    def search(self, **query):
        return {'mode': self.mode, 'synthetic': True, 'records': search_capability(self.records(), **query)}


class AgntcyDirectory:
    mode = 'agntcy_directory'

    def __init__(self, endpoint):
        from agntcy.dir_sdk.client.client import Client
        from agntcy.dir_sdk.client.config import Config
        self.client = Client(Config(server_address=endpoint))

    def register(self, record):
        from agntcy.dir_sdk.models import core_v1
        from google.protobuf.json_format import ParseDict
        proto = core_v1.Record()
        ParseDict(record, proto.data)
        return self.client.push([proto])[0].cid

    def unregister(self, cid):
        from agntcy.dir_sdk.models import core_v1
        self.client.delete([core_v1.RecordRef(cid=cid)])

    def search(self, **query):
        from agntcy.dir_sdk.models import search_v1
        from google.protobuf.json_format import MessageToDict
        request = search_v1.SearchRecordsRequest(queries=[search_v1.RecordQuery(
            type=search_v1.RecordQueryType.RECORD_QUERY_TYPE_NAME, value='harvestnet.org/agents/*')], limit=100)
        records = [MessageToDict(response.record.data, preserving_proto_field_name=True)
                   for response in self.client.search_records(request)]
        # Search returns records; exact current capacity/time is checked locally.
        return {'mode': self.mode, 'records': search_capability(latest_per_organization(records), **query)}


class DirectoryPublisher:
    """Keeps one organization's Directory record matching its own systems.

    ``refresh()`` re-reads the organization's systems and publishes a new record only
    when its capabilities changed (for example, a failed cooler drops cold space to
    zero), then removes the stale record. Native hosts call it periodically.
    """

    def __init__(self, directory, organization, endpoint, systems, clock=None):
        self.directory, self.organization, self.endpoint, self.systems = directory, organization, endpoint, systems
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.cid, self.published = None, None
        self.lock = threading.Lock()

    def refresh(self):
        with self.lock:
            current = capabilities(self.organization, self.systems)
            if current == self.published:
                return {'status': 'unchanged', 'cid': self.cid}
            cid = self.directory.register(record_for(self.organization, self.endpoint, self.systems, published_at=self.clock()))
            stale = self.cid if self.cid and self.cid != cid else None
            self.cid, self.published = cid, current
            if stale:
                try:
                    self.directory.unregister(stale)
                except Exception as exc:  # search still prefers the newest record
                    return {'status': 'published', 'cid': cid, 'stale_cid': stale, 'unregister_error': str(exc)}
            return {'status': 'published', 'cid': cid, 'replaced_cid': stale}

    def run_forever(self, interval_seconds, stop=None):
        stop = stop or threading.Event()
        while not stop.is_set():
            try:
                self.refresh()
            except Exception as exc:  # keep serving moves; report and retry next interval
                print(f'Directory refresh failed for {self.organization}: {exc}', flush=True)
            stop.wait(interval_seconds)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--register', action='store_true')
    parser.add_argument('--cold-lb', type=float, default=0)
    parser.add_argument('--pickup-at')
    args = parser.parse_args()
    endpoints = json.loads(os.environ['AGENT_ENDPOINTS'])
    systems = Systems(os.getenv('BEECEPTOR_BASE_URL'), os.getenv('COOLER_STATE_PATH'))
    endpoint = os.getenv('AGNTCY_DIRECTORY_ADDRESS')
    directory = AgntcyDirectory(endpoint) if endpoint else LocalDirectory(systems, endpoints)
    if args.register and endpoint:
        result = {'mode': directory.mode, 'records': {org: directory.register(record_for(org, endpoints[org], systems)) for org in ORGANIZATIONS}}
    else:
        result = directory.search(min_cold_lb=args.cold_lb, pickup_at=args.pickup_at)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
