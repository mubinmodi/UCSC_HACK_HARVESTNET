"""The core calculators behind Lane B's interface, the round counter, and API errors.

Every number is synthetic. No test calls the Claude API."""
from datetime import timedelta
from pathlib import Path
import unittest
from harvestnet_agents.calculators import CalculatorError as AgentsCalculatorError, StandInCalculators
from harvestnet_agents.profiles import UnitConversionError
from harvestnet_agents.rules_negotiators import rules_negotiator
from harvestnet_agents.scenario import load_scenario
from harvestnet_agents.scenario_runner import run_scenario
from harvestnet_core.api import API
from harvestnet_core.calculators import Calculators, CalculatorError
from harvestnet_core.engine import Engine, run_fixture
from harvestnet_core.protocol import dt
from harvestnet_core.records import Records
from test_core import fixture

CONTRACT_EXAMPLE = Path('docs/contracts/examples/scenario-normal-afternoon.json')


class BadInputNegotiator:
    """Asks a calculator for a produce with no profile, then never gets to move."""

    def __init__(self, calculators):
        self.calc = calculators

    def move(self, agent_input):
        self.calc.to_pounds('not-a-produce', 1, 'lb')


class CalculatorInterfaceTests(unittest.TestCase):
    def test_core_calculators_run_the_contract_scenario_end_to_end(self):
        run = run_scenario(load_scenario(CONTRACT_EXAMPLE), Calculators())
        self.assertEqual(run.status, 'committed')
        failed = {k: v.failures for k, v in run.lane_b_rule_checks.items() if not v.passed}
        self.assertEqual(failed, {})
        scenario = next(e for e in run.events if e['kind'] == 'scenario')
        self.assertEqual(scenario['calculators'], Calculators.label)
        self.assertEqual(scenario['compared_with'], StandInCalculators.label)
        self.assertEqual(run.calculator_differences, [])

    def test_bad_calculator_input_is_logged_by_the_runner_not_a_crash(self):
        def factory(role, org, calc):
            return BadInputNegotiator(calc) if org == 'advocate' else rules_negotiator(role, org, calc)
        run = run_scenario(load_scenario(CONTRACT_EXAMPLE), Calculators(), negotiator_factory=factory)
        errors = [e for e in run.events if e['kind'] == 'calculator_call' and e.get('error')]
        self.assertTrue(errors)
        self.assertTrue(all(e['error']['code'] == 'calculator_error' and e['actor'] == 'advocate' for e in errors))
        invalid = [e for e in run.events if e['kind'] == 'invalid_move' and e['organization_id'] == 'advocate']
        self.assertTrue(invalid)
        self.assertTrue(all('no produce profile' in e['problem'] for e in invalid))

    def test_adjust_pounds_takes_negative_changes_and_never_goes_below_zero(self):
        calc = Calculators()
        self.assertEqual(calc.adjust_pounds(10, -4), 6)
        self.assertEqual(calc.adjust_pounds(10, -40), 0)
        self.assertEqual(calc.adjust_pounds(10, 5), 15)
        for current, change in ((-1, 0), (10, float('nan')), (10, True), (1e308, 1e308)):
            with self.assertRaises(AgentsCalculatorError):
                calc.adjust_pounds(current, change)

    def test_capacity_fit_treats_negative_free_space_as_none_like_the_stand_in(self):
        core, stand_in = Calculators().capacity_fit(-5, 3), StandInCalculators().capacity_fit(-5, 3)
        self.assertEqual(core, stand_in)
        self.assertFalse(core.fits)
        self.assertEqual(core.over_by_lb, 3)

    def test_bad_inputs_raise_lane_b_calculator_errors_that_old_callers_still_catch(self):
        calc = Calculators()
        cases = [
            (lambda: calc.fair_share(0), ValueError),
            (lambda: calc.gap_after_plan(-1, 0), ValueError),
            (lambda: calc.capacity_fit(10, -1), ValueError),
            (lambda: calc.to_pounds('not-a-produce', 1, 'lb'), KeyError),
            (lambda: calc.to_pounds('romaine', 1, 'not-a-unit'), UnitConversionError),
        ]
        for call, old in cases:
            with self.assertRaises(AgentsCalculatorError):
                call()
            with self.assertRaises(CalculatorError):
                call()
            with self.assertRaises(old):
                call()


def counter_once_provider(produce_id):
    """City counters once in round 1; every other move is a pass."""
    def provider(org, wire):
        move = {'organization_id': org, 'version': wire['draft']['version'], 'reason': 'synthetic test move'}
        if org == 'city' and wire['turn_context']['number'] == 2:
            return {**move, 'action': 'counter', 'amendment': {'kind': 'set_pounds', 'food_bank_id': 'city', 'produce_id': produce_id, 'pounds': 1}}
        return {**move, 'action': 'pass'}
    return provider


class StopRuleTests(unittest.TestCase):
    def run_with_limit(self, limit):
        f = fixture()
        f['humans'] = []
        f['policies']['rounds_without_new_terms_before_disagreement'] = limit
        records = Records()
        run_fixture(f, counter_once_provider(f['surplus_offers'][0]['items'][0]['produce_id']), records=records)
        lot_id = f['surplus_offers'][0]['lot_id']
        moves = [e for e in records.events(lot_id) if e['kind'] == 'move']
        return len(moves), len(f['turn_order']), records.get('lot', lot_id)

    def test_a_round_with_a_counter_does_not_count_toward_the_stop_rule(self):
        for limit in (3, 2):
            moves, per_round, lot = self.run_with_limit(limit)
            # Round 1 had the counter, then `limit` rounds with no new terms.
            self.assertEqual(moves, (1 + limit) * per_round)
            self.assertEqual(lot['status'], 'preserved_disagreement')
            self.assertTrue(lot['stop_reason'].startswith(f'{limit} rounds without new terms'))


class ApiErrorTests(unittest.TestCase):
    def test_condition_check_on_produce_not_in_the_lot_is_a_400_not_a_dropped_connection(self):
        f = fixture()
        f['humans'] = []
        records = Records()
        run_fixture(f, records=records)
        lot = records.all('lot')[0]
        d = lot['draft']
        engine = Engine(f, records)
        now = (dt(f['surplus_offers'][0]['reported_at']) + timedelta(minutes=5)).isoformat()
        api = API(engine, clock=lambda: now, staff_tokens={'market': 'synthetic-market-token', 'city': 'synthetic-city-token'})
        body = {'version': d['version'], 'organization_id': 'market', 'produce_id': 'not-in-this-lot', 'condition_grade': 'good',
                'usable_until': (dt(now) + timedelta(days=1)).isoformat(), 'reason': 'synthetic check'}
        status, data = api.call('POST', f"/lots/{d['lot_id']}/condition-checks", body, 'synthetic-market-token')
        self.assertEqual(status, 400)
        self.assertEqual(data['error']['code'], 'bad_request')
        self.assertIn('not-in-this-lot', data['error']['message'])
        self.assertEqual(records.get('lot', d['lot_id'])['draft']['version'], d['version'])


if __name__ == '__main__':
    unittest.main()
