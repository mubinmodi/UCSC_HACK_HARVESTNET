"""Ticket #20, the join: every scenario fixture through the harness with the real agents.

Lane A's harness runs each fixture with Lane B's rules-based negotiators and Lane A's
real calculators. One run gives both rule-check sets: the fixture's own (Lane A's) and
Lane B's six, read from a Lane B event log built from that same harness run. Every
calculator call is compared with the stand-ins, and each difference is explained.

Every number is synthetic. No test calls the Claude API or the network."""
import copy
import json
from pathlib import Path
import unittest

from harvestnet_agents.calculators import StandInCalculators
from harvestnet_agents.lane_b_rule_checks import LANE_B_RULE_CHECKS
from harvestnet_agents.scenario import load_scenario
from harvestnet_core.calculators import Calculators
from harvestnet_core.join import (
    FIXTURE_PATHS,
    LANE_A_RULE_CHECKS,
    ROOT,
    STAND_IN_DIFFERENCES,
    load_fixture,
    run_join,
)

CONTRACT_EXAMPLE = Path('docs/contracts/examples/scenario-normal-afternoon.json')


def failures(checks):
    return {name: c['failures'] for name, c in checks.items() if not c['passed']}


class EveryFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {p.relative_to(ROOT).as_posix(): run_join(load_fixture(p)) for p in FIXTURE_PATHS}

    def test_the_join_covers_the_contract_example_and_all_of_lane_as_fixtures(self):
        self.assertIn(str(CONTRACT_EXAMPLE), self.runs)
        core = sorted(str(p) for p in Path('core_fixtures').glob('*.json'))
        self.assertEqual(len(core), 5)
        self.assertTrue(set(core) <= set(self.runs))

    def test_lane_as_fixtures_load_through_the_contract_loader_unchanged(self):
        for path in FIXTURE_PATHS:
            raw = json.loads(Path(path).read_text())
            self.assertEqual(raw['contract_version'], 'contract-v0.1')
            self.assertEqual(load_fixture(path), raw)
            load_scenario(raw)  # Lane B's contract loader accepts it as is

    def test_every_fixture_runs_with_the_real_rules_based_negotiators(self):
        for path, run in self.runs.items():
            with self.subTest(path):
                self.assertEqual(run.harness['policy_label'], 'real rules-based negotiators')
                moves = [e for e in run.events if e['kind'] == 'move']
                self.assertTrue(moves)
                self.assertEqual({e['negotiator'] for e in moves}, {'rules'})
                self.assertEqual(set(run.lane_b_runner['negotiators'].values()), {'rules'})

    def test_every_fixture_uses_lane_as_real_calculators_not_the_stand_ins(self):
        for path, run in self.runs.items():
            with self.subTest(path):
                scenario = run.events[0]
                self.assertEqual(scenario['kind'], 'scenario')
                self.assertEqual(scenario['calculators'], Calculators.label)
                self.assertEqual(scenario['compared_with'], StandInCalculators.label)
                self.assertEqual(run.harness['calculator_label'], Calculators.label)
                self.assertEqual(run.lane_b_runner['calculators'], Calculators.label)

    def test_every_rule_check_passes_on_every_fixture_and_none_is_pending(self):
        for path, run in self.runs.items():
            with self.subTest(path):
                raw = load_fixture(path)
                self.assertEqual(set(run.rule_checks), set(raw['rule_checks']) | set(LANE_B_RULE_CHECKS))
                self.assertEqual(failures(run.rule_checks), {})
                self.assertEqual(failures(run.lane_b_runner['rule_checks']), {})
                self.assertTrue(run.passed)
                for name, check in {**run.rule_checks, **run.lane_b_runner['rule_checks']}.items():
                    self.assertIs(check['passed'], True, name)
                    self.assertNotIn('pending', json.dumps(check).lower(), name)
                self.assertEqual(run.harness['rule_checks'], {n: True for n in LANE_A_RULE_CHECKS})

    def test_version_one_lists_the_donors_own_drop_off_route(self):
        for path, run in self.runs.items():
            with self.subTest(path):
                raw = load_fixture(path)
                for offer in raw['surplus_offers']:
                    donor = next(d for d in raw['donors'] if d['organization_id'] == offer['donor_id'])
                    v1 = next(e for e in run.events if e['kind'] == 'version' and e['lot_id'] == offer['lot_id'] and e['version'] == 1)
                    drop = donor.get('drop_off')
                    self.assertEqual(v1['terms']['drop_off_to'], list(drop['food_bank_ids']) if drop else [])
                    self.assertEqual(v1['terms']['drop_off_refrigerated'], bool(drop and drop['refrigerated']))

    def test_both_check_sets_are_read_from_the_same_harness_run(self):
        for path, run in self.runs.items():
            with self.subTest(path):
                sources = {c['source'] for c in run.rule_checks.values()}
                self.assertEqual(sources, {'lane_a_harness_records', 'lane_b_checks_over_harness_log'})
                commitments = [e for e in run.events if e['kind'] == 'commitment']
                self.assertEqual(len(commitments), len({(c['lot_id'], c['version']) for c in commitments}))
                committed = sorted((c['food_bank_id'], c['produce_id'], c['pounds']) for c in run.harness['commitments'])
                logged = [] if not commitments else sorted(
                    (a['food_bank_id'], a['produce_id'], a['pounds'])
                    for a in commitments[0]['allocations'])
                self.assertEqual(committed, logged)

    def test_every_calculator_call_is_compared_with_the_stand_ins_and_none_differ(self):
        for path, run in self.runs.items():
            with self.subTest(path):
                calls = [e for e in run.events if e['kind'] == 'calculator_call']
                self.assertTrue(calls)
                self.assertTrue(all('difference_from_stand_in' in e for e in calls))
                compared = [e for e in calls if not e.get('not_compared') and not e.get('error')]
                self.assertTrue(compared)
                not_compared = {e['calculator'] for e in calls if e.get('not_compared')}
                self.assertTrue(not_compared <= {'fair_share', 'household_portions'})
                self.assertEqual(run.calculator_differences, [])
                self.assertEqual(run.lane_b_runner['calculator_differences'], [])

    def test_without_a_fault_the_harness_and_lane_bs_runner_commit_the_same_terms(self):
        for path, run in self.runs.items():
            if load_fixture(path)['faults']:
                continue
            with self.subTest(path):
                self.assertTrue(run.lane_b_runner['same_commitment_as_harness'], (
                    run.harness['commitments'], run.lane_b_runner['committed_allocations']))

    def test_with_a_known_cooler_failure_the_harness_forecasts_it_and_lane_bs_runner_reacts_to_it(self):
        # The one remaining difference between the two runs, by design on each side: Lane A's
        # harness treats a scripted fault as known and gives the failing cooler no cold space
        # from the start; Lane B's runner lets the fault happen at its time and runs #15.
        profiles = Calculators().profiles
        for path, run in self.runs.items():
            raw = load_fixture(path)
            if not raw['faults']:
                continue
            with self.subTest(path):
                failing = raw['faults'][0]['food_bank_id']
                cold_to_failing = [c for c in run.harness['commitments']
                                   if c['food_bank_id'] == failing and profiles.get(c['produce_id']).needs_cold]
                self.assertEqual(cold_to_failing, [])
                self.assertFalse(run.lane_b_runner['same_commitment_as_harness'])
                [assessment] = run.lane_b_runner['cooler_failure_assessments']
                self.assertEqual(assessment['food_bank_id'], failing)
                self.assertFalse(assessment['proposal']['committed'])

    def test_a_fixture_that_asks_for_a_check_lane_a_lacks_reports_it_not_run_and_failed(self):
        raw = load_fixture(CONTRACT_EXAMPLE)
        raw['rule_checks'] = raw['rule_checks'] + ['not_a_real_check']
        run = run_join(raw)
        self.assertFalse(run.rule_checks['not_a_real_check']['passed'])
        self.assertEqual(run.rule_checks['not_a_real_check']['source'], 'not_run')
        self.assertFalse(run.passed)
        self.assertEqual(set(LANE_A_RULE_CHECKS) & {'not_a_real_check'}, set())


class DifferenceTests(unittest.TestCase):
    def test_the_recorder_logs_fair_share_and_household_portions_in_the_contracts_shape(self):
        from datetime import datetime
        from harvestnet_agents.scenario_runner import EventLog
        from harvestnet_core.join import recorded_core_calculators
        log = EventLog()
        calc = recorded_core_calculators(log, lambda: datetime.fromisoformat('2026-10-13T12:00:00-07:00'))
        examples = json.loads(Path('docs/contracts/examples/calculators.json').read_text())['examples']
        covered = [e for e in examples if e['calculator'] in ('fair_share', 'household_portions')]
        self.assertEqual(len(covered), 4)
        for ex in covered:
            getattr(calc, ex['calculator'])(*ex['input'].values())
            logged = log.events[-1]
            self.assertEqual(logged['input'], ex['input'], ex['name'])
            self.assertEqual(logged['output'], ex['output'], ex['name'])
            self.assertIsNone(logged['difference_from_stand_in'])
            self.assertIn('no ' + ex['calculator'], logged['not_compared'])

    def test_overlapping_storage_readings_differ_from_the_stand_in_and_the_log_says_why(self):
        raw = load_fixture('core_fixtures/normal-afternoon.json')
        city = next(b for b in raw['food_banks'] if b['organization_id'] == 'city')
        # A second, overlapping synthetic reading with less cold space.
        city['storage'].append({**copy.deepcopy(city['storage'][0]), 'cold_free_lb': city['storage'][0]['cold_free_lb'] - 50})
        run = run_join(raw)
        diffs = run.calculator_differences
        self.assertTrue(diffs)
        self.assertEqual({d['calculator'] for d in diffs}, {'storage_at'})
        d = diffs[0]['difference_from_stand_in']
        self.assertEqual(d['fields'], ['cold_free_lb'])
        self.assertLess(d['output']['cold_free_lb'], d['stand_in_output']['cold_free_lb'])
        self.assertIn(STAND_IN_DIFFERENCES['storage_at'], d['explanation'])
        self.assertEqual(failures(run.rule_checks), {})


class TamperTests(unittest.TestCase):
    """Lane B's checks over the harness log really check it: break one rule, see it fail."""

    @classmethod
    def setUpClass(cls):
        cls.joined = run_join(load_fixture('core_fixtures/normal-afternoon.json'))

    def recheck(self, events):
        from harvestnet_agents.lane_b_rule_checks import run_lane_b_rule_checks
        return run_lane_b_rule_checks(events, Calculators().profiles)

    def test_a_move_from_another_organizations_facts_fails_no_central_decider(self):
        events = copy.deepcopy(self.joined.events)
        move = next(e for e in events if e['kind'] == 'move' and e['role'] == 'food_bank')
        move['facts']['food_bank_id'] = 'someone-else'
        self.assertFalse(self.recheck(events)['no_central_decider'].passed)

    def test_a_missing_approval_fails_commits_only_with_every_named_approval(self):
        events = copy.deepcopy(self.joined.events)
        approval = next(e for e in events if e['kind'] == 'approval')
        events.remove(approval)
        self.assertFalse(self.recheck(events)['commits_only_with_every_named_approval'].passed)

    def test_an_invented_number_in_a_reason_fails_numbers_trace_to_inputs(self):
        events = copy.deepcopy(self.joined.events)
        move = next(e for e in events if e['kind'] == 'move')
        move['move']['reason'] += ' We can take 987654 lb.'
        self.assertFalse(self.recheck(events)['numbers_trace_to_inputs'].passed)


if __name__ == '__main__':
    unittest.main()
