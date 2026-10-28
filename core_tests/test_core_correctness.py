"""Regression tests for core correctness fixes (timezones, transactions, declines, audit checks,
API errors, purge, baselines). Each was written to fail before its fix. All data is synthetic."""
import contextlib
import copy
import inspect
import json
import tempfile
import unittest
from datetime import timedelta, timezone
from pathlib import Path

from harvestnet_core.api import API
from harvestnet_core.engine import Engine, run_fixture
from harvestnet_core.protocol import Conflict, dt, named, terms_hash
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


def race(records, frame, other):
    """Run ``other`` (a second process on the same database) just before ``records`` opens the
    first transaction called from function ``frame``: after any read that came before it."""
    real, done = records.transaction, []

    @contextlib.contextmanager
    def transaction():
        if not done and any(f.function == frame for f in inspect.stack()[1:6]):
            done.append(True)
            other()
        with real() as txn:
            yield txn
    records.transaction = transaction


class ReadsInsideTransactions(unittest.TestCase):
    """Two processes share one database. A check made before the transaction is stale by the time it writes."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name, 'core.sqlite'))
        # More households than produce: a second split would still find households below fair share.
        self.f = load('more-households-than-produce')
        f = copy.deepcopy(self.f)
        f['household_replies'] = []
        records = Records(self.path)
        run_fixture(f, records=records)
        self.pickups = records.all('pickup')
        self.lot_id = self.f['surplus_offers'][0]['lot_id']
        self.received = records.get('request', 'K7P4')['received_this_week_lb']
        records.close()

    def tearDown(self):
        self.folder.cleanup()

    def test_two_processes_split_a_lot_once(self):
        records = Records(self.path)
        with records.transaction():
            for p in records.all('pickup'):
                records.delete('pickup', p['pickup_id'])
        first, second = Engine(self.f, records), Engine(self.f, Records(self.path))
        race(first.records, 'distribute', lambda: second.distribute(self.lot_id))
        first.distribute(self.lot_id)
        pickups = first.records.all('pickup')
        self.assertTrue(pickups)
        self.assertAlmostEqual(sum(p['pounds'] for p in pickups), sum(p['pounds'] for p in self.pickups))
        # The fixture run's notices plus exactly one more split.
        self.assertEqual(len(first.records.events_of_kind('pickup_notice')), 2 * len(self.pickups))

    def test_two_staff_confirming_at_once_count_the_pickup_once(self):
        pickup = next(p for p in self.pickups if p['request_code'] == 'K7P4')
        now = pickup['window']['start']
        body = {'food_bank_id': pickup['food_bank_id'], 'request_code': 'K7P4'}
        tokens = {pickup['food_bank_id']: 'staff'}
        first = API(Engine(self.f, Records(self.path)), clock=lambda: now, staff_tokens=tokens)
        second = API(Engine(self.f, Records(self.path)), clock=lambda: now, staff_tokens=tokens)
        race(first.records, 'op_confirm_pickup', lambda: self.assertEqual(second.call('POST', '/pickup-confirmations', body, token='staff')[0], 200))
        self.assertEqual(first.call('POST', '/pickup-confirmations', body, token='staff')[0], 409)
        self.assertEqual(first.records.get('request', 'K7P4')['received_this_week_lb'], self.received + pickup['pounds'])


class DeclinesAreFinal(unittest.TestCase):
    """A recorded decline is final for its version, on a lot and on a change of a committed lot."""

    def test_a_declined_lot_version_never_flips_to_approved(self):
        from test_core import fixture
        f = fixture()
        engine = Engine(f)
        api = API(engine, clock=lambda: '2026-10-13T12:00:00-07:00', staff_tokens={'market': 'donor-test', 'city': 'city-test'})
        lot_id = api.call('POST', '/surplus-offers', copy.deepcopy(f['surplus_offers'][0]), token='donor-test')[1]['lot_id']
        lot = engine.records.get('lot', lot_id)
        self.assertEqual(lot['status'], 'awaiting_approvals')
        draft, holds = lot['draft'], lot['holds']
        decide = lambda owner, decision: {'lot_id': lot_id, 'version': draft['version'], 'organization_id': owner,
                                          'terms_hash': terms_hash(draft), 'decision': decision}
        engine.protocol.approve(decide('city', 'decline'), 'city', engine.now, engine.validate)
        # Suppose the owners hold the same terms again: the decline still stands for this version.
        for owner in named(draft):
            engine.protocol.hold(lot_id, draft['version'], owner, holds[owner], engine.now, engine.capacities(owner, draft))
        for owner in ('market', 'city'):
            with self.subTest(owner=owner), self.assertRaises(Conflict):
                engine.protocol.approve(decide(owner, 'approve'), owner, engine.now, engine.validate)
        lot = engine.records.get('lot', lot_id)
        self.assertNotEqual(lot['status'], 'committed')
        self.assertEqual(lot['approvals']['city']['decision'], 'decline')

    def test_a_declined_change_is_kept_when_the_next_change_is_proposed(self):
        from harvestnet_core import changes
        from test_cooler_checks import run
        engine, lot_id, _ = run(answer_within_trip=False)
        declined = changes.changes_for(engine.records, lot_id)[-1]
        engine.now = '2026-10-13T15:31:00-07:00'  # inside the planned trip time
        receipt = {'lot_id': lot_id, 'version': declined['version'], 'organization_id': 'eastside',
                   'terms_hash': declined['terms_hash'], 'decision': 'decline'}
        self.assertEqual(changes.approve(engine, receipt, 'eastside')['status'], 'declined')
        self.assertEqual(changes.holding(engine, lot_id, 'city')['current_version'], declined['version'])
        # The same version number again would replace the declined record: refused.
        with self.assertRaises(Conflict):
            changes.propose(engine, lot_id, {'terms': declined['terms'], 'organizations': declined['organizations']}, 'city')
        terms = {**declined['terms'], 'version': declined['version'] + 1, 'based_on_version': declined['version']}
        proposed = changes.propose(engine, lot_id, {'terms': terms, 'organizations': declined['organizations']}, 'city')
        self.assertEqual(proposed['version'], declined['version'] + 1)
        kept = {c['version']: c['status'] for c in changes.changes_for(engine.records, lot_id)}
        self.assertEqual(kept, {declined['version']: 'declined', proposed['version']: 'awaiting_approvals'})


def two_lots():
    """Normal afternoon plus a second offer from the same donor that nobody can take (condition doubt)."""
    f = load('normal-afternoon')
    second = copy.deepcopy(f['surplus_offers'][0])
    second.update(lot_id='lot-market-1013-b')
    second['items'] = [{**second['items'][0], 'quantity': 10, 'condition_doubt': 'bruising reported'}]
    f['surplus_offers'].append(second)
    records = Records()
    return f, run_fixture(copy.deepcopy(f), records=records), records


class AuditChecks(unittest.TestCase):
    """The audit checks are as strong as their names."""

    def test_holds_on_another_lot_are_checked_against_their_owners_real_capacity(self):
        _, run, _ = two_lots()
        # The second lot names only the donor; the food banks' holds on the first lot still fit their storage.
        self.assertTrue(run['rule_checks']['no_double_booking'])
        self.assertTrue(run['rule_checks']['zero_invalid_commitments'])

    def test_fair_share_counts_the_households_whole_week(self):
        from harvestnet_core.checks import rule_checks
        f, run, records = two_lots()
        engine = Engine(f, records)
        lot_id = f['surplus_offers'][0]['lot_id']
        request = records.get('request', 'K7P4')
        # Another lot's pickup that, with this lot's, takes the household past its fair share.
        mine = sum(p['pounds'] for p in records.all('pickup') if p['request_code'] == 'K7P4' and p['status'] != 'released')
        extra = request['fair_share_lb'] - request.get('initial_received_lb', 0) - mine + 1
        with records.transaction():
            records.put('pickup', 'pk-other-1', {'pickup_id': 'pk-other-1', 'request_code': 'K7P4', 'lot_id': 'lot-market-1013-b', 'food_bank_id': 'city',
                                                 'pounds': extra, 'items': [{'produce_id': 'apples', 'pounds': extra}], 'status': 'committed'})
        pathways = engine.pathways(lot_id)
        self.assertFalse(rule_checks(records, lot_id, pathways, {})['fair_share_respected'])

    def test_invalid_commitments_counts_each_commitment_by_its_own_lot(self):
        from harvestnet_core.evaluation import metrics
        f, run, records = two_lots()
        self.assertEqual(metrics(f, run, records)['invalid_commitments'], 0)
        # Suppose only the second lot (which committed nothing) failed its checks.
        run['lot_rule_checks']['lot-market-1013-b']['zero_invalid_commitments'] = False
        run['rule_checks']['zero_invalid_commitments'] = False
        self.assertEqual(metrics(f, run, records)['invalid_commitments'], 0)
        run['lot_rule_checks']['lot-market-1013']['zero_invalid_commitments'] = False
        self.assertEqual(metrics(f, run, records)['invalid_commitments'], 1)


if __name__ == '__main__':
    unittest.main()
