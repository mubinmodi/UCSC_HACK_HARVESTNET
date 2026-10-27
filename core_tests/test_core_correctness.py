"""Regression tests for core correctness fixes (timezones, transactions, declines, audit checks,
API errors, purge, baselines). Each was written to fail before its fix. All data is synthetic."""
import copy
import json
import unittest
from datetime import timedelta, timezone
from pathlib import Path

from harvestnet_core.api import API
from harvestnet_core.engine import Engine, run_fixture
from harvestnet_core.protocol import dt
from harvestnet_core.records import Records


def load(name):
    return json.loads(Path('core_fixtures', name + '.json').read_text())


def utc(value):
    return dt(value).astimezone(timezone.utc)


def instants(window):
    return window and (dt(window['start']), dt(window['end']))


class RegionLocalTime(unittest.TestCase):
    """Household and pickup hours are the region's local clock, whatever offset the instant carries."""

    def setUp(self):
        self.f = load('normal-afternoon')
        self.engine = Engine(self.f)

    def test_same_instant_in_utc_or_local_gives_the_same_pickup(self):
        item = next(i for i in self.f['surplus_offers'][0]['items'] if i['produce_id'] == 'romaine')
        arrival = dt('2026-10-13T16:30:00-07:00')
        for bank in self.f['food_banks']:
            for request in self.engine.records.all('request'):
                with self.subTest(bank=bank['organization_id'], request=request['request_code']):
                    local = self.engine.eligible(request, bank, item, arrival)
                    from_utc = self.engine.eligible(request, bank, item, arrival.astimezone(timezone.utc))
                    self.assertEqual(instants(local), instants(from_utc))

    def test_fits_your_pickup_times_does_not_depend_on_the_clocks_offset(self):
        def fits(now):
            engine = Engine(self.f)
            api = API(engine, clock=lambda: now)
            out = {}
            for r in self.f['requests']:
                banks = api.call('GET', '/food-banks?request_code=' + r['request_code'])[1]['food_banks']
                out[r['request_code']] = {b['food_bank_id']: b['fits_your_pickup_times'] for b in banks}
            return out
        local = '2026-10-13T16:30:00-07:00'
        self.assertEqual(fits(local), fits(utc(local).isoformat()))

    def test_released_pickup_reassigns_the_same_way_under_a_utc_clock(self):
        def released(clock_in_utc):
            f = copy.deepcopy(self.f)
            f['household_replies'] = []
            records = Records()
            run_fixture(f, records=records)
            engine = Engine(f, records)
            # A Tuesday-evening household that asked after the plan was split, still below fair share.
            late = {**records.get('request', 'C4N6'), 'request_code': 'LATE1', 'received_this_week_lb': 0, 'initial_received_lb': 0,
                    'chosen_food_bank_ids': ['city'], 'pickup_windows': [{'days': ['tue'], 'start': '18:00', 'end': '20:00'}]}
            with records.transaction():
                records.put('request', 'LATE1', late)
            pickup = next(p for p in records.all('pickup') if p['request_code'] == 'C4N6')
            # 18:30 local on Tuesday is already Wednesday in UTC.
            now = (dt(pickup['window']['start']) + timedelta(minutes=30)).isoformat()
            api = API(engine, clock=lambda: utc(now).isoformat() if clock_in_utc else now)
            self.assertEqual(api.call('POST', f"/pickups/{pickup['pickup_id']}/release", {'request_code': 'C4N6'})[0], 200)
            return sorted((p['request_code'], p['pounds'], instants(p['window'])) for p in records.all('pickup') if p['status'] == 'committed')
        self.assertEqual(released(False), released(True))


if __name__ == '__main__':
    unittest.main()
