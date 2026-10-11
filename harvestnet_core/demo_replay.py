"""Record the demo scenario for the offline backup replay (ticket #25).

``python -m harvestnet_core.demo_replay`` runs the real code on the demo scenario and writes:

- ``docs/demo/replay/recording.json``: the recording, as a JSON fixture.
- ``docs/demo/replay.html``: the offline replay page, with the same recording embedded, so the
  page opens from a file with no network.

``--check`` writes nothing and exits 1 if either file differs from what the code produces now.
``core_tests/test_demo_replay.py`` runs the same check.

**What is recorded.** The demo scenario is ``core_fixtures/cooler-failure.json``: the normal
afternoon (a farmers market's mixed lot, three food banks, the advocate, eight scripted
households), then the city cooler failing at 3:30 pm. Everything comes from the code: the
front-desk read-back and consent question (``POST /requests/preview``), the fair share
(``GET /fair-share``), the rules-based negotiation, holds, scripted approvals and the
commitment (``run_fixture``), the household's pickup page (``GET /requests/{code}``),
Workflow 4 (``cooler_join.apply_fault``: Lane C's switch and local Directory, Lane B's flow and
reason cards), the households' new texts (``cooler_join.household_texts``), and the metrics.

**One labeled variant.** In the shipped fixture the eastside manager answers 15 minutes after
being asked, which is exactly when the planned trip arrives, so the core refuses the late answer
and the romaine waits for a human (docs/core/README.md, #10). The live demo has managers approve
on the spot, so the recording uses the same fixture with the eastside manager answering after
10 minutes instead. The recording says so, and it also carries the shipped fixture's own
evaluation, refusal included.

Nothing here decides anything or invents a number (ADR 0002). All data is synthetic.
"""
import argparse
import copy
import json
import os
import sys
from pathlib import Path

from . import changes, cooler_join
from .api import API
from .engine import run_fixture
from .evaluation import evaluate, metrics
from .records import Records

FIXTURE = Path('core_fixtures/cooler-failure.json')
NORMAL_FIXTURE = Path('core_fixtures/normal-afternoon.json')
RECORDING = Path('docs/demo/replay/recording.json')
PAGE = Path('docs/demo/replay.html')
LOT = 'lot-market-1013'
HOUSEHOLD = 'K7P4'  # the parent in demo moment 1: family of 4, Spanish, Watsonville
VARIANT_MINUTES = {'eastside': 10}
HOUSEHOLD_PAGE = 'https://households.example.invalid'
START, END = '<script type="application/json" id="recording">', '</script>'
REQUEST_FIELDS = ('language', 'household_size', 'pickup_windows', 'limited_fridge', 'neighborhood', 'cant_eat', 'snap')
RESULT_FIELDS = ('method', 'status', 'produce_wasted_lb', 'worst_served_coverage', 'households_reached', 'invalid_commitments')


def demo_fixture(fixture):
    """The shipped fixture with the eastside manager's scripted reply time shortened."""
    demo = copy.deepcopy(fixture)
    for human in demo['humans']:
        if human['organization_id'] in VARIANT_MINUTES:
            human['after_minutes'] = VARIANT_MINUTES[human['organization_id']]
    return demo


def _call(api, method, target, body=None):
    status, data = api.call(method, target, body)
    if status >= 400:
        raise RuntimeError(f'{method} {target} returned {status}: {data}')
    return data


def _household(api, request):
    """Demo moment 1 through the web-form path. The voice line uses the same templates."""
    answers = {k: request[k] for k in REQUEST_FIELDS}
    out = {'request_code': request['request_code'], 'channel': request['channel'], 'answers': answers,
           'chosen_food_bank_ids': request['chosen_food_bank_ids'], 'by_language': {}}
    for language in ('es', 'en'):
        preview = _call(api, 'POST', '/requests/preview', {**answers, 'language': language})
        share = _call(api, 'GET', f"/fair-share?household_size={request['household_size']}&language={language}")
        out['by_language'][language] = {'read_back': preview['read_back'], 'consent_question': preview['consent_question'],
                                        'fair_share_lb': preview['fair_share_lb'], 'fair_share_wording': share['wording'],
                                        'table_version': share['table_version'], 'is_placeholder': share['is_placeholder']}
    return out


def _pickup_page(api, code):
    pages = {}
    for language in ('es', 'en'):
        page = _call(api, 'GET', f'/requests/{code}?language={language}')
        pages[language] = {k: page[k] for k in ('fair_share_lb', 'received_this_week_lb')} | {
            'pickups': [{k: p[k] for k in ('food_bank_name', 'window', 'items', 'pounds', 'version', 'wording')} for p in page['pickups']]}
    return pages


def _offer(fixture, profiles, events):
    offer = fixture['surplus_offers'][0]
    # Pounds as the donor agent's version 1 states them (calculators convert sacks to pounds).
    pounds = {i['produce_id']: i['pounds'] for e in events if e['kind'] == 'draft' and e['data'].get('version') == 1
              for i in e['data']['items']}
    donor = next(d for d in fixture['donors'] if d['organization_id'] == offer['donor_id'])
    items = [{'produce_id': i['produce_id'], 'name': profiles.get(i['produce_id']).name,
              'name_es': profiles.get(i['produce_id']).name_es, 'quantity': i['quantity'], 'unit': i['unit'],
              'lb_per_unit': i['lb_per_unit'], 'pounds': pounds[i['produce_id']], 'condition_grade': i['condition_grade'],
              'needs_fridge': profiles.get(i['produce_id']).needs_fridge} for i in offer['items']]
    return {'lot_id': offer['lot_id'], 'donor_id': offer['donor_id'], 'reported_at': offer['reported_at'],
            'deadline': offer['deadline'], 'items': items, 'drop_off': donor.get('drop_off')}


def _negotiation(events):
    """Every move with its reason, and every version the moves created."""
    moves, versions = [], []
    for e in events:
        if e['kind'] == 'move':
            d = e['data']
            moves.append({'sequence': e['sequence'], 'organization_id': d['organization_id'], 'version': d['version'],
                          'action': d['action'], 'reason': d['reason'], 'amendment': d.get('amendment'), 'holds': d.get('holds')})
        elif e['kind'] == 'draft' and e['data'].get('version') == 1:
            versions.append({'sequence': e['sequence'], 'version': 1, 'proposer_id': e['data']['donor_id'], 'amendment': None,
                             'allocations': e['data']['allocations'], 'transports': e['data']['transports']})
        elif e['kind'] == 'amendment':
            d = e['data']
            versions.append({'sequence': e['sequence'], 'version': d['draft']['version'], 'proposer_id': d['organization_id'], 'amendment': d['amendment'],
                             'allocations': d['draft']['allocations'], 'transports': d['draft']['transports']})
    return moves, versions


def _kinds(events, *kinds):
    return [{'sequence': e['sequence'], 'at': e['at'], 'kind': e['kind'], 'data': e['data']} for e in events if e['kind'] in kinds]


def _results(paths):
    out = []
    for path in paths:
        result = evaluate(json.loads(path.read_text(encoding='utf-8')))
        methods = []
        for m in result['methods']:
            row = {k: m.get(k) for k in RESULT_FIELDS}
            if 'cooler_failure' in m:
                row['cooler_failure'] = m['cooler_failure']
            methods.append(row)
        out.append({'scenario_id': result['scenario_id'], 'fixture': path.as_posix(), 'run_mode': result['run_mode'],
                    'synthetic': result['synthetic'], 'note': result['note'], 'methods': methods})
    return out


def record():
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    demo = demo_fixture(fixture)
    request = next(r for r in demo['requests'] if r['request_code'] == HOUSEHOLD)

    # Snapshots on the scenario stopped at its commitment, then through the cooler failure.
    engine, faults, pre_run = cooler_join.run_until_fault(demo)
    try:
        profiles = engine.calc.profiles
        names = dict(engine.names)
        household = _household(API(engine, clock=lambda: request['submitted_at']), request)
        committed_at = next(e['at'] for e in pre_run['events'] if e['kind'] == 'commitment')
        before = _pickup_page(API(engine, clock=lambda: committed_at), HOUSEHOLD)
        fault = faults[0]
        workflow_4 = cooler_join.apply_fault(engine, LOT, fault)
        change = changes.find(engine.records, LOT, workflow_4['version'])
        texts = cooler_join.household_texts(engine, LOT, change['version'], household_page_url=HOUSEHOLD_PAGE)
        after = _pickup_page(API(engine, clock=lambda: change['committed_at']), HOUSEHOLD) if change.get('committed_at') else None
    finally:
        engine.records.close()

    # The whole scenario run as the evaluation runs it: negotiation, failure, replies, metrics.
    records = Records()
    try:
        run = run_fixture(copy.deepcopy(demo), records=records)
        run_metrics = metrics(demo, run, records)
    finally:
        records.close()
    events = run['events']
    moves, versions = _negotiation(events)
    commitment = next(e for e in events if e['kind'] == 'commitment')

    return {
        'kind': 'harvestnet_demo_recording',
        'label': 'Recorded replay',
        'synthetic': True,
        'mode': demo['mode'],
        'generated_by': 'python -m harvestnet_core.demo_replay',
        'fixture': FIXTURE.as_posix(),
        'note': ('A recorded run of the real code on synthetic, scripted data. Rules-based negotiators; the LLM negotiators '
                 'were not run. Scripted humans stand in for each organization\'s manager. Not a live run.'),
        'variant': {
            'description': ('Same as the shipped fixture, except the eastside manager answers approval requests after 10 '
                            'minutes instead of 15. With the shipped 15 minutes, the answer to the cooler change arrives '
                            'when the planned trip is due, the core refuses it, and the romaine waits for a human. That '
                            'outcome is in results.shipped below.'),
            'humans': demo['humans'],
        },
        'organizations': names,
        'fair_share_table_version': demo['policies']['fair_share_table_version'],
        'household': household,
        'offer': _offer(demo, profiles, events),
        'negotiation': {'moves': moves, 'versions': versions},
        'holds': _kinds(events, 'owner_hold'),
        'approvals': _kinds(events, 'human_decision'),
        'commitment': {'sequence': commitment['sequence'], 'at': commitment['at'], 'version': commitment['data']['version'],
                       'terms_hash': commitment['data']['terms_hash'], 'allocations': commitment['data']['allocations']},
        'pickup_notices': [e['data'] for e in events if e['kind'] == 'pickup_notice'],
        'household_page_before': before,
        'cooler_failure': {
            'fault': fault,
            'events': _kinds(events, 'cooler_failure', 'change_proposed', 'change_decision', 'change_refused',
                             'change_commitment', 'pickup_held_for_human'),
            'dashboard': change['dashboard'],
            'terms': change['terms'],
            'status': change['status'],
            'moved_pickups': change.get('moved_pickups', []),
            'summary': workflow_4,
        },
        'household_texts': texts,
        'household_page_after': after,
        'pickup_outcomes': _kinds(events, 'pickup_confirmation', 'pickup_released'),
        'metrics': run_metrics,
        'results': {'shipped': _results([NORMAL_FIXTURE, FIXTURE])},
    }


def render(recording):
    """The two files' contents: the JSON fixture, and the page with the recording embedded."""
    text = json.dumps(recording, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    page = PAGE.read_text(encoding='utf-8')
    start = page.index(START) + len(START)
    end = page.index(END, start)
    embedded = '\n' + json.dumps(recording, ensure_ascii=False, allow_nan=False).replace('</', '<\\/') + '\n'
    return text, page[:start] + embedded + page[end:]


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m harvestnet_core.demo_replay', description=__doc__.split('\n\n')[0])
    parser.add_argument('--check', action='store_true', help='write nothing; exit 1 if the saved recording is stale')
    args = parser.parse_args(argv)
    # The cooler failure reads Lane C's organization systems in process.
    sys.path.insert(0, os.environ.get('HARVESTNET_PLATFORM_SOURCE', '.'))
    text, page = render(record())
    stale = [p.as_posix() for p, new in ((RECORDING, text), (PAGE, page)) if not p.exists() or p.read_text(encoding='utf-8') != new]
    if args.check:
        print('stale: ' + ', '.join(stale) if stale else 'recording matches the code')
        return 1 if stale else 0
    RECORDING.parent.mkdir(parents=True, exist_ok=True)
    RECORDING.write_text(text, encoding='utf-8')
    PAGE.write_text(page, encoding='utf-8')
    print(f'Wrote {RECORDING} and {PAGE} (synthetic, recorded replay)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
