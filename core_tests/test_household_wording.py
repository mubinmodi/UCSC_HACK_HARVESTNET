"""Ticket #6: household-facing produce names and messages follow the household's language.

Spanish produce names come from one source, the produce profiles' ``name_es``. All data is
synthetic.
"""
import json
import unittest
from pathlib import Path

from harvestnet_core.api import API
from harvestnet_core.engine import Engine, run_fixture
from harvestnet_core.records import Records


def fixture():
    return json.loads(Path('core_fixtures/normal-afternoon.json').read_text(encoding='utf-8'))


PICKUP_TIME = '2026-10-13T18:00:00-07:00'


class HouseholdLanguageTests(unittest.TestCase):
    def setUp(self):
        # A committed run that leaves every pickup open.
        self.records = Records()
        run_fixture(fixture() | {'household_replies': []}, records=self.records)
        self.api = API(Engine(fixture(), self.records), clock=lambda: PICKUP_TIME)
        self.request = next(r for r in self.records.all('request') if r['language'] == 'es'
                            and any(p['request_code'] == r['request_code'] for p in self.records.all('pickup')))

    def tearDown(self):
        self.records.close()

    def get(self, language=None):
        query = f'?language={language}' if language else ''
        status, body = self.api.call('GET', f"/requests/{self.request['request_code']}{query}")
        self.assertEqual(status, 200)
        self.assertTrue(body['pickups'])
        return body['pickups']

    def test_spanish_page_shows_spanish_produce_names_from_the_profiles(self):
        profiles = self.api.engine.calc.profiles
        for pickup in self.get('es'):
            for item in pickup['items']:
                self.assertEqual(item['name'], profiles.get(item['produce_id']).name_es)
                self.assertIn(f"lb de {item['name'].lower()}", pickup['wording'])
            self.assertTrue(pickup['wording'].startswith('Puede recoger en'))

    def test_english_page_keeps_english_names(self):
        profiles = self.api.engine.calc.profiles
        for pickup in self.get('en'):
            for item in pickup['items']:
                self.assertEqual(item['name'], profiles.get(item['produce_id']).name)
                self.assertIn(f"lb {item['name'].lower()}", pickup['wording'])

    def test_without_a_page_language_the_request_language_is_used(self):
        self.assertEqual(self.get(), self.get('es'))

    def test_food_bank_list_names_follow_the_request_language(self):
        status, body = self.api.call('GET', f"/food-banks?request_code={self.request['request_code']}")
        self.assertEqual(status, 200)
        profiles = self.api.engine.calc.profiles
        names = {i['name'] for b in body['food_banks'] for i in b['committed_now']}
        self.assertTrue(names)
        self.assertEqual(names, {profiles.get(i['produce_id']).name_es for b in body['food_banks'] for i in b['committed_now']})

    def test_release_message_is_in_the_households_language(self):
        pickup = next(p for p in self.records.all('pickup') if p['request_code'] == self.request['request_code'])
        status, body = self.api.call('POST', f"/pickups/{pickup['pickup_id']}/release", {'request_code': self.request['request_code']})
        self.assertEqual(status, 200)
        self.assertEqual(body['message'], 'Gracias por avisarnos. Su porción pasará a otra familia.')


if __name__ == '__main__':
    unittest.main()
