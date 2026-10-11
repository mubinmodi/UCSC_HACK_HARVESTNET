"""Cooler failure end to end, run locally (#23 join, Workflow 4).

This wires the three lanes together without changing any of their decisions:

- Lane C's organization systems and demo cooler switch (``harvestnet_platform.systems``)
  serve the core scenario's day (``organization_systems``, ``ScenarioSystems``). Lane C's
  Directory (``LocalDirectory`` or ``AgntcyDirectory``) does the rediscovery.
- The failing food bank's own agent (``handle_cooler_reading``) reads its own systems,
  gets its committed holding and recorded route minutes from the core, asks each
  candidate food bank for its own answer, and runs Lane B's ``run_cooler_failure_flow``.
  It records the failed cooler in its food bank status and proposes the new version to the
  core (``harvestnet_core.changes``). It never approves or commits.
- Lane C's approval bridge issues each named organization's review link. Each human's
  decision goes to the core's ``/approvals`` with that organization's own credential
  (``OrganizationCoreAPI``). Only every named approval commits the new version.
- ``household_texts`` builds the affected households' texts with Lane B's wording, from
  the core's pickups, after commitment. The core adds ``to``, ``pickup_id`` and
  ``release_url``. Lane C's ``/notifications/prepare`` turns them into n8n text bodies.

Nothing here decides for an organization (ADR 0001, 0004). Every number comes from a
reading, a record, a calculator or a profile (ADR 0002). All data is synthetic.
Interfaces added here are **proposed**, pending ticket #1.
"""
import argparse
import copy
import json
from datetime import timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from zoneinfo import ZoneInfo

from harvestnet_agents.cooler_failure import PickupWindow
from harvestnet_agents.cooler_failure_flow import NewVersion, household_change_notices, read_cooler_signal, run_cooler_failure_flow
from harvestnet_agents.cooler_failure_flow import terms_hash as lane_b_terms_hash
from harvestnet_agents.negotiation import parse_facts

from . import changes
from .engine import Engine, run_fixture
from .protocol import dt
from .records import Records


class CoreError(ValueError):
    def __init__(self, status, body):
        super().__init__(f'core API {status}: {body}')
        self.status, self.body = status, body


def _json(url, body=None, *, token=None, method=None):
    from harvestnet_platform.http import request_json
    try:
        return request_json(url, body, token=token, method=method)
    except HTTPError as exc:
        raise CoreError(exc.code, json.loads(exc.read() or b'{}')) from exc


# --- The core scenario up to its fault ------------------------------------------------------


def run_until_fault(fixture, records=None):
    """Run the core fixture to its commitment, before its scripted faults and household replies.

    The fixture's own run applies the cooler failure before negotiating (a forecast); here
    the failure arrives mid-run, after commitment and delivery, through Lane C's switch.
    """
    pre = copy.deepcopy(fixture)
    faults = pre.get('faults', [])
    pre['faults'], pre['household_replies'] = [], []
    records = records or Records()
    run = run_fixture(pre, records=records)
    return Engine(pre, records), faults, run


# --- Lane C organization systems for the scenario's day ------------------------------------


def _truck(truck):
    if not truck:
        return {'available': False, 'capacity_lb': 0, 'refrigerated': False, 'windows': []}
    return {'available': True, 'capacity_lb': truck['capacity_lb'], 'refrigerated': truck['refrigerated'], 'windows': [truck['window']]}


def _utc(value):
    return dt(value).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def organization_systems(engine, at, faults=(), recorded=None):
    """Lane C's ``systems.json`` shape for the core scenario at time ``at``.

    Free storage is each food bank's recorded storage at ``at`` minus its own active holds,
    from the core's calculators and records. Cooler readings are Lane C's synthetic sensor
    copies; a fixture fault's reading replaces the failing food bank's failed reading.
    """
    from harvestnet_platform.systems import BANKS, Systems
    recorded = copy.deepcopy(recorded or Systems().fixture)
    f, records, now = engine.fixture, engine.records, dt(at)
    if set(engine.banks) != set(BANKS):
        raise ValueError(f'Lane C organization systems cover {sorted(BANKS)}; the scenario has {sorted(engine.banks)}')
    offer = f['surplus_offers'][0]
    lot = records.get('lot', offer['lot_id'])
    out = {'fixture_version': f"{f['scenario_id']}/{f['contract_version']}", 'observed_at': _utc(at),
           'donor': {'inventory': {'lot_id': offer['lot_id'], 'recall': bool(offer['recall_notice']), 'deadline': offer['deadline'],
                                   'items': [{'profile_id': i['produce_id'], 'quantity': i['quantity'], 'unit': i['unit'],
                                              'condition': i['condition_grade']} for i in offer['items']]},
                     'truck': _truck(engine.donors[offer['donor_id']].get('drop_off'))}}
    held = {}
    for other in records.all('lot'):
        for owner, hs in other['holds'].items():
            for h in hs:
                if dt(h['start']) <= now < dt(h['end']):
                    held[(owner, h['resource'])] = held.get((owner, h['resource']), 0) + (h.get('pounds') or 0)
    for bid in engine.banks:
        bank = records.get('bank', bid)
        free = engine.calc.storage_at(parse_facts('food_bank', engine.facts(bid, lot['draft'])).storage, now)
        failed = copy.deepcopy(recorded[bid]['cooler-failed'])
        for fault in faults:
            if fault['kind'] == 'cooler_failure' and fault['food_bank_id'] == bid:
                if fault['reading'].get('status') != 'failed':
                    raise ValueError('a cooler-failure fault must read failed')
                failed.update(status='failed', temperature_c=fault['reading']['temperature_c'], cold_available=False)
        out[bid] = {'storage': {'cold_available_lb': max(0, free.cold_free_lb - held.get((bid, 'storage_cold'), 0)),
                                'dry_available_lb': max(0, free.dry_free_lb - held.get((bid, 'storage_dry'), 0)),
                                'windows': [s['window'] for s in bank['storage']]},
                    'cooler': copy.deepcopy(recorded[bid]['cooler']), 'cooler-failed': failed,
                    'pickup-hours': {'windows': copy.deepcopy(bank['pickup_windows'])}, 'truck': _truck(bank.get('truck'))}
    return out


def scenario_systems(data, base_url=None, state_path=None):
    """Lane C's ``Systems`` (reads, switch, fallback labels) unchanged, serving ``data``."""
    from harvestnet_platform.systems import Systems

    class ScenarioSystems(Systems):
        def __init__(self):
            super().__init__(base_url, state_path)
            self.fixture = copy.deepcopy(data)
    return ScenarioSystems()


# --- The failing food bank's agent ----------------------------------------------------------


def candidate_answer(systems_url, organization, name):
    """A candidate food bank's own answer: its own storage and pickup-hours readings.

    Proposed. Lane C's transport has no candidate-answer message yet, so the join reads
    each candidate's own organization system directly, as that candidate's agent would.
    """
    base = systems_url.rstrip('/')
    return {'response': 'answered', 'name': name,
            'storage': _json(f'{base}/systems/{quote(organization)}/storage'),
            'pickup_hours': _json(f'{base}/systems/{quote(organization)}/pickup-hours')}


def handle_cooler_reading(*, food_bank_id, lot_id, systems_url, core_url, token, directory, answer, profiles=None):
    """Run when the food bank's cooler reading changes. Proposes a new version; never commits.

    ``answer(organization_id)`` returns that candidate's own answer, or ``None`` for no answer.
    """
    from harvestnet_platform.directory import record_info
    base, core = systems_url.rstrip('/'), core_url.rstrip('/')

    def read(resource):
        return _json(f'{base}/systems/{quote(food_bank_id)}/{resource}')

    cooler = read('cooler')
    signal = read_cooler_signal(cooler, organization_id=food_bank_id)
    if not signal.failed:
        return {'status': 'no_failure', 'flow': None, 'change': None}
    holding = _json(f'{core}/lots/{quote(lot_id)}/holding?food_bank_id={quote(food_bank_id)}', token=token, method='GET')
    found = directory.search(min_cold_lb=0)  # every food bank, so every one gets a reason card
    answers = {}
    for record in found['records']:
        info = record_info(record)
        org = info.get('organization_id')
        if info.get('capabilities', {}).get('role') == 'food_bank' and org != food_bank_id:
            reply = answer(org)
            if reply is not None:
                answers[org] = reply
    flow = run_cooler_failure_flow(cooler_reading=cooler, truck_reading=read('truck'), pickup_hours_reading=read('pickup-hours'),
                                   holding=holding, directory_result=found, answers=answers,
                                   travel_minutes=holding['travel_minutes'], profiles=profiles)
    reading = flow.signal.reading.summary()
    status = {'status': 'failed', 'temperature_c': signal.temperature_c, 'cold_available': False,
              **{k: reading[k] for k in ('source', 'mode', 'synthetic', 'observed_at')}}
    _json(f'{core}/food-banks/{quote(food_bank_id)}/status', {'cooler': status}, token=token, method='PUT')
    change = None
    if flow.new_version is not None:
        change = _json(f'{core}/lots/{quote(lot_id)}/changes', {'terms': flow.new_version.terms,
                       'organizations': list(flow.new_version.organizations), 'dashboard': flow.dashboard()}, token=token)
    return {'status': 'assessed', 'flow': flow, 'change': change}


def request_approvals(approvals_url, events_token, approval_request):
    """Ask Lane C's bridge for each named organization's review link. Nothing is approved here."""
    return _json(approvals_url.rstrip('/') + '/approval-requests', approval_request, token=events_token)


def _core_api_class():
    from harvestnet_platform.approvals import CoreAPI

    class OrganizationCoreAPI(CoreAPI):
        """Lane C's core client, relaying each human's decision with that organization's own core credential."""

        def __init__(self, base_url, tokens):
            super().__init__(base_url)
            self.tokens = dict(tokens)

        def decision(self, record):
            payload = {k: record[k] for k in ('event_id', 'version', 'organization_id', 'terms_hash', 'decision', 'receipt_id')}
            from harvestnet_platform.http import request_json
            return request_json(self.base_url + '/approvals', payload, token=self.tokens[record['organization_id']])
    return OrganizationCoreAPI


def organization_core_api(base_url, tokens):
    return _core_api_class()(base_url, tokens)


# --- Household texts after commitment ---------------------------------------------------------


def new_version_from_change(engine, change):
    """Lane B's ``NewVersion`` rebuilt from the core's stored change, in the food bank's timezone."""
    terms, tz = change['terms'], ZoneInfo(engine.fixture['timezone'])
    moves = terms['moves']
    receiver = moves[0]['to_food_bank_id'] if moves else None
    collect = None
    if moves:
        w = moves[0]['households_collect']
        collect = PickupWindow(dt(w['start']).astimezone(tz), dt(w['end']).astimezone(tz))
    return NewVersion(event_id=terms['event_id'], lot_id=terms['lot_id'], version=terms['version'],
                      based_on_version=terms['based_on_version'], proposer_id=terms['proposer_id'],
                      receiving_food_bank_id=receiver, receiving_food_bank_name=engine.names[receiver] if receiver else None,
                      households_collect=collect, organizations=tuple(change['organizations']), terms=terms,
                      terms_hash=lane_b_terms_hash(terms), status='awaiting_receiver_decision' if moves else 'awaiting_approval')


def household_texts(engine, lot_id, version, *, household_page_url, item_names=None, profiles=None):
    """Texts for the households whose pickups this committed version moved.

    Lane B writes the words; the core supplies the pounds, ``pickup_id``, ``release_url``
    and ``to`` (only if the household gave a phone). Raises ``NotCommittedError`` until
    every named organization approved this exact version.
    """
    change = changes.find(engine.records, lot_id, version)
    if change is None:
        raise KeyError(f'{lot_id} has no version {version} change')
    households = changes.households(engine, lot_id, version)
    notices = household_change_notices(new_version_from_change(engine, change), changes.decision_records(change),
                                       households, item_names, profiles)
    by_code = {h['request_code']: h for h in households}
    out = []
    for n in notices:
        ids = by_code[n.request_code]['pickup_ids']
        if len(ids) != 1:
            raise ValueError('one pickup notice per moved pickup; this household has several')
        try:
            phone = engine.records.get('phone', n.request_code)['phone']
        except KeyError:
            phone = None
        out.append({**n.to_dict(), 'pickup_id': ids[0], 'to': phone,
                    'release_url': f"{household_page_url.rstrip('/')}/pickups/{quote(ids[0], safe='')}"})
    return out


def prepare_texts(approvals_url, events_token, notices):
    """Lane C's prepared text bodies for n8n. Only households with a phone get one; nothing is sent."""
    return [_json(approvals_url.rstrip('/') + '/notifications/prepare', n, token=events_token) for n in notices if n.get('to')]


# --- Rule checks ------------------------------------------------------------------------------


def rule_checks(engine, lot_id, flow):
    """The core's checks over the lot after the change, merged with Lane B's flow checks."""
    checks = changes.rule_checks(engine, lot_id)
    for name, passed in flow.rule_checks().items():
        checks[name] = checks.get(name, True) and passed
    return checks


def outcomes(engine, lot_id, flow):
    """Lane C's ``join.require_outcomes`` over the changed lot: every required check present and passing."""
    from harvestnet_platform.join import require_outcomes
    lot = engine.records.get('lot', lot_id)
    return require_outcomes({'commitments': lot['commitments'], 'pathways': changes.pathways(engine, lot_id),
                             'rule_checks': rule_checks(engine, lot_id, flow)})


def lane_b_harness_checks(fixture):
    """Lane B's six harness checks on the same fixture, with the core's real calculators."""
    from harvestnet_agents.scenario import load_scenario
    from harvestnet_agents.scenario_runner import run_scenario
    from .calculators import Calculators
    run = run_scenario(load_scenario(copy.deepcopy(fixture)), Calculators())
    return {name: result.passed for name, result in run.lane_b_rule_checks.items()}


def main():
    parser = argparse.ArgumentParser(description='Export the organization systems for the cooler-failure scenario (synthetic).')
    parser.add_argument('--fixture', default='core_fixtures/cooler-failure.json')
    parser.add_argument('--export-systems', help="write Lane C's systems.json shape for the fault time")
    parser.add_argument('--export-openapi', help='write the OpenAPI document to import into Beeceptor')
    args = parser.parse_args()
    fixture = json.loads(Path(args.fixture).read_text())
    engine, faults, _ = run_until_fault(fixture)
    if not faults:
        parser.error('the fixture has no fault')
    data = organization_systems(engine, faults[0]['at'], faults)
    for path, value in ((args.export_systems, data), (args.export_openapi, scenario_systems(data).openapi() if args.export_openapi else None)):
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json.dumps(value, indent=2) + '\n')
            print(f'Wrote {path} (synthetic)')


if __name__ == '__main__':
    main()
