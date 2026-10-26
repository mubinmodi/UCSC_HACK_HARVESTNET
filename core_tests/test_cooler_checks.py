"""The cooler-failure rule check looks at what is actually committed at the failed cooler.

``failed_cooler_holds_nothing_cold`` used to skip declined or unanswered changes, so it passed
while cold produce was still committed to a cooler that had failed. It now fails unless an
approved change moved that produce, or the produce is held for a human and labeled.
"""
import copy
import json
from pathlib import Path
import unittest
from harvestnet_core import changes
from harvestnet_core.engine import Engine, run_fixture
from harvestnet_core.records import Records

FIXTURE = Path('core_fixtures/cooler-failure.json')
CHECK = 'failed_cooler_holds_nothing_cold'


def run(answer_within_trip):
    fixture = json.loads(FIXTURE.read_text())
    if answer_within_trip:
        for human in fixture['humans']:
            human['after_minutes'] = 1  # inside the planned trip time, so the change commits
    records = Records()
    result = run_fixture(copy.deepcopy(fixture), records=records)
    lot_id = records.all('lot')[0]['draft']['lot_id']
    return Engine(fixture, records), lot_id, result


def cold_commitments_at_failed_cooler(engine, lot_id):
    lot = engine.records.get('lot', lot_id)
    return [a for a in lot['commitments'] if a['food_bank_id'] == 'city' and a['pounds'] > 0 and a.get('pathway') is None
            and engine.calc.profiles.get(a['produce_id']).needs_cold]


class FailedCoolerCheck(unittest.TestCase):
    def test_an_approved_change_that_moved_the_cold_produce_passes(self):
        engine, lot_id, result = run(answer_within_trip=True)
        self.assertEqual(result['faults'][0]['change_status'], 'committed')
        self.assertEqual(cold_commitments_at_failed_cooler(engine, lot_id), [])
        self.assertTrue(changes.rule_checks(engine, lot_id)[CHECK])
        self.assertTrue(result['rule_checks'][CHECK])

    def test_unanswered_change_leaves_the_cold_produce_held_for_a_human_and_labeled(self):
        engine, lot_id, result = run(answer_within_trip=False)
        self.assertEqual(result['faults'][0]['change_status'], 'awaiting_approvals')
        self.assertTrue(cold_commitments_at_failed_cooler(engine, lot_id))  # still committed to the failed cooler
        lot = engine.records.get('lot', lot_id)
        self.assertEqual({(h['food_bank_id'], h['produce_id']) for h in lot['held_for_human']}, {('city', 'romaine')})
        self.assertTrue(all(h['reason'] for h in lot['held_for_human']))
        self.assertTrue(result['rule_checks'][CHECK])
        self.assertTrue(changes.rule_checks(engine, lot_id)[CHECK])

    def test_cold_produce_left_committed_and_unlabeled_at_the_failed_cooler_fails(self):
        engine, lot_id, _ = run(answer_within_trip=False)
        lot = engine.records.get('lot', lot_id)
        lot.pop('held_for_human')
        engine.records.put('lot', lot_id, lot)
        self.assertFalse(changes.rule_checks(engine, lot_id)[CHECK])

    def test_a_cold_pickup_still_scheduled_at_the_failed_cooler_fails(self):
        engine, lot_id, _ = run(answer_within_trip=False)
        held = next(p for p in engine.records.all('pickup') if p['status'] == 'held_for_human')
        engine.records.put('pickup', held['pickup_id'], {**held, 'status': 'committed'})
        self.assertFalse(changes.rule_checks(engine, lot_id)[CHECK])

    def test_a_declined_change_is_not_skipped(self):
        engine, lot_id, _ = run(answer_within_trip=False)
        change = changes.changes_for(engine.records, lot_id)[-1]
        engine.now = '2026-10-13T15:31:00-07:00'  # inside the planned trip time
        receipt = {'lot_id': lot_id, 'version': change['version'], 'organization_id': 'eastside', 'terms_hash': change['terms_hash'],
                   'decision': 'decline', 'receipt_id': 'decline-eastside'}
        self.assertEqual(changes.approve(engine, receipt, 'eastside')['status'], 'declined')
        self.assertTrue(cold_commitments_at_failed_cooler(engine, lot_id))
        lot = engine.records.get('lot', lot_id)
        lot.pop('held_for_human', None)
        engine.records.put('lot', lot_id, lot)
        self.assertFalse(changes.rule_checks(engine, lot_id)[CHECK])

    def test_a_run_with_no_proposed_change_still_holds_the_cold_produce_for_a_human(self):
        engine, lot_id, result = run(answer_within_trip=False)
        # Without any change record the check still looks at the commitments.
        for key in [c['version'] for c in changes.changes_for(engine.records, lot_id)]:
            engine.records.delete('change', f'{lot_id}:{key}')
        self.assertEqual(changes.changes_for(engine.records, lot_id), [])
        self.assertTrue(changes.rule_checks(engine, lot_id)[CHECK])
        lot = engine.records.get('lot', lot_id)
        lot.pop('held_for_human')
        engine.records.put('lot', lot_id, lot)
        self.assertFalse(changes.rule_checks(engine, lot_id)[CHECK])


if __name__ == '__main__':
    unittest.main()
