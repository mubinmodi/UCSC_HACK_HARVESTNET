"""Pickup messages by email (user decision, October 11, 2026; contract-v0.2).

The household's optional email: validated, write-only, never returned or put in an event,
deleted with the request after 7 days. Its pickup emails, in English and Spanish, carry a
"Can't make it" link that really releases the pickup through the core. All data is synthetic;
addresses use the reserved example.invalid domain. Nothing is sent.
"""
import json
import os
import sys
import unittest
from urllib.parse import parse_qs, urlsplit

from harvestnet_core.api import API
from harvestnet_core.contact import email_address, release_url
from harvestnet_core.engine import Engine, run_fixture
from harvestnet_core.notices import pickup_notice, released_notice
from harvestnet_core.records import Records

from test_core import fixture

ADDRESS = 'Household.Test+pickup@Example.INVALID'
STORED = 'Household.Test+pickup@example.invalid'
PAGE = 'https://households.example.invalid/household/'


def form(f):
    return {k: f['requests'][0][k] for k in ('household_size', 'pickup_windows', 'limited_fridge', 'neighborhood', 'cant_eat', 'snap', 'language')}


class EmailAddress(unittest.TestCase):
    def test_valid_addresses_are_trimmed_and_their_domain_lowercased(self):
        self.assertEqual(email_address('  ' + ADDRESS + ' '), STORED)
        self.assertEqual(email_address('a@b.co'), 'a@b.co')

    def test_invalid_addresses_are_refused_without_repeating_them(self):
        for bad in ('', 'no-at-sign', 'two@@example.invalid', 'a@b', 'a@b.c', 'a b@example.invalid', 'a@exa mple.invalid',
                    '.a@example.invalid', 'a..b@example.invalid', 'a@-example.invalid', 'a@example.invalid\r\nBcc: x@example.invalid',
                    'a@example.invalid,b@example.invalid', '<a@example.invalid>', '"a"@example.invalid', 'x' * 65 + '@example.invalid',
                    'a@' + 'b' * 250 + '.invalid', 42, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError) as refused:
                email_address(bad)
            if isinstance(bad, str) and bad:
                self.assertNotIn(bad, str(refused.exception))

    def test_release_link_puts_pickup_and_code_in_the_fragment(self):
        url = release_url('https://households.example.invalid/household', 'pk-1 2', 'K7P4', 'es')
        parts = urlsplit(url)
        self.assertEqual((parts.path, parts.query), ('/household/', ''))  # nothing reaches a server log
        self.assertEqual({k: v[0] for k, v in parse_qs(parts.fragment).items()}, {'pickup': 'pk-1 2', 'code': 'K7P4', 'lang': 'es'})
        with self.assertRaises(ValueError):
            release_url('', 'pk-1', 'K7P4')


class CreateRequestEmail(unittest.TestCase):
    def setUp(self):
        self.f = fixture()
        self.engine = Engine(self.f)
        self.now = '2026-10-13T12:00:00-07:00'
        self.api = API(self.engine, clock=lambda: self.now)
        self.form = {**form(self.f), 'consent': True, 'channel': 'web'}
        self.seeded = len(self.engine.records.all('request'))  # the fixture's own requests

    def everything_stored(self):
        rows = self.engine.records.execute('SELECT kind, data FROM records').fetchall()
        events = self.engine.records.execute('SELECT data FROM events').fetchall()
        return rows, json.dumps(events)

    def test_email_is_optional_write_only_and_never_returned(self):
        status, body = self.api.call('POST', '/requests', self.form)
        self.assertEqual((status, body['emails']), (201, False))
        status, body = self.api.call('POST', '/requests', {**self.form, 'email': ADDRESS})
        self.assertEqual((status, body['emails']), (201, True))
        code = body['request_code']
        self.assertEqual(self.engine.records.get('email', code)['email'], STORED)
        responses = [body]
        for target in (f'/requests/{code}', f'/food-banks?request_code={code}', '/'):
            responses.append(self.api.call('GET', target)[1])
        responses.append(self.api.call('PUT', f'/requests/{code}/food-banks', {'food_bank_ids': ['city']})[1])
        dump = json.dumps(responses).lower()
        self.assertNotIn('household.test', dump)
        self.assertNotIn('"email"', dump)
        rows, events = self.everything_stored()
        self.assertEqual([kind for kind, data in rows if 'household.test' in data.lower()], ['email'])
        self.assertNotIn('household.test', events.lower())

    def test_a_bad_email_saves_nothing_and_is_not_echoed(self):
        status, body = self.api.call('POST', '/requests', {**self.form, 'email': 'not an address'})
        self.assertEqual(status, 400)
        self.assertNotIn('not an address', json.dumps(body))
        self.assertEqual((len(self.engine.records.all('request')), self.engine.records.all('email')), (self.seeded, []))

    def test_phone_is_no_longer_collected(self):
        status, body = self.api.call('POST', '/requests', {**self.form, 'phone': '+15555550142'})
        self.assertEqual(status, 400)
        self.assertIn('email', body['error']['message'])
        self.assertNotIn('5555550142', json.dumps(body))
        self.assertEqual((len(self.engine.records.all('request')), self.engine.records.all('phone')), (self.seeded, []))

    def test_email_is_deleted_with_its_request_after_seven_days(self):
        code = self.api.call('POST', '/requests', {**self.form, 'email': ADDRESS})[1]['request_code']
        self.engine.records.put('phone', code, {'phone': '+15555550142'})  # a record from contract-v0.1 goes too
        self.now = '2026-10-20T11:59:00-07:00'
        self.assertEqual(self.api.call('GET', f'/requests/{code}')[0], 200)
        self.assertTrue(self.engine.records.all('email'))
        self.now = '2026-10-20T12:00:00-07:00'
        self.assertEqual(self.api.call('GET', f'/requests/{code}')[0], 404)
        self.assertEqual((self.engine.records.all('email'), self.engine.records.all('phone')), ([], []))
        rows, events = self.everything_stored()
        self.assertFalse(any('household.test' in data.lower() for _, data in rows))


@unittest.skipUnless(os.environ.get('HARVESTNET_PLATFORM_SOURCE'), 'pinned platform package not configured')
class PickupEmails(unittest.TestCase):
    """English and Spanish emails from a real committed pickup; the link releases it."""

    def setUp(self):
        sys.path.insert(0, os.environ['HARVESTNET_PLATFORM_SOURCE'])
        from harvestnet_platform.approvals import pickup_email
        self.pickup_email = pickup_email

    def run_household(self, language):
        f = fixture()
        f['household_replies'] = []
        f['requests'][0]['language'] = language
        records = Records()
        run_fixture(f, records=records)
        api = API(Engine(f, records), clock=lambda: '2026-10-13T18:00:00-07:00')
        code = f['requests'][0]['request_code']
        with records.transaction():
            records.put('email', code, {'email': STORED, 'expires_at': records.get('request', code)['expires_at']})
        pickup = next(p for p in records.all('pickup') if p['request_code'] == code and p['status'] == 'committed')
        return api, records, code, pickup

    def check_language(self, language, subject, words, thanks):
        api, records, code, pickup = self.run_household(language)
        notice = pickup_notice(api, pickup['pickup_id'], household_page_url=PAGE)
        self.assertEqual((notice['to'], notice['language'], notice['kind']), (STORED, language, 'pickup_ready'))
        mail = self.pickup_email(notice)
        self.assertEqual(mail['to'], STORED)
        self.assertTrue(mail['subject'].startswith(subject), mail['subject'])
        for part in (*words, code, f"{pickup['pounds']:g} lb"):
            self.assertIn(part, mail['text'])
        # The link in the email opens the household page on this pickup with its code ...
        link = next(line for line in mail['text'].splitlines() if line.startswith(PAGE))
        self.assertEqual(link, notice['release_url'])
        opened = {k: v[0] for k, v in parse_qs(urlsplit(link).fragment).items()}
        self.assertEqual(opened, {'pickup': pickup['pickup_id'], 'code': code, 'lang': language})
        # ... and the page's "Can't make it" button releases it through the core.
        status, released = api.call('POST', f"/pickups/{opened['pickup']}/release", {'request_code': opened['code']})
        self.assertEqual((status, released['released']), (200, True), released)
        self.assertEqual(records.get('pickup', pickup['pickup_id'])['status'], 'released')
        thank_you = self.pickup_email(released_notice(api, pickup['pickup_id'], code))
        self.assertEqual(thank_you['to'], STORED)
        self.assertIn(thanks, thank_you['text'])
        with self.assertRaises(ValueError):
            pickup_notice(api, pickup['pickup_id'], household_page_url=PAGE)  # released: nothing to announce

    def test_english_pickup_email(self):
        self.check_language('en', 'HarvestNet: your produce is ready at', ('lb apples', 'Your code:', "Can't make it?", 'Please wash produce'),
                            'Thanks for telling us. Your portion will go to another family.')

    def test_spanish_pickup_email_uses_name_es(self):
        self.check_language('es', 'HarvestNet: sus productos están listos en', ('lb de manzanas', 'Su código:', '¿No puede ir?', 'lave los productos'),
                            'Gracias por avisarnos. Su porción pasará a otra familia.')

    def test_household_without_an_email_gets_no_message(self):
        api, records, code, pickup = self.run_household('en')
        with records.transaction():
            records.delete('email', code)
        notice = pickup_notice(api, pickup['pickup_id'], household_page_url=PAGE)
        self.assertIsNone(notice['to'])
        with self.assertRaises(ValueError):
            self.pickup_email(notice)


if __name__ == '__main__':
    unittest.main()
