"""The food bank dashboard says what the food bank's own rules-based negotiator would do with
each offer, from that food bank's own facts only (ADR 0001), or why it has no suggestion."""
import copy
import unittest
from harvestnet_agents.negotiation import parse_agent_input
from harvestnet_agents.rules_negotiators import rules_negotiator
from harvestnet_core.api import API
from harvestnet_core.engine import Engine
from harvestnet_core.protocol import named, terms_hash

from test_core import fixture

TOKENS = {'market': 'donor-test', 'city': 'city-test'}


class DashboardSuggestion(unittest.TestCase):
    def setUp(self):
        self.f = fixture()
        self.engine = Engine(self.f)
        self.clock = {'now': '2026-10-13T12:00:00-07:00'}
        self.api = API(self.engine, clock=lambda: self.clock['now'], staff_tokens=TOKENS)
        status, created = self.api.call('POST', '/surplus-offers', copy.deepcopy(self.f['surplus_offers'][0]), token='donor-test')
        self.assertEqual(status, 201, created)
        self.lot_id = created['lot_id']

    def offers(self):
        status, dash = self.api.call('GET', '/food-banks/city/dashboard', token='city-test')
        self.assertEqual(status, 200, dash)
        return [o for o in dash['incoming_offers'] if o['lot_id'] == self.lot_id]

    def test_a_pending_offer_that_fits_is_suggested_for_acceptance_with_the_negotiators_reason(self):
        (offer,) = self.offers()
        self.assertTrue(offer['needs_your_approval'])
        self.assertEqual(offer['agent_suggests'], 'accept')
        self.assertIn('Version', offer['agent_reason'])
        # The same move the city's own rules negotiator makes from the city's own facts.
        lot = self.engine.records.get('lot', self.lot_id)
        raw = {'role': 'food_bank', 'draft': lot['draft'], 'facts': self.engine.facts('city', lot['draft']),
               'turn': {'organization_id': 'city', 'number': 1, 'now': self.clock['now'], 'accepted_by': []}}
        role, typed = parse_agent_input(raw)
        move = rules_negotiator('food_bank', 'city', self.engine.calc).move(typed)
        self.assertEqual(offer['agent_reason'], move.reason)

    def test_asking_for_a_suggestion_changes_nothing(self):
        before = (self.engine.records.get('lot', self.lot_id), len(self.engine.records.events(self.lot_id)))
        self.offers()
        self.offers()
        self.assertEqual((self.engine.records.get('lot', self.lot_id), len(self.engine.records.events(self.lot_id))), before)

    def test_the_suggestion_follows_the_food_banks_own_facts(self):
        # The city's manager now reports almost no dry space: the same offer no longer fits.
        status, _ = self.api.call('PUT', '/food-banks/city/status', {'storage': [{**s, 'dry_free_lb': 1, 'cold_free_lb': 1} for s in self.engine.records.get('bank', 'city')['storage']]}, token='city-test')
        self.assertEqual(status, 200)
        (offer,) = self.offers()
        self.assertEqual(offer['agent_suggests'], 'counter')
        self.assertIn('space', offer['agent_reason'])

    def test_a_committed_offer_has_no_suggestion_and_says_why(self):
        draft = self.engine.records.get('lot', self.lot_id)['draft']
        for owner in named(draft):
            receipt = {'lot_id': self.lot_id, 'version': draft['version'], 'organization_id': owner, 'terms_hash': terms_hash(draft),
                       'decision': 'approve', 'receipt_id': 'r-' + owner}
            self.assertEqual(self.api.call('POST', '/approvals', receipt, token=TOKENS[owner])[0], 200)
        (offer,) = self.offers()
        self.assertFalse(offer['needs_your_approval'])
        self.assertIsNone(offer['agent_suggests'])
        self.assertIn('committed', offer['agent_reason'])

    def test_a_lot_that_ended_without_agreement_has_no_suggestion_and_says_why(self):
        self.clock['now'] = '2026-10-13T15:00:00-07:00'  # the deadline passes with nothing committed
        (offer,) = self.offers()
        self.assertIsNone(offer['agent_suggests'])
        self.assertIn('unclaimed', offer['agent_reason'])


if __name__ == '__main__':
    unittest.main()
