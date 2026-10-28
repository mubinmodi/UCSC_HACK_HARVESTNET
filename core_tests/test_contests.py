"""ADR 0013 in the core: food banks contest each other's shares, and a standoff is kept.

The core checks every counter's shape by owner (a food bank changes only its own share, or
shifts one item from one other food bank to itself), gives the advocate the contests in the
shared records, and stops a contest and take-back that repeat the same terms as a preserved
disagreement. All data is synthetic.
"""
import copy
import json
import unittest
from pathlib import Path

from harvestnet_core.api import API
from harvestnet_core.engine import Engine, run_fixture
from harvestnet_core.records import Records

SCARCE = json.loads(Path('core_fixtures/more-households-than-produce.json').read_text(encoding='utf-8'))


class ContestStandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = Records()
        cls.result = run_fixture(copy.deepcopy(SCARCE), records=cls.records)
        cls.lot_id = SCARCE['surplus_offers'][0]['lot_id']
        cls.lot = cls.records.get('lot', cls.lot_id)
        cls.moves = [e['data'] for e in cls.records.events(cls.lot_id) if e['kind'] == 'move']

    @classmethod
    def tearDownClass(cls):
        cls.records.close()

    def test_the_standoff_ends_as_a_preserved_disagreement_and_nothing_commits(self):
        self.assertEqual(self.lot['status'], 'preserved_disagreement')
        self.assertIn('going round in a cycle', self.lot['stop_reason'])
        self.assertEqual(self.lot['commitments'], [])
        self.assertLess(len(self.moves), 200)  # stopped by the cycle, not the turn limit

    def test_contests_take_backs_and_the_advocates_side_are_in_the_record(self):
        reasons = [m['reason'] for m in self.moves]
        self.assertTrue(any('We contest' in r for r in reasons))
        self.assertTrue(any('We take back' in r for r in reasons))
        self.assertTrue(any(m['organization_id'] == 'advocate' and 'we back' in m['reason'] for m in self.moves))

    def test_the_dashboards_show_both_versions_and_both_food_banks_reasons(self):
        engine = Engine(SCARCE, records=self.records)
        view = API(engine, clock=lambda: '2026-10-13T13:00:00-07:00').disagreement_view(self.lot)
        self.assertGreaterEqual(len(view['options']), 2)
        self.assertTrue(all(o['reason'] for o in view['options']))
        self.assertLessEqual({'city', 'rural'}, {r['organization_id'] for r in view['reasons']})

    def test_rule_checks_still_pass(self):
        self.assertTrue(all(self.result['rule_checks'].values()), self.result['rule_checks'])


class OwnerAmendmentShapeTests(unittest.TestCase):
    def setUp(self):
        self.protocol = Engine(SCARCE).protocol

    def test_a_contest_to_the_proposer_is_accepted(self):
        self.protocol.check_owner_amendment('city', {'kind': 'shift_pounds', 'produce_id': 'potatoes', 'from_food_bank_id': 'rural',
                                                     'to_food_bank_id': 'city', 'pounds': 5.0})

    def test_setting_another_food_banks_share_or_shifting_between_two_others_is_refused(self):
        with self.assertRaises(ValueError):
            self.protocol.check_owner_amendment('city', {'kind': 'set_pounds', 'produce_id': 'potatoes', 'food_bank_id': 'rural', 'pounds': 0.0})
        with self.assertRaises(ValueError):
            self.protocol.check_owner_amendment('city', {'kind': 'shift_pounds', 'produce_id': 'potatoes', 'from_food_bank_id': 'rural',
                                                         'to_food_bank_id': 'eastside', 'pounds': 5.0})

    def test_the_donor_and_advocate_are_not_held_to_the_food_bank_shape(self):
        shift = {'kind': 'shift_pounds', 'produce_id': 'potatoes', 'from_food_bank_id': 'rural', 'to_food_bank_id': 'eastside', 'pounds': 5.0}
        self.protocol.check_owner_amendment('advocate', shift)


if __name__ == '__main__':
    unittest.main()
