"""Placeholder settings for `docker compose config` tests. Test values only, never real secrets."""
import json
import os

from harvestnet_platform.transport_auth import host_env
from test_transport import TEST_KEYS

STAFF = {'market': 'staff-market-x', 'city': 'staff-city-x', 'rural': 'staff-rural-x',
         'eastside': 'staff-eastside-x', 'advocate': 'staff-advocate-x'}
APPROVALS = 'approvals-placeholder-x'


def compose_env(**extra):
    """What deploy/load_secrets.py would write, with placeholder values."""
    return {'PATH': os.environ['PATH'], 'HOME': os.environ.get('HOME', '/tmp'), 'HARVESTNET_RELEASE': 'test',
            'API_EVENTS_TOKEN': 'events', 'DEMO_SWITCH_TOKEN': 'x', 'APPROVAL_PUBLIC_URL': 'https://example.invalid',
            'HARVESTNET_ALLOWED_ORIGIN': 'https://example.invalid', 'HARVESTNET_DOMAIN': 'example.invalid',
            'HARVESTNET_STAFF_TOKENS': json.dumps(STAFF), 'HARVESTNET_APPROVALS_TOKEN': APPROVALS,
            **{f'STAFF_TOKEN_{org.upper()}': token for org, token in STAFF.items()},
            **host_env(TEST_KEYS), **extra}
