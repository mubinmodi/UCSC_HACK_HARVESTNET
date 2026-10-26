"""One organization roster for the platform, equal to the contract scenario's organizations."""
import json
from pathlib import Path
import unittest
from harvestnet_platform import approvals, roster, systems, transport

CONTRACT_SCENARIO = Path(__file__).parents[1] / 'docs' / 'contracts' / 'examples' / 'scenario-normal-afternoon.json'
CORE_FIXTURES = Path(__file__).parents[1] / 'core_fixtures'


class OneRoster(unittest.TestCase):
    def test_every_module_reads_the_roster(self):
        self.assertIs(transport.ORGANIZATIONS, roster.ORGANIZATIONS)
        self.assertIs(transport.ROLES, roster.ROLES)
        self.assertIs(approvals.APPROVERS, roster.APPROVERS)
        self.assertIs(systems.SYSTEM_ORGANIZATIONS, roster.SYSTEM_ORGANIZATIONS)
        self.assertEqual((systems.DONOR, systems.BANKS), (roster.DONOR, roster.BANKS))

    def test_roster_matches_the_contract_scenarios_organizations_and_roles(self):
        for path in [CONTRACT_SCENARIO, *sorted(CORE_FIXTURES.glob('*.json'))]:
            scenario = json.loads(path.read_text())
            self.assertEqual({o['organization_id']: o['role'] for o in scenario['organizations']}, roster.ROLES, path.name)

    def test_only_organizations_with_humans_approve_and_only_those_have_systems(self):
        self.assertEqual(set(roster.ORGANIZATIONS) - set(roster.APPROVERS), {roster.ADVOCATE})
        self.assertEqual(roster.APPROVERS, roster.SYSTEM_ORGANIZATIONS)

    def test_the_donor_is_called_by_its_organization_id_only(self):
        store = approvals.ApprovalStore()
        with self.assertRaises(ValueError):
            store.request('lot', 1, {'lb': 1}, ['donor', 'city'])
        store.db.close()


if __name__ == '__main__':
    unittest.main()
