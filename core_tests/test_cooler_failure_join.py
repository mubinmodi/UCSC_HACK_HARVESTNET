"""#23 join: the cooler failure end to end, locally, over real local HTTP servers.

Lane C's organization systems and demo switch, its local Directory, and its approval
bridge; Lane B's cooler-failure flow; Lane A's core API, records and calculators. The
humans' decisions are made in the test, one organization at a time, through Lane C's
review links. All data is synthetic. No network beyond 127.0.0.1, no paid APIs.
"""
import copy
import json
import os
import socket
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError

from harvestnet_core.api import API
from harvestnet_core.server import make_server
from harvestnet_core import changes

FIXTURE = Path('core_fixtures/cooler-failure.json')
LOT = 'lot-market-1013'
TOKENS = {'market': 'synthetic-market-staff', 'city': 'synthetic-city-staff', 'rural': 'synthetic-rural-staff', 'eastside': 'synthetic-eastside-staff'}
EVENTS, DEMO = 'synthetic-events-token', 'synthetic-demo-switch'
# Translation pending ticket #6; the same name Lane B's recorded fixture uses.
ITEM_NAMES = {'es': {'romaine': 'lechuga romana'}}
# Fictional 555 numbers, only to show where the core attaches a phone.
PHONES = {'C4N6': '+15555550101', 'K7P4': '+15555550102'}


def call(method, url, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw.decode())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read() or b'{}')


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@unittest.skipUnless(os.environ.get('HARVESTNET_PLATFORM_SOURCE'), 'pinned platform package not configured')
class CoolerFailureJoin(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.environ['HARVESTNET_PLATFORM_SOURCE'])
        from harvestnet_core import cooler_join as join
        from harvestnet_platform import approvals, systems as lane_c_systems
        from harvestnet_platform.directory import LocalDirectory
        from harvestnet_platform.transport import ORGANIZATIONS
        self.join = join
        self.fixture = json.loads(FIXTURE.read_text())
        self.engine, self.faults, self.pre_run = join.run_until_fault(self.fixture)
        self.fault = self.faults[0]
        self.clock = {'now': self.fault['at']}
        self.api = API(self.engine, clock=lambda: self.clock['now'], staff_tokens=TOKENS)
        with self.engine.records.transaction():
            for code, phone in PHONES.items():
                self.engine.records.put('phone', code, {'phone': phone, 'expires_at': self.engine.records.get('request', code)['expires_at']})
        self.servers = []
        core = make_server(self.api, port=0)
        self.core_url = self.serve(core)
        self.systems = join.scenario_systems(join.organization_systems(self.engine, self.fault['at'], self.faults))
        self.systems_url = self.serve(ThreadingHTTPServer(('127.0.0.1', 0), lane_c_systems.handler_for(self.systems, DEMO)))
        port = free_port()
        self.approvals_url = f'http://127.0.0.1:{port}'
        self.store = approvals.ApprovalStore()
        bridge = join.organization_core_api(self.core_url, {k: v for k, v in TOKENS.items()})
        self.serve(ThreadingHTTPServer(('127.0.0.1', port), approvals.handler_for(self.store, bridge, EVENTS, self.approvals_url)))
        # Local Directory fallback (labeled); agent URLs are placeholders, no agent hosts run here.
        self.directory = LocalDirectory(self.systems, {org: f'http://127.0.0.1/agents/{org}' for org in ORGANIZATIONS})

    def serve(self, server):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        return f'http://127.0.0.1:{server.server_port}'

    def tearDown(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join()
        self.store.db.close()
        self.engine.records.close()

    def handle(self):
        return self.join.handle_cooler_reading(
            food_bank_id='city', lot_id=LOT, systems_url=self.systems_url, core_url=self.core_url, token=TOKENS['city'],
            directory=self.directory, answer=lambda org: self.join.candidate_answer(self.systems_url, org, self.engine.names[org]))

    def flip_switch(self):
        status, reading = call('POST', self.systems_url + '/demo/city/cooler', {'failed': True}, DEMO)
        self.assertEqual(status, 200)
        self.assertEqual(reading['data']['status'], 'failed')
        return reading

    def human(self, link, decision, at):
        """One organization's human opens its own review link and decides."""
        self.clock['now'] = at
        token = link['decision_url'].split('token=', 1)[1]
        status, page = call('GET', link['decision_url'])
        self.assertEqual(status, 200)
        self.assertIn(f"Review draft version {link['version']}", page)
        return call('POST', self.approvals_url + '/human/decision', {'token': token, 'decision': decision,
                    'version': link['version'], 'terms_hash': link['terms_hash'], 'human_confirmed': True})

    def propose_and_request(self):
        self.flip_switch()
        result = self.handle()
        status, issued = call('POST', self.approvals_url + '/approval-requests', result['change']['approval_request'], EVENTS)
        self.assertEqual(status, 201)
        self.assertFalse(issued['committed'])
        return result, {link['organization_id']: link for link in issued['requests']}

    def test_cooler_switch_to_new_household_texts_end_to_end(self):
        lot_before = self.engine.records.get('lot', LOT)
        self.assertEqual(lot_before['status'], 'committed')
        self.assertIn({'produce_id': 'romaine', 'food_bank_id': 'city', 'pounds': 200.0}, lot_before['commitments'])

        # Before the switch the reading is working: nothing happens.
        self.assertEqual(self.handle()['status'], 'no_failure')
        self.assertEqual(self.engine.records.all('change'), [])
        self.assertEqual(call('POST', self.systems_url + '/demo/city/cooler', {'failed': True})[0], 401)

        # The switch -> the disruption is detected from the organization-system reading.
        reading = self.flip_switch()
        self.assertEqual(reading['disruption'], 'synthetic_cooler_failure')
        result = self.handle()
        flow, change = result['flow'], result['change']
        self.assertEqual(result['status'], 'assessed')
        self.assertEqual(self.engine.records.get('bank', 'city')['cooler']['status'], 'failed')

        # 1. Only cold-dependent items move.
        self.assertEqual([i.produce_id for i in flow.decision.items_to_move], ['romaine'])
        self.assertEqual([i.produce_id for i in flow.decision.items_staying], ['apples'])
        terms = change['approval_request']['terms']
        self.assertEqual([(m['produce_id'], m['pounds'], m['to_food_bank_id']) for m in terms['moves']], [('romaine', 150, 'eastside')])
        self.assertEqual([(f['produce_id'], f['pounds'], f['kind']) for f in terms['fallback']], [('romaine', 50, 'same_day_offer')])
        self.assertEqual([(s['produce_id'], s['pounds']) for s in terms['staying']], [('apples', 50)])

        # 2. Every candidate has a reason card on the food bank dashboard.
        self.assertEqual(call('GET', self.core_url + '/food-banks/city/dashboard')[0], 401)
        status, board = call('GET', self.core_url + '/food-banks/city/dashboard', token=TOKENS['city'])
        self.assertEqual(status, 200)
        self.assertEqual(board['capacity']['cooler']['status'], 'failed')
        [disruption] = board['disruptions']
        cards = disruption['dashboard']['reason_cards']
        found = self.directory.search(min_cold_lb=0)['records']
        candidates = sorted(json.loads(r['annotations']['harvestnet'])['organization_id'] for r in found
                            if json.loads(r['annotations']['harvestnet'])['capabilities']['role'] == 'food_bank')
        self.assertEqual(sorted(c['food_bank_id'] for c in cards), [c for c in candidates if c != 'city'])
        self.assertTrue(all(c['text'] and c['reasons'] for c in cards))
        self.assertEqual({c['food_bank_id']: c['outcome'] for c in cards}, {'eastside': 'chosen', 'rural': 'rejected'})
        self.assertIn('Directory results came from', ' '.join(disruption['dashboard']['flags']))
        self.assertNotIn('request_code', json.dumps(board))
        status, receiver_board = call('GET', self.core_url + '/food-banks/eastside/dashboard', token=TOKENS['eastside'])
        self.assertTrue(receiver_board['disruptions'][0]['needs_your_approval'])

        # 3. The new version needs fresh approvals.
        self.assertEqual((change['version'], change['based_on_version'], change['committed']), (13, 12, False))
        self.assertEqual(change['terms_hash'], 'sha256:' + flow.new_version.terms_hash)
        self.assertEqual(lot_before['approvals']['eastside']['version'], 12)  # the old approvals exist ...
        self.assertEqual(changes.find(self.engine.records, LOT, 13)['approvals'], {})  # ... and don't carry over
        status, pending = call('GET', self.core_url + '/approvals?organization_id=eastside', token=TOKENS['eastside'])
        self.assertEqual([(a['version'], a['change']) for a in pending['approvals']], [(13, 'cooler_failure')])
        stale = {'lot_id': LOT, 'version': 13, 'organization_id': 'eastside', 'decision': 'approve',
                 'terms_hash': lot_before['approvals']['eastside']['terms_hash']}
        self.assertEqual(call('POST', self.core_url + '/approvals', stale, TOKENS['eastside'])[0], 409)
        status, issued = call('POST', self.approvals_url + '/approval-requests', change['approval_request'], EVENTS)
        self.assertEqual(status, 201)
        links = {link['organization_id']: link for link in issued['requests']}
        self.assertEqual(sorted(links), ['city', 'eastside'])
        self.assertTrue(all(l['terms_hash'] == flow.new_version.terms_hash and 'version 13' in l['message'] for l in links.values()))

        status, decided = self.human(links['eastside'], 'approve', '2026-10-13T15:35:00-07:00')
        self.assertEqual(status, 200)
        self.assertEqual((decided['committed'], decided['awaiting_approval_from']), (False, ['city']))
        from harvestnet_agents.cooler_failure_flow import NotCommittedError
        with self.assertRaises(NotCommittedError):
            self.join.household_texts(self.engine, LOT, 13, household_page_url='https://households.example.invalid', item_names=ITEM_NAMES)
        status, decided = self.human(links['city'], 'approve', '2026-10-13T15:40:00-07:00')
        self.assertEqual(status, 200)
        self.assertTrue(decided['committed'])

        lot = self.engine.records.get('lot', LOT)
        self.assertEqual(lot['change_version'], 13)
        romaine = sorted((a['food_bank_id'], a['pounds'], a.get('pathway')) for a in lot['commitments'] if a['produce_id'] == 'romaine')
        self.assertEqual(romaine, [('city', 50.0, 'same_day_offer'), ('eastside', 150.0, None)])
        self.assertIn({'produce_id': 'apples', 'food_bank_id': 'city', 'pounds': 50.0}, lot['commitments'])

        # 4. Affected households get a new text and can decline.
        notices = self.join.household_texts(self.engine, LOT, 13, household_page_url='https://households.example.invalid', item_names=ITEM_NAMES)
        by_code = {n['request_code']: n for n in notices}
        self.assertEqual(sorted(by_code), ['C4N6', 'D9H3', 'G1L7', 'K7P4'])
        self.assertEqual({c: n['reply_expected'] for c, n in by_code.items()}, {'C4N6': True, 'D9H3': False, 'G1L7': False, 'K7P4': True})
        self.assertTrue(all(n['food_bank_id'] == 'eastside' and n['version'] == 13 and n['decline_replies'] for n in notices))
        self.assertIn('NO PUEDO IR', by_code['K7P4']['message'])
        self.assertIn('lechuga romana', by_code['K7P4']['message'])
        self.assertIn("CAN'T MAKE IT", by_code['C4N6']['message'])
        self.assertEqual({c: n['to'] for c, n in by_code.items() if n['to']}, PHONES)
        pickup = self.engine.records.get('pickup', by_code['C4N6']['pickup_id'])
        self.assertEqual((pickup['food_bank_id'], pickup['version'], pickup['moved_from_food_bank_id']), ('eastside', 13, 'city'))
        self.assertEqual(by_code['C4N6']['items'], [{'name': 'romaine lettuce', 'pounds': pickup['pounds'], 'produce_id': 'romaine'}])
        prepared = self.join.prepare_texts(self.approvals_url, EVENTS, notices)
        self.assertEqual(sorted(p['to'] for p in prepared), sorted(PHONES.values()))
        self.assertTrue(all(p['sent'] is False and 'Eastside food bank' in p['message'] for p in prepared))
        self.assertTrue(all('/pickups/' in p['message'] for p in prepared))
        # The fixture's own reply: C4N6 can't make it. The household page's button releases it.
        self.clock['now'] = '2026-10-13T18:00:00-07:00'
        status, released = call('POST', f"{self.core_url}/pickups/{by_code['C4N6']['pickup_id']}/release", {'request_code': 'C4N6'})
        self.assertEqual((status, released['released']), (200, True))
        self.assertEqual(self.engine.records.get('pickup', by_code['C4N6']['pickup_id'])['status'], 'released')

        # 5. The cooler-failure fixture passes every rule check (Lane A core + Lane B flow).
        checks = self.join.rule_checks(self.engine, LOT, flow)
        self.assertEqual({k for k, v in checks.items() if v is not True}, set())
        self.assertTrue({'no_double_booking', 'zero_invalid_commitments', 'only_cold_dependent_items_move',
                         'every_candidate_has_reason_card', 'failed_cooler_holds_nothing_cold'} <= set(checks))
        report = self.join.outcomes(self.engine, LOT, flow)
        self.assertTrue(all(report['rule_checks'].values()))

    def test_the_receiving_food_bank_can_decline_and_nothing_commits(self):
        result, links = self.propose_and_request()
        status, decided = self.human(links['eastside'], 'decline', '2026-10-13T15:35:00-07:00')
        self.assertEqual((status, decided['committed'], decided['change_status']), (200, False, 'declined'))
        # The proposer's later approval of the declined version changes nothing. The core
        # answers 409; Lane C's bridge reports any core HTTP error as 503 (a listed gap).
        self.assertNotEqual(self.human(links['city'], 'approve', '2026-10-13T15:40:00-07:00')[0], 200)
        late = {'lot_id': LOT, 'version': 13, 'organization_id': 'city', 'decision': 'approve', 'terms_hash': result['change']['terms_hash']}
        self.assertEqual(call('POST', self.core_url + '/approvals', late, TOKENS['city'])[0], 409)
        lot = self.engine.records.get('lot', LOT)
        self.assertIn({'produce_id': 'romaine', 'food_bank_id': 'city', 'pounds': 200.0}, lot['commitments'])
        self.assertNotIn('change_version', lot)
        self.assertTrue(all(p['food_bank_id'] != 'eastside' or p['items'][0]['produce_id'] != 'romaine' for p in self.engine.records.all('pickup')))
        from harvestnet_agents.cooler_failure_flow import NotCommittedError
        with self.assertRaises(NotCommittedError):
            self.join.household_texts(self.engine, LOT, 13, household_page_url='https://households.example.invalid', item_names=ITEM_NAMES)
        self.assertTrue(self.join.rule_checks(self.engine, LOT, result['flow'])['no_auto_commit'])

    def test_core_refuses_stale_unnamed_late_and_unrecorded_changes(self):
        self.flip_switch()
        change = self.handle()['change']
        flow_terms = change['approval_request']['terms']
        receipt = {'lot_id': LOT, 'version': 13, 'decision': 'approve', 'terms_hash': change['terms_hash']}
        self.assertEqual(call('POST', self.core_url + '/approvals', {**receipt, 'organization_id': 'rural'}, TOKENS['rural'])[0], 409)
        self.assertEqual(call('POST', self.core_url + '/approvals', {**receipt, 'organization_id': 'city'}, TOKENS['eastside'])[0], 401)
        # A second proposal while this version awaits approvals is refused.
        self.assertEqual(call('POST', f'{self.core_url}/lots/{LOT}/changes', {'terms': flow_terms, 'organizations': ['city', 'eastside']}, TOKENS['city'])[0], 409)
        # After the planned trip time the version is stale.
        self.clock['now'] = '2026-10-13T16:00:00-07:00'
        status, body = call('POST', self.core_url + '/approvals', {**receipt, 'organization_id': 'eastside', 'receipt_id': 'r-late'}, TOKENS['eastside'])
        self.assertEqual(status, 409)
        self.assertIn('trip time has passed', body['error']['message'])
        self.assertEqual(changes.find(self.engine.records, LOT, 13)['status'], 'awaiting_approvals')

    def test_core_refuses_a_change_before_the_failure_is_recorded_or_moving_produce_that_keeps(self):
        self.flip_switch()
        holding = changes.holding(self.engine, LOT, 'city')
        self.assertEqual(sorted((i['produce_id'], i['pounds']) for i in holding['items']), [('apples', 50.0), ('romaine', 200.0)])
        self.assertNotIn('request_code', json.dumps(holding))
        result = self.handle()
        terms = copy.deepcopy(result['change']['approval_request']['terms'])
        self.engine.records.delete('change', f'{LOT}:13')
        moved_apples = copy.deepcopy(terms)
        moved_apples['moves'].append({**moved_apples['moves'][0], 'produce_id': 'apples', 'pounds': 50})
        moved_apples['staying'] = []
        status, body = call('POST', f'{self.core_url}/lots/{LOT}/changes', {'terms': moved_apples, 'organizations': ['city', 'eastside']}, TOKENS['city'])
        self.assertEqual(status, 409)
        self.assertIn('only cold-dependent produce moves', body['error']['message'])
        bank = self.engine.records.get('bank', 'city')
        bank.pop('cooler')
        with self.engine.records.transaction():
            self.engine.records.put('bank', 'city', bank)
        status, body = call('POST', f'{self.core_url}/lots/{LOT}/changes', {'terms': terms, 'organizations': ['city', 'eastside']}, TOKENS['city'])
        self.assertEqual(status, 409)
        self.assertIn('failed cooler', body['error']['message'])
        self.assertEqual(call('POST', f'{self.core_url}/lots/{LOT}/changes', {'terms': terms, 'organizations': ['city', 'eastside']}, TOKENS['eastside'])[0], 401)

    def test_organization_systems_follow_the_core_records_and_the_switch(self):
        before = {org: self.systems.read(org, 'storage')['data']['cold_available_lb'] for org in ('city', 'rural', 'eastside')}
        self.assertEqual(before, {'city': 50.0, 'rural': 50.0, 'eastside': 150.0})  # city holds 200 lb romaine of 250
        self.assertEqual(self.systems.read('city', 'cooler')['observed_at'], '2026-10-13T22:30:00Z')
        self.flip_switch()
        self.assertEqual(self.systems.read('city', 'storage')['data']['cold_available_lb'], 0)
        self.assertEqual(self.systems.read('city', 'cooler')['data']['temperature_c'], self.fault['reading']['temperature_c'])
        caps = {json.loads(r['annotations']['harvestnet'])['organization_id']: json.loads(r['annotations']['harvestnet'])['capabilities']
                for r in self.directory.search(min_cold_lb=0)['records']}
        self.assertEqual(caps['city']['cold_space_lb'], 0)
        self.assertEqual(self.systems.openapi()['info']['version'], 'synthetic-v1')
        self.assertIn('/systems/city/cooler-failed', self.systems.openapi()['paths'])


class CoolerFailureFixtureChecks(unittest.TestCase):
    def test_lane_a_and_lane_b_rule_checks_pass_on_the_cooler_failure_fixture(self):
        from harvestnet_core.engine import run_fixture
        fixture = json.loads(FIXTURE.read_text())
        core = run_fixture(copy.deepcopy(fixture))['rule_checks']
        self.assertEqual({k for k, v in core.items() if v is not True}, set())
        sys.path.insert(0, os.environ.get('HARVESTNET_PLATFORM_SOURCE', '.'))
        from harvestnet_core.cooler_join import lane_b_harness_checks
        lane_b = lane_b_harness_checks(fixture)
        self.assertEqual(len(lane_b), 6)
        self.assertEqual({k for k, v in lane_b.items() if v is not True}, set())


if __name__ == '__main__':
    unittest.main()
