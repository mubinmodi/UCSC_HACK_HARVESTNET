"""Design section 8: the state diagram and the stop-rule table, through the public API.

A preserved disagreement survives the deadline. A hold that expires, or a human's decline,
sends the lot back to negotiation; nothing is ever committed automatically.
"""
import copy
import unittest
from harvestnet_core.api import API
from harvestnet_core.engine import Engine
from harvestnet_core.protocol import terms_hash

from test_core import fixture

TOKENS = {'market': 'donor-test', 'city': 'city-test'}


def api_for(f):
    engine = Engine(f)
    clock = {'now': '2026-10-13T12:00:00-07:00'}
    return API(engine, clock=lambda: clock['now'], staff_tokens=TOKENS), engine, clock


def kinds(engine, lot_id):
    return [e['kind'] for e in engine.records.events(lot_id)]


def receipt(draft, owner, decision, rid):
    return {'lot_id': draft['lot_id'], 'version': draft['version'], 'organization_id': owner,
            'terms_hash': terms_hash(draft), 'decision': decision, 'receipt_id': rid}


class PreservedDisagreementTests(unittest.TestCase):
    def setUp(self):
        f = fixture()
        for slot in f['food_banks'][0]['storage']:
            slot['dry_free_lb'] = slot['cold_free_lb'] = 0  # the only food bank has no space: nobody can agree
        self.api, self.engine, self.clock = api_for(f)
        status, created = self.api.call('POST', '/surplus-offers', copy.deepcopy(f['surplus_offers'][0]), token='donor-test')
        self.assertEqual(status, 201, created)
        self.lot_id = created['lot_id']

    def test_the_disagreement_is_kept_when_the_deadline_passes(self):
        before = self.api.call('GET', '/lots/' + self.lot_id)[1]
        self.assertEqual(before['status'], 'preserved_disagreement')
        self.clock['now'] = '2026-10-13T15:00:00-07:00'  # the donor's deadline
        status, lot = self.api.call('GET', '/lots/' + self.lot_id)
        self.assertEqual(status, 200)
        self.assertEqual(lot['status'], 'preserved_disagreement')
        self.assertNotIn('deadline_unclaimed', kinds(self.engine, self.lot_id))
        self.assertEqual(self.engine.records.get('lot', self.lot_id)['commitments'], [])
        self.assertEqual(lot['disagreement']['reason'], before['disagreement']['reason'])
        self.assertTrue(all(i['status'] != 'unclaimed' for i in lot['items']))

    def test_the_disagreement_shows_its_options_and_each_organizations_reason(self):
        self.clock['now'] = '2026-10-13T15:00:00-07:00'
        disagreement = self.api.call('GET', '/lots/' + self.lot_id)[1]['disagreement']
        self.assertTrue(disagreement['options'])
        self.assertTrue(all({'version', 'proposer_id', 'reason', 'allocations'} <= set(o) for o in disagreement['options']))
        by_org = {r['organization_id']: r for r in disagreement['reasons']}
        self.assertTrue({'market', 'city'} <= set(by_org))
        self.assertTrue(all(r['reason'] for r in by_org.values()))

    def test_the_food_bank_dashboard_still_lists_it_after_the_deadline(self):
        self.clock['now'] = '2026-10-13T15:00:00-07:00'
        status, dash = self.api.call('GET', '/food-banks/city/dashboard', token='city-test')
        self.assertEqual(status, 200)
        mine = [d for d in dash['disagreements'] if d['lot_id'] == self.lot_id]
        self.assertEqual(len(mine), 1)
        self.assertTrue(mine[0]['reasons'] and mine[0]['options'])

    def test_a_lot_still_awaiting_approvals_does_become_unclaimed(self):
        f = fixture()
        api, engine, clock = api_for(f)
        lot_id = api.call('POST', '/surplus-offers', copy.deepcopy(f['surplus_offers'][0]), token='donor-test')[1]['lot_id']
        self.assertEqual(engine.records.get('lot', lot_id)['status'], 'awaiting_approvals')
        clock['now'] = '2026-10-13T15:00:00-07:00'
        self.assertEqual(api.call('GET', '/lots/' + lot_id)[1]['status'], 'unclaimed')


class ReturnToNegotiationTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture()
        self.api, self.engine, self.clock = api_for(self.f)
        status, created = self.api.call('POST', '/surplus-offers', copy.deepcopy(self.f['surplus_offers'][0]), token='donor-test')
        self.assertEqual(status, 201, created)
        self.lot_id = created['lot_id']
        self.lot = self.engine.records.get('lot', self.lot_id)
        self.assertEqual(self.lot['status'], 'awaiting_approvals')
        self.draft = self.lot['draft']

    def after(self, kind):
        events = self.engine.records.events(self.lot_id)
        index = max(i for i, e in enumerate(events) if e['kind'] == kind)
        return [e['kind'] for e in events[index + 1:]]

    def test_a_human_decline_returns_the_lot_to_negotiation_and_never_commits(self):
        status, result = self.api.call('POST', '/approvals', receipt(self.draft, 'city', 'decline', 'r-decline'), token='city-test')
        self.assertEqual(status, 200, result)
        self.assertEqual(result['status'], 'returned_to_negotiation')
        self.assertFalse(result['committed'])
        self.assertIn('move', self.after('returned_to_negotiation'))  # the owners' next turns ran
        lot = self.engine.records.get('lot', self.lot_id)
        self.assertNotIn('commitment', kinds(self.engine, self.lot_id))
        self.assertEqual(lot['commitments'], [])
        # The declined terms never come back for approval unchanged.
        self.assertFalse(lot['status'] == 'awaiting_approvals' and lot['draft']['version'] == self.draft['version'])

    def test_after_a_decline_the_lot_ends_as_a_preserved_disagreement_when_nothing_new_is_proposed(self):
        self.api.call('POST', '/approvals', receipt(self.draft, 'city', 'decline', 'r-decline'), token='city-test')
        lot = self.api.call('GET', '/lots/' + self.lot_id)[1]
        if lot['current_version'] == self.draft['version']:
            self.assertEqual(lot['status'], 'preserved_disagreement')
            self.assertIn('declined', lot['disagreement']['reason'])

    def test_a_decline_does_not_let_the_other_humans_approval_commit_the_old_terms(self):
        self.api.call('POST', '/approvals', receipt(self.draft, 'city', 'decline', 'r-decline'), token='city-test')
        status, result = self.api.call('POST', '/approvals', receipt(self.draft, 'market', 'approve', 'r-market'), token='donor-test')
        self.assertNotEqual(status, 500)
        self.assertFalse(result.get('committed', False))
        self.assertEqual(self.engine.records.get('lot', self.lot_id)['commitments'], [])

    def test_a_lot_whose_hold_expired_goes_back_to_negotiation_and_never_commits(self):
        self.clock['now'] = '2026-10-13T14:59:00-07:00'  # before the deadline, after the donor's drop-off hold ended
        self.api.call('GET', '/health')  # any call; the API notices the expired hold
        self.assertIn('hold_expired', kinds(self.engine, self.lot_id))
        self.assertIn('move', self.after('hold_expired'))  # the owners' next turns ran
        lot = self.engine.records.get('lot', self.lot_id)
        self.assertNotIn(lot['status'], ('committed', 'awaiting_approvals'))
        self.assertEqual(lot['approvals'], {})  # fresh holds, then fresh approvals
        for owner, token in (('market', 'donor-test'), ('city', 'city-test')):
            status, result = self.api.call('POST', '/approvals', receipt(lot['draft'], owner, 'approve', 'late-' + owner), token=token)
            self.assertNotEqual(status, 500)
            self.assertFalse(result.get('committed', False))
        self.assertEqual(self.engine.records.get('lot', self.lot_id)['commitments'], [])

    def test_an_approval_that_arrives_after_a_hold_expired_returns_the_lot_to_negotiation(self):
        """The protocol itself, for callers that do not sweep first (the scenario harness)."""
        result = self.engine.protocol.approve(receipt(self.draft, 'city', 'approve', 'r-late'), 'city', '2026-10-13T14:59:00-07:00', self.engine.validate)
        self.assertFalse(result['committed'])
        self.assertEqual(result['returned_to_negotiation'], 'hold_expired')
        lot = self.engine.records.get('lot', self.lot_id)
        self.assertEqual((lot['status'], lot['approvals'], lot['commitments']), ('negotiating', {}, []))
        self.assertIn('hold_expired', kinds(self.engine, self.lot_id))

    def test_a_retried_receipt_after_expiry_returns_the_same_answer(self):
        r = receipt(self.draft, 'city', 'approve', 'r-late')
        first = self.engine.protocol.approve(r, 'city', '2026-10-13T14:59:00-07:00', self.engine.validate)
        self.assertEqual(self.engine.protocol.approve(r, 'city', '2026-10-13T14:59:30-07:00', self.engine.validate), first)


if __name__ == '__main__':
    unittest.main()
