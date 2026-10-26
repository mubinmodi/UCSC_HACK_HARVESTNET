"""Lane A follow-ups for #8, #9, #10 and #22, each written as a failing test first.

All data is synthetic. No paid API is called: the Claude extractor tests use a fake client.
"""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from importlib import resources
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from harvestnet_core.api import API
from harvestnet_core.engine import Engine, run_fixture
from harvestnet_core.evaluation import evaluate, metrics
from harvestnet_core.protocol import dt
from harvestnet_core.records import Records
from harvestnet_agents.profiles import load_profiles

from test_core import fixture

# The cooler-failure scenario reads Lane C's organization systems in process.
sys.path.insert(0, os.environ.get('HARVESTNET_PLATFORM_SOURCE', '.'))

NOW = '2026-10-13T12:00:00-07:00'
TOKENS = {'market': 'donor-test', 'city': 'city-test'}
BAD_REASON = 'Owner claims 999999 lb'


def flaky_rules(real, failures):
    """Wrap the real rules negotiators so their first ``failures`` reasons fail the number check."""
    left = {'n': failures}

    class Flaky:
        def __init__(self, inner):
            self.inner = inner

        def move(self, typed):
            move = self.inner.move(typed).to_dict()
            if left['n'] > 0:
                left['n'] -= 1
                move = {**move, 'reason': BAD_REASON}
            return SimpleNamespace(to_dict=lambda: copy.deepcopy(move))
    return lambda role, org: Flaky(real(role, org))


def kinds(records, lot_id):
    return [e['kind'] for e in records.events(lot_id)]


class NumberCheckFallbackTests(unittest.TestCase):
    """#8: re-ask once, then the template after the second failure; every failure counted."""

    def offer(self, failures):
        engine = Engine(fixture())
        engine.rules_for = flaky_rules(engine.rules_for, failures)
        api = API(engine, clock=lambda: NOW, staff_tokens=TOKENS)
        status, created = api.call('POST', '/surplus-offers', copy.deepcopy(engine.fixture['surplus_offers'][0]), token='donor-test')
        self.assertEqual(status, 201, created)
        return engine.records, created['lot_id']

    def test_api_path_reasks_after_one_failure(self):
        records, lot_id = self.offer(1)
        self.assertEqual(records.get('lot', lot_id)['number_check_failures'], 1)
        self.assertNotIn('template_fallback', kinds(records, lot_id))
        first = next(e['data'] for e in records.events(lot_id) if e['kind'] == 'move')
        self.assertNotEqual(first['reason'], BAD_REASON)
        self.assertNotIn('fallback', first['reason'])  # the re-asked owner's own reason, not the template

    def test_api_path_uses_template_after_two_failures(self):
        records, lot_id = self.offer(2)
        events = records.events(lot_id)
        self.assertEqual(records.get('lot', lot_id)['number_check_failures'], 2)
        self.assertEqual(sum(e['data']['count'] for e in events if e['kind'] == 'number_check_failure'), 2)
        self.assertEqual(kinds(records, lot_id).count('template_fallback'), 1)
        first = next(e['data'] for e in events if e['kind'] == 'move')
        self.assertIn('fallback', first['reason'])

    def test_harness_without_a_provider_also_reasks_before_the_template(self):
        for failures, templates in ((1, 0), (2, 1)):
            with self.subTest(failures=failures):
                real = Engine.rules_for
                state = {}

                def patched(self, role, org):
                    if 'wrap' not in state:
                        state['wrap'] = flaky_rules(lambda r, o: real(self, r, o), failures)
                    return state['wrap'](role, org)
                records = Records()
                with mock.patch.object(Engine, 'rules_for', patched):
                    run = run_fixture(fixture(), records=records)
                lot_id = fixture()['surplus_offers'][0]['lot_id']
                self.assertEqual(records.get('lot', lot_id)['number_check_failures'], failures)
                self.assertEqual(kinds(records, lot_id).count('template_fallback'), templates)
                self.assertTrue(run['rule_checks']['number_check_failures_counted'])
                first = next(e['data'] for e in records.events(lot_id) if e['kind'] == 'move')
                self.assertEqual('fallback' in first['reason'], bool(templates))


class LimitedFridgeRuleTests(unittest.TestCase):
    """#8: the same-day rule for limited-fridge households follows the profile's needs-fridge field."""

    def test_needs_fridge_not_cold_chain_sets_the_same_day_rule(self):
        data = json.loads(resources.files('harvestnet_agents').joinpath('data', 'produce_profiles.json').read_text())
        apples = next(p for p in data['profiles'] if p['id'] == 'apples')
        apples['transport_temperature']['value']['cold_required'] = True  # cold chain, but no household fridge needed
        engine = Engine(fixture())
        engine.calc.profiles = load_profiles(data)
        self.assertTrue(engine.calc.profiles.get('apples').needs_cold)
        self.assertFalse(engine.calc.profiles.get('apples').needs_fridge)
        every_day = [{'days': ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], 'start': '00:00', 'end': '23:59'}]
        request = {'chosen_food_bank_ids': ['city'], 'cant_eat': [], 'limited_fridge': True, 'pickup_windows': every_day,
                   'expires_at': '2026-10-20T00:00:00-07:00'}
        bank = {'organization_id': 'city', 'pickup_windows': [{'start': '2026-10-14T18:00:00-07:00', 'end': '2026-10-14T20:00:00-07:00'}]}
        arrival = dt('2026-10-13T14:00:00-07:00')
        later = '2026-10-30T00:00:00-07:00'
        engine.now = NOW
        self.assertIsNotNone(engine.eligible(request, bank, {'produce_id': 'apples', 'usable_until': later}, arrival))
        self.assertIsNone(engine.eligible(request, bank, {'produce_id': 'romaine', 'usable_until': later}, arrival))
        self.assertIsNotNone(engine.eligible({**request, 'limited_fridge': False}, bank, {'produce_id': 'romaine', 'usable_until': later}, arrival))


class PublicAPITests(unittest.TestCase):
    def setUp(self):
        self.f = fixture()
        self.engine = Engine(self.f)
        self.api = API(self.engine, clock=lambda: NOW, staff_tokens=TOKENS)
        self.offer = copy.deepcopy(self.f['surplus_offers'][0])

    def test_root_lists_every_contract_operation(self):
        status, body = self.api.call('GET', '/')
        self.assertEqual(status, 200, body)
        self.assertEqual(body['contract_version'], 'contract-v0.2')
        agreed = {p.stem for p in Path('docs/contracts/examples/public-api').glob('*.json')}
        listed = {o['operation'] for o in body['operations']}
        self.assertTrue(agreed <= listed, agreed - listed)
        self.assertTrue(all(o['method'] and o['path'].startswith('/') for o in body['operations']))

    def test_unknown_produce_is_bad_input(self):
        self.offer['items'][0]['produce_id'] = 'durian'
        status, body = self.api.call('POST', '/surplus-offers', self.offer, token='donor-test')
        self.assertEqual(status, 400, body)
        self.assertEqual(body['error']['code'], 'bad_request')

    def test_missing_body_field_is_bad_input_not_missing_record(self):
        del self.offer['deadline']
        status, body = self.api.call('POST', '/surplus-offers', self.offer, token='donor-test')
        self.assertEqual(status, 400, body)
        self.assertEqual(self.api.call('GET', '/lots/no-such-lot')[0], 404)

    def test_offer_drop_off_applies_to_that_offer_only(self):
        default = copy.deepcopy(self.engine.donors['market']['drop_off'])
        status, first = self.api.call('POST', '/surplus-offers', {**self.offer, 'drop_off': {'can_drop_off': False}}, token='donor-test')
        self.assertEqual(status, 201, first)
        self.assertEqual(self.engine.donors['market']['drop_off'], default)
        self.assertEqual(self.engine.records.get('lot', first['lot_id'])['draft']['drop_off_to'], [])
        status, second = self.api.call('POST', '/surplus-offers', self.offer, token='donor-test')
        self.assertEqual(status, 201, second)
        self.assertEqual(self.engine.records.get('lot', second['lot_id'])['draft']['drop_off_to'], default['food_bank_ids'])
        # The offer's own drop-off is recorded with that lot and survives a restart.
        restarted = Engine(self.f, self.engine.records)
        self.assertIsNone(restarted.drop_off(first['lot_id']))
        self.assertEqual(restarted.drop_off(second['lot_id']), default)
        bad = {**self.offer, 'drop_off': {**default, 'food_bank_ids': ['nowhere']}}
        self.assertEqual(self.api.call('POST', '/surplus-offers', bad, token='donor-test')[0], 400)

    def test_usable_life_comes_from_the_profile_and_stays_labeled(self):
        del self.offer['items'][0]['usable_until']  # as in the contract's create_surplus_offer example
        status, created = self.api.call('POST', '/surplus-offers', self.offer, token='donor-test')
        self.assertEqual(status, 201, created)
        profiles = self.engine.calc.profiles
        apples = profiles.get('apples')
        item = self.engine.records.get('lot', created['lot_id'])['draft']['items'][0]
        self.assertEqual(dt(item['usable_until']), dt(NOW) + timedelta(days=apples.days_usable_room.min))
        [basis] = [i['usable_until_basis'] for i in created['items']]
        self.assertEqual(basis['kind'], 'profile_assumption')
        self.assertEqual((basis['field'], basis['days'], basis['profile_set_version']), ('days_usable_room', apples.days_usable_room.min, profiles.version))
        status, lot = self.api.call('GET', '/lots/' + created['lot_id'])
        self.assertEqual(lot['items'][0]['usable_until_basis'], basis)

    def test_use_soon_needs_the_donors_own_usable_time(self):
        self.offer['items'][0]['condition_grade'] = 'use_soon'
        del self.offer['items'][0]['usable_until']
        status, body = self.api.call('POST', '/surplus-offers', self.offer, token='donor-test')
        self.assertEqual(status, 400, body)
        self.assertIn('usable_until', body['error']['message'])
        self.offer['items'][0]['usable_until'] = '2026-10-13T22:00:00-07:00'
        status, created = self.api.call('POST', '/surplus-offers', self.offer, token='donor-test')
        self.assertEqual(status, 201, created)
        self.assertEqual(created['items'][0]['usable_until_basis']['kind'], 'donor_condition_check')


def example(operation):
    return json.loads(Path(f'docs/contracts/examples/public-api/{operation}.json').read_text())


class EveryOperationShapeTests(unittest.TestCase):
    """#9: every agreed operation, called for real, answers with the example's status and fields."""

    def check(self, operation, status, body):
        response = example(operation)['example']['response']
        self.assertEqual(status, response['status'], (operation, body))
        self.assertNotEqual(body['mode'], 'example')
        self.assertTrue(set(response['body']) <= set(body), (operation, set(response['body']) - set(body)))
        for key, value in response['body'].items():
            # One level down too: the first item of each list, and each nested object.
            if isinstance(value, list) and value and isinstance(value[0], dict) and body[key]:
                self.assertTrue(set(value[0]) <= set(body[key][0]), (operation, key, set(value[0]) - set(body[key][0])))
            if isinstance(value, dict) and isinstance(body[key], dict):
                self.assertTrue(set(value) <= set(body[key]), (operation, key, set(value) - set(body[key])))
        return body

    def test_every_operation_matches_its_example(self):
        from harvestnet_core.live_evaluation import publish_evaluation
        from harvestnet_core.protocol import terms_hash
        f = fixture()
        f['household_replies'] = []
        engine = Engine(f)
        clock = {'now': NOW}
        data = json.loads(Path('agents/tests/fixtures/front_desk/en_complete.json').read_text())
        api = API(engine, clock=lambda: clock['now'], staff_tokens=TOKENS, extractor=lambda t: data['extractor_output'])
        call = lambda op, target, body=None, token=None: self.check(op, *api.call(example(op)['method'], target, body, token))
        done = set()

        def run(op, target, body=None, token=None):
            done.add(op)
            return call(op, target, body, token)
        form = {k: f['requests'][0][k] for k in ('household_size', 'pickup_windows', 'limited_fridge', 'neighborhood', 'cant_eat', 'snap', 'language')}
        run('get_health', '/health')
        run('get_fair_share', '/fair-share?household_size=4&language=en')
        run('preview_request', '/requests/preview', form)
        code = run('create_request', '/requests', {**form, 'household_size': 3, 'consent': True, 'channel': 'web', 'email': 'household@example.invalid'})['request_code']
        run('list_food_banks', '/food-banks?request_code=' + code)
        run('choose_food_banks', f'/requests/{code}/food-banks', {'food_bank_ids': ['city']})
        run('list_produce_profiles', '/produce-profiles')
        run('voice_intake', '/voice-intake', {'transcript': data['transcript'], 'call_id': 'recorded'})
        lot_id = run('create_surplus_offer', '/surplus-offers', copy.deepcopy(f['surplus_offers'][0]), 'donor-test')['lot_id']
        run('get_lot', '/lots/' + lot_id)
        run('list_lot_versions', f'/lots/{lot_id}/versions')
        run('list_approvals', '/approvals?organization_id=city', None, 'city-test')
        d = engine.records.get('lot', lot_id)['draft']
        for owner, token in (('market', 'donor-test'), ('city', 'city-test')):
            run('record_approval', '/approvals', {'lot_id': lot_id, 'version': d['version'], 'organization_id': owner,
                                                  'terms_hash': terms_hash(d), 'decision': 'approve', 'receipt_id': 'shape-' + owner}, token)
        pickups = [p for p in engine.records.all('pickup') if p['status'] == 'committed']
        self.assertTrue(pickups)
        first = pickups[0]
        run('get_request', '/requests/' + first['request_code'])
        run('get_food_bank_dashboard', '/food-banks/city/dashboard', None, 'city-test')
        clock['now'] = first['window']['start']
        run('confirm_pickup', '/pickup-confirmations', {'food_bank_id': 'city', 'request_code': first['request_code']}, 'city-test')
        status = example('update_food_bank_status')['example']['request']['body']
        run('update_food_bank_status', '/food-banks/city/status', status, 'city-test')
        clock['now'] = NOW
        second = run('create_surplus_offer', '/surplus-offers', copy.deepcopy(f['surplus_offers'][0]), 'donor-test')['lot_id']
        v = engine.records.get('lot', second)['draft']['version']
        run('submit_counter', f'/lots/{second}/counters', {'organization_id': 'city', 'version': v, 'reason': 'Owner asks for less',
                                                          'amendment': {'kind': 'set_pounds', 'produce_id': 'apples', 'food_bank_id': 'city', 'pounds': 2}}, 'city-test')
        publish_evaluation(f, engine.records)
        run('get_results', '/results?scenario_id=' + f['scenario_id'])
        # Release, on a separate run that leaves a pickup open.
        records = Records()
        run_fixture(fixture() | {'household_replies': []}, records=records)
        other = API(Engine(fixture(), records), clock=lambda: '2026-10-13T18:00:00-07:00')
        p = records.all('pickup')[0]
        done.add('release_pickup')
        self.check('release_pickup', *other.call('POST', f"/pickups/{p['pickup_id']}/release", {'request_code': p['request_code']}))
        self.assertEqual(done, {p.stem for p in Path('docs/contracts/examples/public-api').glob('*.json')})


class ApprovalPayloadTests(unittest.TestCase):
    """The approval relay takes the agreed payload (README decision 8) and nothing older.

    Lane C's bridge has sent ``lot_id``, the donor's organization ID and the ``sha256:`` hash
    since PR #56, so the core no longer translates ``event_id``, the role ``donor`` or a bare hex
    hash. The one place that still accepts a bare hex hash is the platform's own inbound
    ``ApprovalStore.decide`` (tests/test_approvals.py)."""

    def offer(self):
        from harvestnet_core.protocol import terms_hash
        engine = Engine(fixture())
        api = API(engine, clock=lambda: NOW, staff_tokens=TOKENS)
        status, created = api.call('POST', '/surplus-offers', copy.deepcopy(engine.fixture['surplus_offers'][0]), token='donor-test')
        self.assertEqual(status, 201, created)
        d = engine.records.get('lot', created['lot_id'])['draft']
        return engine, api, d, terms_hash(d)

    def test_the_agreed_payload_records_the_decision(self):
        engine, api, d, digest = self.offer()
        body = {'lot_id': d['lot_id'], 'version': d['version'], 'organization_id': 'market', 'terms_hash': digest,
                'decision': 'approve', 'receipt_id': 'r-new'}
        status, result = api.call('POST', '/approvals', body, token='donor-test')
        self.assertEqual(status, 200, result)
        self.assertEqual((result['lot_id'], result['organization_id'], result['terms_hash']), (d['lot_id'], 'market', digest))
        self.assertEqual(result['approved_by'], ['market'])

    def test_older_payload_shapes_are_refused_and_record_nothing(self):
        engine, api, d, digest = self.offer()
        older = {
            'event_id instead of lot_id': {'event_id': d['lot_id'], 'version': d['version'], 'organization_id': 'market', 'terms_hash': digest, 'decision': 'approve'},
            'the role donor instead of the donor id': {'lot_id': d['lot_id'], 'version': d['version'], 'organization_id': 'donor', 'terms_hash': digest, 'decision': 'approve'},
            'a bare hex hash': {'lot_id': d['lot_id'], 'version': d['version'], 'organization_id': 'market', 'terms_hash': digest.removeprefix('sha256:'), 'decision': 'approve'},
        }
        for name, body in older.items():
            with self.subTest(name):
                status, result = api.call('POST', '/approvals', body, token='donor-test')
                self.assertIn(status, (400, 401, 409), result)
        self.assertEqual(engine.records.get('lot', d['lot_id'])['approvals'], {})


class ResultsTests(unittest.TestCase):
    """#9/#10: an evaluation run stores what /results returns."""

    def test_cli_evaluation_is_served_by_results(self):
        from harvestnet_core.__main__ import main
        path = 'core_fixtures/normal-afternoon.json'
        f = json.loads(Path(path).read_text())
        with tempfile.TemporaryDirectory() as folder:
            db = str(Path(folder) / 'core.sqlite')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(['evaluate', path, '--database', db, '--output', str(Path(folder) / 'replays')])
            printed = json.loads(out.getvalue())
            records = Records(db)
            try:
                api = API(Engine(f, records), clock=lambda: f['clock']['start'])
                status, body = api.call('GET', '/results?scenario_id=' + f['scenario_id'])
                self.assertEqual(status, 200, body)
                self.assertEqual(body['methods'], printed[0]['methods'])
                example = json.loads(Path('docs/contracts/examples/public-api/get_results.json').read_text())['example']['response']['body']
                self.assertTrue(set(example) <= set(body))
                for method in body['methods']:
                    self.assertTrue(set(example['methods'][0]) <= set(method))
                self.assertEqual((body['run_mode'], body['synthetic']), ('synthetic', True))
                self.assertEqual([m['status'] for m in body['methods']], ['completed', 'completed', 'completed', 'not_run'])
                self.assertFalse(body['methods'][3]['measured'])
                self.assertEqual(api.call('GET', '/results?scenario_id=never-run')[0], 404)
                self.assertEqual(api.call('GET', '/results')[0], 400)
            finally:
                records.close()


def request(code, banks, received, share=4):
    return {'request_code': code, 'chosen_food_bank_ids': banks, 'received_this_week_lb': received, 'fair_share_lb': share,
            'household_size': 1, 'expires_at': '2026-10-20T00:00:00-07:00'}


class WorstServedTests(unittest.TestCase):
    """#10, design section 16: the lowest average coverage across food banks, zeros included."""

    def test_worst_served_is_the_lowest_food_bank_average(self):
        f = {'food_banks': [{'organization_id': 'a'}, {'organization_id': 'b'}, {'organization_id': 'empty'}],
             'surplus_offers': [], 'clock': {'start': NOW}}
        records = Records()
        with records.transaction():
            for r in (request('A1', ['a'], 4), request('A0', ['a'], 0), request('B1', ['b'], 1), request('B2', ['b'], 1)):
                records.put('request', r['request_code'], r)
        m = metrics(f, {'events': [], 'rule_checks': {}}, records)
        self.assertEqual(m['worst_served_coverage'], 0.25)  # b averages 0.25; a averages 0.5 despite one household at 0
        self.assertEqual(m['coverage_by_food_bank'], {'a': 0.5, 'b': 0.25})

    def test_pickup_window_match_counts_pounds_collected_before_the_usable_time(self):
        f = {'food_banks': [{'organization_id': 'a'}], 'surplus_offers': [], 'clock': {'start': NOW}}
        records = Records()
        lot = {'draft': {'lot_id': 'L', 'items': [{'produce_id': 'romaine', 'pounds': 4, 'usable_until': '2026-10-14T12:00:00-07:00'}]}}
        with records.transaction():
            records.put('lot', 'L', lot)
            for pid, lb in (('early', 3), ('late', 1)):
                records.put('pickup', pid, {'pickup_id': pid, 'lot_id': 'L', 'status': 'collected', 'pounds': lb, 'request_code': pid,
                                            'items': [{'produce_id': 'romaine', 'pounds': lb}], 'window': {}})
        events = [{'kind': 'pickup_confirmation', 'at': '2026-10-13T18:00:00-07:00', 'data': {'pickup_id': 'early'}},
                  {'kind': 'pickup_confirmation', 'at': '2026-10-14T18:00:00-07:00', 'data': {'pickup_id': 'late'}}]
        self.assertEqual(metrics(f, {'events': events, 'rule_checks': {}}, records)['pickup_window_match'], 0.75)
        self.assertIsNone(metrics(f, {'events': [], 'rule_checks': {}}, Records())['pickup_window_match'])

    def test_metric_differs_between_scenarios_and_methods(self):
        values = set()
        for path in sorted(Path('core_fixtures').glob('*.json')):
            for m in evaluate(json.loads(path.read_text()))['methods'][:3]:
                values.add(m['worst_served_coverage'])
        self.assertGreater(len(values), 1, values)


class MidRunCoolerFailureTests(unittest.TestCase):
    """#10/#23: agents don't see the cooler fault before it happens; Workflow 4 runs at its time."""

    def setUp(self):
        self.f = json.loads(Path('core_fixtures/cooler-failure.json').read_text())
        self.fault = self.f['faults'][0]
        self.failing = self.fault['food_bank_id']

    def prompt_humans(self):
        """The same scenario with the receiving food bank's human answering within the trip time."""
        f = copy.deepcopy(self.f)
        for h in f['humans']:
            h['after_minutes'] = min(h['after_minutes'], 5)
        return f

    def test_engine_does_not_forecast_the_fault(self):
        bank = Engine(self.f).records.get('bank', self.failing)
        self.assertTrue(all(s['cold_free_lb'] > 0 for s in bank['storage']))

    def test_the_plan_is_committed_without_foresight(self):
        records = Records()
        run = run_fixture(copy.deepcopy(self.f), records=records)
        profiles = Engine(self.f, records).calc.profiles
        first = next(e for e in run['events'] if e['kind'] == 'commitment')
        self.assertTrue(any(a['food_bank_id'] == self.failing and profiles.get(a['produce_id']).needs_cold for a in first['data']['allocations']))
        self.assertLess(dt(first['at']), dt(self.fault['at']))
        self.assertEqual(records.get('bank', self.failing)['cooler']['status'], 'failed')

    def test_a_late_human_answer_commits_nothing_and_holds_cold_pickups_for_a_human(self):
        # The fixture's scripted eastside human answers 15 minutes after being asked, which is
        # the planned trip's arrival time, so the core refuses it as stale. Reported, not hidden.
        records = Records()
        run = run_fixture(copy.deepcopy(self.f), records=records)
        found = [e['kind'] for e in run['events']]
        self.assertIn('change_proposed', found)
        self.assertIn('change_refused', found)
        self.assertNotIn('change_commitment', found)
        [fault] = run['faults']
        self.assertEqual((fault['handling'], fault['change_status']), ('mid_run_workflow_4', 'awaiting_approvals'))
        self.assertIn('trip time has passed', fault['refusals'][0]['reason'])
        held = [p for p in records.all('pickup') if p['status'] == 'held_for_human']
        self.assertTrue(held)
        self.assertAlmostEqual(sum(p['pounds'] for p in held), fault['held_for_human_lb'])
        self.assertTrue(all(p['food_bank_id'] == self.failing for p in held))
        self.assertTrue(all(run['rule_checks'].values()), run['rule_checks'])

    def test_prompt_human_answers_commit_the_change_with_fresh_approvals(self):
        records = Records()
        run = run_fixture(self.prompt_humans(), records=records)
        profiles = Engine(self.f, records).calc.profiles
        change = next(e for e in run['events'] if e['kind'] == 'change_commitment')
        self.assertGreaterEqual(dt(change['at']), dt(self.fault['at']))
        self.assertTrue(all(run['rule_checks'].values()), run['rule_checks'])
        for name in ('only_cold_dependent_items_move', 'failed_cooler_holds_nothing_cold', 'household_pickups_follow_new_version'):
            self.assertIn(name, run['rule_checks'])
        # After the change, cold produce at the failed cooler is only the same-day fallback.
        at_failing = [c for c in run['commitments'] if c['food_bank_id'] == self.failing and profiles.get(c['produce_id']).needs_cold]
        self.assertTrue(all(c.get('pathway') for c in at_failing), at_failing)
        self.assertEqual(run['faults'][0]['change_status'], 'committed')

    def test_a_fault_before_the_offer_is_a_current_fact_for_every_agent(self):
        f = copy.deepcopy(self.f)
        f['faults'][0]['at'] = '2026-10-13T11:30:00-07:00'  # before the lot is reported
        self.assertLess(dt(f['faults'][0]['at']), dt(f['surplus_offers'][0]['reported_at']))
        records = Records()
        run = run_fixture(f, records=records)
        profiles = Engine(f, records).calc.profiles
        self.assertEqual(run['faults'][0]['handling'], 'before_offer_status')
        self.assertFalse([c for c in run['commitments'] if c['food_bank_id'] == self.failing and profiles.get(c['produce_id']).needs_cold])
        self.assertTrue(all(run['rule_checks'].values()), run['rule_checks'])

    def test_evaluation_reports_workflow_4_for_every_method(self):
        for f, committed in ((self.f, 0), (self.prompt_humans(), 1)):
            result = evaluate(copy.deepcopy(f))
            self.assertIn('cooler failure', result['note'])
            for m in result['methods'][:3]:
                with self.subTest(method=m['method'], committed=committed):
                    self.assertEqual(m['invalid_commitments'], 0)
                    report = m['cooler_failure']
                    self.assertEqual((report['faults'], report['handling']), (1, 'mid_run_workflow_4'))
                    self.assertEqual(report['changes_committed'], committed)
                    self.assertEqual(report['pounds_moved'] > 0, bool(committed))
                    self.assertEqual(report['held_for_human_lb'] > 0, not committed)

    def test_replay_reproduces_the_mid_run_change(self):
        from harvestnet_core.evaluation import replay
        with tempfile.TemporaryDirectory() as folder:
            evaluate(self.prompt_humans(), output=folder)
            path = next(Path(folder).glob('*rules_based*.json'))
            run = replay(path)
            self.assertIn('change_commitment', [e['kind'] for e in run['events']])


class PrivacyPurgeTests(unittest.TestCase):
    """Design section 12: an expired request leaves only counts in the event log."""

    def test_expired_request_is_removed_from_events(self):
        f = fixture()
        f['household_replies'] = []
        records = Records()
        run_fixture(f, records=records)
        lot_id = f['surplus_offers'][0]['lot_id']
        notices = [e for e in records.events(lot_id) if e['kind'] == 'pickup_notice']
        self.assertTrue(notices)
        self.assertIn('TEST1', json.dumps([e['data'] for e in notices]))
        expires = records.get('request', 'TEST1')['expires_at']
        api = API(Engine(f, records), clock=lambda: (dt(expires) + timedelta(minutes=1)).isoformat())
        self.assertEqual(api.call('GET', '/health')[0], 200)
        everything = json.dumps([e['data'] for e in records.events(lot_id)])
        self.assertNotIn('TEST1', everything)
        after = [e for e in records.events(lot_id) if e['kind'] == 'pickup_notice']
        self.assertEqual(len(after), len(notices))
        self.assertEqual([e['data']['pounds'] for e in after], [e['data']['pounds'] for e in notices])
        self.assertTrue(all(e['data']['request_code'] is None and e['data']['window'] is None for e in after))
        self.assertEqual(records.all('pickup'), [])


def fake_claude(output, calls):
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=json.dumps(output))])
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))


class VoiceIntakeLimitTests(unittest.TestCase):
    """#22: voice intake has a per-process rate limit and a capped Claude extractor."""

    def setUp(self):
        self.data = json.loads(Path('agents/tests/fixtures/front_desk/en_complete.json').read_text())
        self.engine = Engine(fixture())
        self.body = {'transcript': self.data['transcript'], 'call_id': 'recorded'}

    def test_rate_limit_per_process(self):
        clock = {'t': 0.0}
        api = API(self.engine, clock=lambda: NOW, extractor=lambda t: self.data['extractor_output'],
                  voice_rate_limit=(2, 60), monotonic=lambda: clock['t'])
        self.assertEqual(api.call('POST', '/voice-intake', self.body)[0], 200)
        self.assertEqual(api.call('POST', '/voice-intake', self.body)[0], 200)
        status, body = api.call('POST', '/voice-intake', self.body)
        self.assertEqual((status, body['error']['code']), (503, 'rate_limited'))
        clock['t'] = 61.0
        self.assertEqual(api.call('POST', '/voice-intake', self.body)[0], 200)

    def test_claude_extractor_requires_a_spending_cap(self):
        from harvestnet_agents.front_desk import ClaudeExtractor
        from harvestnet_core.voice import CappedExtractor
        calls = []
        claude = ClaudeExtractor(client=fake_claude(self.data['extractor_output'], calls))
        with self.assertRaises(ValueError):
            API(self.engine, extractor=claude)
        with self.assertRaises(ValueError):
            CappedExtractor(claude, limit_usd=1)  # paid calls need explicit authorization
        with self.assertRaises(ValueError):
            CappedExtractor(claude, limit_usd=101, allow_paid=True)
        capped = CappedExtractor(claude, limit_usd=1, allow_paid=True)
        api = API(self.engine, clock=lambda: NOW, extractor=capped)
        status, body = api.call('POST', '/voice-intake', self.body)
        self.assertEqual(status, 200, body)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(capped.cap.entries), 1)  # one call logged against the shared cap (actual usage)
        self.assertIs(claude.cap, capped.cap)
        self.assertLessEqual(capped.cap.spent_usd, 1)
        # Once the next call's worst case no longer fits, no call is made.
        capped.cap.limit_usd = capped.cap.spent_usd
        status, body = api.call('POST', '/voice-intake', self.body)
        self.assertEqual((status, body['error']['code']), (503, 'spending_cap_reached'))
        self.assertEqual(len(calls), 1)

    def test_zero_cap_never_calls_claude(self):
        from harvestnet_agents.front_desk import ClaudeExtractor
        from harvestnet_core.voice import CappedExtractor
        calls = []
        api = API(self.engine, clock=lambda: NOW, extractor=CappedExtractor(ClaudeExtractor(client=fake_claude({}, calls)), limit_usd=0))
        self.assertEqual(api.call('POST', '/voice-intake', self.body)[0], 503)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
