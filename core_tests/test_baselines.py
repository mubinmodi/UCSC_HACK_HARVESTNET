"""Design section 16: first-come-first-served means the first food bank to claim gets the whole lot."""
import copy
import json
from pathlib import Path
import unittest
from harvestnet_core.engine import run_fixture
from harvestnet_core.evaluation import Baseline, evaluate
from harvestnet_core.records import Records


def load(name):
    return json.loads(Path('core_fixtures', name + '.json').read_text())


def run(fixture, method):
    records = Records()
    provider = Baseline(fixture, method) if method != 'rules_based' else None
    result = run_fixture(copy.deepcopy(fixture), provider, records=records)
    return result, records


def banks_by_item(result):
    by_item = {}
    for c in result['commitments']:
        if c['pounds'] > 0:
            by_item.setdefault(c['produce_id'], set()).add(c['food_bank_id'])
    return by_item


class FirstComeFirstServed(unittest.TestCase):
    def test_every_item_goes_to_one_food_bank_only(self):
        fixture = load('normal-afternoon')
        fcfs, _ = run(fixture, 'first_come_first_served')
        self.assertTrue(fcfs['commitments'])
        self.assertTrue(all(len(banks) == 1 for banks in banks_by_item(fcfs).values()), banks_by_item(fcfs))
        # The rules-based negotiators do share an item between food banks, so this is a real difference.
        rules, _ = run(fixture, 'rules_based')
        self.assertTrue(any(len(banks) > 1 for banks in banks_by_item(rules).values()))

    def test_it_still_obeys_every_rule_the_harness_enforces(self):
        for path in sorted(Path('core_fixtures').glob('*.json')):
            fixture = json.loads(path.read_text())
            result, _ = run(fixture, 'first_come_first_served')
            self.assertEqual({k for k, v in result['rule_checks'].items() if v is not True}, set(), path.name)

    def test_what_the_first_bank_cannot_take_is_reported_wasted_not_given_to_another_bank(self):
        fixture = load('more-produce-than-storage')  # each food bank has 5 lb of cold and 5 lb of dry space
        result, records = run(fixture, 'first_come_first_served')
        for item, banks in banks_by_item(result).items():
            self.assertEqual(len(banks), 1, item)
            self.assertLessEqual(sum(c['pounds'] for c in result['commitments'] if c['produce_id'] == item), 5 + 1e-9)
        methods = {m['method']: m for m in evaluate(fixture)['methods']}
        self.assertGreater(methods['first_come_first_served']['produce_wasted_lb'], methods['rules_based']['produce_wasted_lb'])
        self.assertEqual(methods['first_come_first_served']['invalid_commitments'], 0)
        lot = records.all('lot')[0]
        unclaimed = [p for p in result['pathways'] if p['status'] == 'unclaimed']
        self.assertTrue(unclaimed and all(p['reason'] for p in unclaimed))

    def test_the_earliest_claimant_goes_first(self):
        fixture = load('normal-afternoon')
        order = Baseline(fixture, 'first_come_first_served').priority
        earliest = {b: min(r['submitted_at'] for r in fixture['requests'] if b in r['chosen_food_bank_ids']) for b in order}
        self.assertEqual([earliest[b] for b in order], sorted(earliest[b] for b in order))


if __name__ == '__main__':
    unittest.main()
