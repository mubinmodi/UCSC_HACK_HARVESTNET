"""ADR 0013 in the core: food banks contest each other's shares and concede toward need.

The core checks every counter's shape by owner (a food bank changes only its own share, or
shifts one item from one other food bank to itself), hands every negotiator the claims stated in
the lot's records, and gives the advocate the contests. With the rules everywhere, a scarce lot
converges on a proportional split and commits. A side that refuses the split makes the terms
repeat, which stops as a preserved disagreement. All data is synthetic.
"""
import copy
import json
import unittest
from pathlib import Path

from harvestnet_agents.calculators import StandInCalculators, split_in_proportion
from harvestnet_agents.negotiation import parse_agent_input
from harvestnet_agents.rules_negotiators import RulesFoodBank, rules_negotiator
from harvestnet_core.api import API
from harvestnet_core.calculators import Calculators
from harvestnet_core.engine import Engine, run_fixture
from harvestnet_core.records import Records

SCARCE = json.loads(Path('core_fixtures/more-households-than-produce.json').read_text(encoding='utf-8'))
LOT = SCARCE['surplus_offers'][0]['lot_id']


def moves(records):
    return [e['data'] for e in records.events(LOT) if e['kind'] == 'move']


class ConcedeTowardNeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = Records()
        cls.result = run_fixture(copy.deepcopy(SCARCE), records=cls.records)
        cls.lot = cls.records.get('lot', LOT)
        cls.moves = moves(cls.records)

    @classmethod
    def tearDownClass(cls):
        cls.records.close()

    def test_a_scarce_lot_converges_on_a_proportional_split_and_commits(self):
        self.assertEqual(self.lot['status'], 'committed')
        potatoes = {a['food_bank_id']: a['pounds'] for a in self.lot['draft']['allocations'] if a['produce_id'] == 'potatoes'}
        gaps = {'city': 31, 'rural': 32, 'eastside': 19}  # the fixture's synthetic fair-share gaps
        self.assertEqual(potatoes, split_in_proportion(potatoes, gaps).shares_lb)

    def test_contests_take_backs_and_the_advocates_side_are_in_the_record_with_their_claims(self):
        claims = [m for m in self.moves if (m.get('amendment') or {}).get('to_food_bank_id') == m['organization_id']]
        self.assertTrue(any('We contest' in m['reason'] for m in claims))
        self.assertTrue(any('We take back' in m['reason'] for m in claims))
        self.assertTrue(all(m['amendment'].get('claimant_gap_lb') is not None for m in claims))
        self.assertTrue(any(m['organization_id'] == 'advocate' and 'restores the proportional split' in m['reason'] for m in self.moves))

    def test_rule_checks_still_pass(self):
        self.assertTrue(all(self.result['rule_checks'].values()), self.result['rule_checks'])


class Insisting(RulesFoodBank):
    """Refuses the proportional split: always claims its whole gap (as an LLM or a staff counter might)."""

    def _short_of_share(self, split, facts, held):
        return facts.demand.below_fair_share_lb


class StandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        negotiators = {}

        def provider(org, wire):
            role, typed = parse_agent_input({**wire, 'turn': wire['turn_context']})
            if org not in negotiators:
                negotiators[org] = Insisting(org, calc) if org == 'rural' else rules_negotiator(role, org, calc)
            return negotiators[org].move(typed).to_dict()

        calc = Calculators()
        cls.records = Records()
        run_fixture(copy.deepcopy(SCARCE), provider, records=cls.records, calculators=calc)
        cls.lot = cls.records.get('lot', LOT)

    @classmethod
    def tearDownClass(cls):
        cls.records.close()

    def test_a_side_that_refuses_the_split_ends_in_a_preserved_disagreement(self):
        self.assertEqual(self.lot['status'], 'preserved_disagreement')
        self.assertIn('going round in a cycle', self.lot['stop_reason'])
        self.assertEqual(self.lot['commitments'], [])
        self.assertLess(len(moves(self.records)), 200)  # stopped by the cycle, not the turn limit

    def test_the_dashboards_show_the_competing_versions_and_each_food_banks_reason(self):
        engine = Engine(SCARCE, records=self.records)
        view = API(engine, clock=lambda: '2026-10-13T13:00:00-07:00').disagreement_view(self.lot)
        self.assertGreaterEqual(len(view['options']), 2)
        self.assertTrue(all(o['reason'] for o in view['options']))
        self.assertIn('rural', {r['organization_id'] for r in view['reasons']})


class OwnerAmendmentShapeTests(unittest.TestCase):
    def setUp(self):
        self.protocol = Engine(SCARCE).protocol

    def test_a_contest_to_the_proposer_is_accepted(self):
        self.protocol.check_owner_amendment('city', {'kind': 'shift_pounds', 'produce_id': 'potatoes', 'from_food_bank_id': 'rural',
                                                     'to_food_bank_id': 'city', 'pounds': 5.0, 'claimant_gap_lb': 31.0})

    def test_setting_another_food_banks_share_or_shifting_between_two_others_is_refused(self):
        with self.assertRaises(ValueError):
            self.protocol.check_owner_amendment('city', {'kind': 'set_pounds', 'produce_id': 'potatoes', 'food_bank_id': 'rural', 'pounds': 0.0})
        with self.assertRaises(ValueError):
            self.protocol.check_owner_amendment('city', {'kind': 'shift_pounds', 'produce_id': 'potatoes', 'from_food_bank_id': 'rural',
                                                         'to_food_bank_id': 'eastside', 'pounds': 5.0})

    def test_the_donor_and_advocate_are_not_held_to_the_food_bank_shape(self):
        shift = {'kind': 'shift_pounds', 'produce_id': 'potatoes', 'from_food_bank_id': 'rural', 'to_food_bank_id': 'eastside', 'pounds': 5.0}
        self.protocol.check_owner_amendment('advocate', shift)


class ProportionalSplitCalculatorTests(unittest.TestCase):
    def test_the_core_and_the_stand_ins_give_the_same_split(self):
        held, gaps = {'city': 100, 'rural': 150}, {'city': 300, 'rural': 640}
        self.assertEqual(Calculators().proportional_split(held, gaps), StandInCalculators().proportional_split(held, gaps))

    def test_the_core_refuses_negative_or_non_finite_pounds(self):
        with self.assertRaises(ValueError):
            Calculators().proportional_split({'a': -1}, {'a': 1})
        with self.assertRaises(ValueError):
            Calculators().proportional_split({'a': float('nan')}, {'a': 1})


if __name__ == '__main__':
    unittest.main()
