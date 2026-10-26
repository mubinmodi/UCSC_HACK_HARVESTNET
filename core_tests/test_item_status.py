"""get_lot reports each item's own status (contract: offered, negotiating, held, committed,
moving, at the food bank, collected, unclaimed), derived from the records, not the lot's."""
import copy
import json
from pathlib import Path
import unittest
from harvestnet_core.api import API
from harvestnet_core.engine import Engine
from harvestnet_core.protocol import named, terms_hash

from test_core import fixture

ORGS = ('market', 'city', 'rural', 'eastside')
TOKENS = {o: o + '-token' for o in ORGS}


class ItemStatus(unittest.TestCase):
    def setUp(self):
        self.f = json.loads(Path('core_fixtures/normal-afternoon.json').read_text())
        self.engine = Engine(self.f)
        self.clock = {'now': '2026-10-13T12:00:00-07:00'}
        self.api = API(self.engine, clock=lambda: self.clock['now'], staff_tokens=TOKENS)
        status, created = self.api.call('POST', '/surplus-offers', copy.deepcopy(self.f['surplus_offers'][0]), token=TOKENS['market'])
        self.assertEqual(status, 201, created)
        self.lot_id = created['lot_id']

    def statuses(self):
        status, lot = self.api.call('GET', '/lots/' + self.lot_id)
        self.assertEqual(status, 200)
        return {i['produce_id']: i['status'] for i in lot['items']}

    def commit(self):
        draft = self.engine.records.get('lot', self.lot_id)['draft']
        for org in named(draft):
            receipt = {'lot_id': self.lot_id, 'version': draft['version'], 'organization_id': org, 'terms_hash': terms_hash(draft),
                       'decision': 'approve', 'receipt_id': 'r-' + org}
            self.assertEqual(self.api.call('POST', '/approvals', receipt, token=TOKENS[org])[0], 200)
        self.assertEqual(self.engine.records.get('lot', self.lot_id)['status'], 'committed')

    def test_items_are_held_once_their_owners_holds_are_placed(self):
        self.assertEqual(self.engine.records.get('lot', self.lot_id)['status'], 'awaiting_approvals')
        self.assertEqual(set(self.statuses().values()), {'held'})

    def test_items_follow_the_commitment_and_their_own_transport(self):
        self.commit()
        self.assertEqual(set(self.statuses().values()), {'committed'})
        # Donor drops off 1:00-1:40 pm (rural), 1:00-1:25 pm (eastside); the city truck leaves 3:00 pm.
        self.clock['now'] = '2026-10-13T13:30:00-07:00'
        self.assertEqual(self.statuses(), {'apples': 'moving', 'romaine': 'committed', 'potatoes': 'moving'})
        self.clock['now'] = '2026-10-13T13:45:00-07:00'
        self.assertEqual(self.statuses(), {'apples': 'moving', 'romaine': 'committed', 'potatoes': 'at_food_bank'})
        self.clock['now'] = '2026-10-13T15:10:00-07:00'
        self.assertEqual(self.statuses(), {'apples': 'moving', 'romaine': 'moving', 'potatoes': 'at_food_bank'})
        self.clock['now'] = '2026-10-13T15:30:00-07:00'
        self.assertEqual(set(self.statuses().values()), {'at_food_bank'})

    def test_an_item_every_household_collected_is_collected(self):
        self.commit()
        self.clock['now'] = '2026-10-13T15:30:00-07:00'
        for p in self.engine.records.all('pickup'):
            if p['items'][0]['produce_id'] == 'apples':
                self.engine.records.put('pickup', p['pickup_id'], {**p, 'status': 'collected'})
        statuses = self.statuses()
        self.assertEqual(statuses['apples'], 'collected')
        self.assertEqual(statuses['romaine'], 'at_food_bank')  # its households have not collected yet
        self.assertEqual(statuses['potatoes'], 'at_food_bank')  # no household portion was planned

    def test_a_lot_nobody_claimed_by_the_deadline_has_unclaimed_items_with_a_reason(self):
        f = fixture()
        engine = Engine(f)
        api = API(engine, clock=lambda: '2026-10-13T12:00:00-07:00', staff_tokens={'market': 'm'})
        engine.create_offer({**copy.deepcopy(f['surplus_offers'][0]), 'lot_id': 'lot-quiet'})
        lot = api.call('GET', '/lots/lot-quiet')[1]
        self.assertEqual([i['status'] for i in lot['items']], ['offered'])  # published, no food bank has answered yet
        record = engine.records.get('lot', 'lot-quiet')
        record.update(status='unclaimed', stop_reason='Deadline passed without every exact-version approval; nothing auto-committed')
        engine.records.put('lot', 'lot-quiet', record)
        item = api.call('GET', '/lots/lot-quiet')[1]['items'][0]
        self.assertEqual(item['status'], 'unclaimed')
        self.assertGreater(item['unclaimed_lb'], 0)
        self.assertIn('Deadline passed', item['unclaimed_reason'])

    def test_an_item_with_planned_pounds_but_no_holds_is_negotiating(self):
        f = fixture()
        engine = Engine(f)
        api = API(engine, clock=lambda: '2026-10-13T12:00:00-07:00', staff_tokens={'market': 'm'})
        engine.create_offer({**copy.deepcopy(f['surplus_offers'][0]), 'lot_id': 'lot-busy'})
        engine.protocol.amend('lot-busy', 1, 'city', {'kind': 'set_pounds', 'produce_id': 'apples', 'food_bank_id': 'city', 'pounds': 2}, 'We can take some', engine.now)
        self.assertEqual(api.call('GET', '/lots/lot-busy')[1]['items'][0]['status'], 'negotiating')

    def test_a_preserved_disagreement_marks_every_item_as_a_disagreement(self):
        f = fixture()
        for slot in f['food_banks'][0]['storage']:
            slot['dry_free_lb'] = slot['cold_free_lb'] = 0
        engine = Engine(f)
        api = API(engine, clock=lambda: '2026-10-13T12:00:00-07:00', staff_tokens={'market': 'm', 'city': 'c'})
        lot_id = api.call('POST', '/surplus-offers', copy.deepcopy(f['surplus_offers'][0]), token='m')[1]['lot_id']
        lot = api.call('GET', '/lots/' + lot_id)[1]
        self.assertEqual(lot['status'], 'preserved_disagreement')
        self.assertEqual({i['status'] for i in lot['items']}, {'disagreement'})


class ChangedItemStatus(unittest.TestCase):
    def test_produce_a_cooler_failure_change_moved_follows_the_changes_own_trip(self):
        from harvestnet_core import changes
        from harvestnet_core.engine import run_fixture
        from harvestnet_core.records import Records
        fixture = json.loads(Path('core_fixtures/cooler-failure.json').read_text())
        for human in fixture['humans']:
            human['after_minutes'] = 1  # inside the planned trip time, so the change commits
        records = Records()
        run_fixture(copy.deepcopy(fixture), records=records)
        lot_id = records.all('lot')[0]['draft']['lot_id']
        move = changes.changes_for(records, lot_id)[-1]['terms']['moves'][0]
        clock = {'now': move['departs_at']}
        api = API(Engine(fixture, records), clock=lambda: clock['now'], staff_tokens={})
        status = lambda: {i['produce_id']: i['status'] for i in api.call('GET', '/lots/' + lot_id)[1]['items']}
        self.assertEqual(status()['romaine'], 'moving')  # the change's truck run has left, the city's other romaine is where it was
        clock['now'] = move['arrives_at']
        self.assertEqual(status()['romaine'], 'at_food_bank')


if __name__ == '__main__':
    unittest.main()
