"""Ticket #20, the join: every scenario fixture through the harness with the real agents.

``run_join(fixture)`` runs one contract fixture two ways, both with Lane B's rules-based
negotiators and Lane A's real calculators (never the stand-ins):

1. **Lane A's harness** (``engine.run_fixture``): turns, owner holds, scripted human
   approvals, commitment, household pickups and releases. A ``HarnessLog`` watches the
   run and writes Lane B's event log for it (the kinds ``lane_b_rule_checks.py`` reads:
   ``scenario``, ``facts``, ``calculator_call``, ``move``, ``version``, ``hold``, ``held``,
   ``approval``, ``commitment``, ``stop``), so **both rule-check sets read the same run**:
   the fixture's own checks (Lane A's, from the harness records) and Lane B's six (from
   this log). It never makes or changes a move.
2. **Lane B's runner** (``scenario_runner.run_scenario``), with Lane A's calculators as
   the default. It also runs Lane B's cooler-failure logic (#15) after a commitment,
   which the harness doesn't. Its six checks are reported separately.

Every calculator call goes through ``RecordedCalculators``: the answer used is Lane A's,
and the stand-ins are asked the same question. A call whose answer differs carries
``difference_from_stand_in`` with both answers and a sentence saying why
(``Calculators.stand_in_differences``). The stand-ins have no ``fair_share`` or
``household_portions``, so those calls say ``not_compared``.

The fixtures need no adapter: ``core_fixtures/*.json`` are already in the contract's
scenario-fixture format (``contract-v0.1``), and ``load_fixture`` reads them through Lane
B's contract loader unchanged.

Every number is synthetic. Nothing here calls a model or the network."""
import copy
from dataclasses import dataclass
import json
from pathlib import Path

from harvestnet_agents.calculators import StandInCalculators
from harvestnet_agents.lane_b_rule_checks import run_lane_b_rule_checks
from harvestnet_agents.negotiation import Role
from harvestnet_agents.scenario import load_scenario
from harvestnet_agents.scenario_runner import EventLog, RecordedCalculators, negotiator_label, run_scenario
from .calculators import Calculators
from .engine import run_fixture
from .protocol import dt, named, terms_hash
from .records import Records

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATHS = (ROOT / 'docs/contracts/examples/scenario-normal-afternoon.json', *sorted((ROOT / 'core_fixtures').glob('*.json')))

# The fixture checks Lane A's harness implements (``checks.rule_checks``).
LANE_A_RULE_CHECKS = ('zero_invalid_commitments', 'no_double_booking', 'pounds_conserved', 'fair_share_respected',
                      'versioned_approvals', 'no_auto_commit', 'all_pounds_have_pathway', 'number_check_failures_counted')

STAND_IN_DIFFERENCES = Calculators.stand_in_differences

LANE_A_SOURCE = 'lane_a_harness_records'
LANE_B_SOURCE = 'lane_b_checks_over_harness_log'
LANE_B_RUNNER_SOURCE = 'lane_b_checks_over_lane_b_runner_log'


def load_fixture(source):
    """A contract fixture as a plain dict, after Lane B's contract loader accepts it."""
    raw = copy.deepcopy(dict(source)) if isinstance(source, dict) else json.loads(Path(source).read_text(encoding='utf-8'))
    load_scenario(raw)  # refuses anything that isn't a contract-v0.1 scenario fixture
    return raw


def recorded_core_calculators(log, clock, calculators=None):
    """Lane A's real calculators, every call logged and compared with the stand-ins."""
    primary = calculators if calculators is not None else Calculators()
    return RecordedCalculators(primary, log, clock, reference=StandInCalculators(profiles=primary.profiles))


class HarnessLog:
    """Lane B's event log, written while Lane A's harness runs a fixture.

    The harness tells it when a turn starts, when the mover's facts are ready, when the
    move is recorded, and when a lot is finished (``run_fixture(observer=...)``). Each
    time, the harness's new records events are translated in order: ``draft`` and
    ``amendment`` become ``version``, ``owner_hold`` becomes ``hold`` (and ``held`` once
    every named organization holds), ``human_decision`` becomes ``approval``,
    ``commitment`` stays ``commitment``, and ``preserved_disagreement`` and
    ``recall_refused`` become ``stop``. Everything else (pickup notices, confirmations,
    releases, number-check failures, the scripted cooler failure) is kept under its own
    kind with the harness's data."""

    def __init__(self, fixture, calculators=None):
        self.fixture = fixture
        self.log = EventLog()
        self.engine = None
        self.calc = recorded_core_calculators(self.log, self._clock, calculators)
        self.done = {}
        self.versions = {}
        self.holders = {}
        self.held = set()
        self.last_move = None
        self.last_move_seq = None
        self.offer_seqs = []
        self.facts_seqs = []
        self.move_seqs = []
        self.turns = len(fixture['turn_order'])
        names = {o['organization_id']: o for o in fixture['organizations']}
        self.log.add('scenario', dt(fixture['clock']['start']), scenario_id=fixture['scenario_id'], title=fixture.get('title'),
                     mode=fixture['mode'], synthetic=fixture['synthetic'], note=fixture.get('note'),
                     lot_ids=[o['lot_id'] for o in fixture['surplus_offers']],
                     organizations=[{'organization_id': o, 'role': v['role'], 'name': v['name']} for o, v in names.items()],
                     turn_order=list(fixture['turn_order']), calculators=self.calc.label,
                     compared_with=self.calc.reference.label, harness="Lane A's harness (harvestnet_core.engine.run_fixture)",
                     request_codes=[r['request_code'] for r in fixture['requests']], humans_are_scripted=True,
                     rounds_without_new_terms=fixture['policies']['rounds_without_new_terms_before_disagreement'])

    def _clock(self):
        return dt(self.engine.now if self.engine is not None else self.fixture['clock']['start'])

    # The harness's hooks

    def attach(self, engine):
        self.engine = engine
        self.offer_seqs = self.calc.capture('harness', 'offer')

    def turn_started(self, engine, lot_id, org):
        self._flush(engine, lot_id)
        self.facts_seqs = self.calc.capture(org, 'facts')

    def facts_ready(self, engine, lot_id, org, agent_input):
        self.log.add('facts', self._clock(), lot_id=lot_id, organization_id=org, role=agent_input['role'],
                     facts=agent_input['facts'], calculator_call_seqs=list(self.facts_seqs))
        self.move_seqs = self.calc.capture(org, 'move')

    def move_made(self, engine, lot_id, org, agent_input, move):
        self._flush(engine, lot_id)
        turn = agent_input['turn']
        negotiator = engine.negotiators.get((Role(agent_input['role']), org))
        event = self.log.add(
            'move', self._clock(), lot_id=lot_id, version=agent_input['draft']['version'],
            round=(turn['number'] - 1) // self.turns + 1, organization_id=org, role=agent_input['role'],
            negotiator=negotiator_label(negotiator) if negotiator is not None else 'move provider',
            turn=turn, facts=agent_input['facts'], move=move,
            # A harness move never commits: only every named human's approval does (protocol.approve).
            commits=False, calculator_call_seqs=list(self.move_seqs))
        self.last_move, self.last_move_seq = move, event['seq']
        self.calc.capture('harness', 'apply')

    def lot_finished(self, engine, lot_id):
        self._flush(engine, lot_id)
        try:
            lot = engine.records.get('lot', lot_id)
        except KeyError:
            lot = None
        if lot is not None:
            committed = lot['status'] == 'committed'
            self.log.add('outcome', self._clock(), lot_id=lot_id, status=lot['status'],
                         reason="Every named organization's human approved this version." if committed else lot.get('stop_reason'),
                         committed_version=lot['draft']['version'] if committed else None, pathways=engine.pathways(lot_id))
        self.offer_seqs = self.calc.capture('harness', 'offer')

    # Records events, translated in order

    def _flush(self, engine, lot_id):
        events = engine.records.events(lot_id)
        for e in events[self.done.get(lot_id, 0):]:
            self._translate(lot_id, e)
        self.done[lot_id] = len(events)

    def _version(self, lot_id, at, draft, *, proposer_id, move_seq, amendment, calculator_call_seqs=()):
        key = (lot_id, draft['version'])
        self.versions[key] = draft
        self.log.add('version', at, lot_id=lot_id, version=draft['version'], based_on_version=draft.get('based_on_version'),
                     proposer_id=proposer_id, reason=draft.get('reason'), move_seq=move_seq, amendment=amendment, terms=draft,
                     terms_hash=terms_hash(draft), named_organizations=named(draft),
                     calculator_call_seqs=list(calculator_call_seqs))

    def _translate(self, lot_id, e):
        kind, data, at = e['kind'], e['data'], dt(e['at'])
        if kind == 'move':
            return  # logged by move_made, with the mover's facts, turn, and calculator calls
        if kind == 'draft':
            self._version(lot_id, at, data, proposer_id=data['proposer_id'], move_seq=None, amendment=None,
                          calculator_call_seqs=self.offer_seqs)
        elif kind == 'amendment':
            self._version(lot_id, at, data['draft'], proposer_id=data['organization_id'], move_seq=self.last_move_seq,
                          amendment=data['amendment'])
        elif kind == 'owner_hold':
            org, version = data['organization_id'], data['version']
            owner = (self.last_move or {}).get('resource_owner', org)
            for h in data['holds']:
                self.log.add('hold', at, lot_id=lot_id, version=version, organization_id=org, owner_id=owner,
                             resource=h['resource'], pounds=h.get('pounds'), start=h['start'], end=h['end'],
                             move_seq=self.last_move_seq)
            holders = self.holders.setdefault((lot_id, version), set())
            holders.add(org)
            draft = self.versions.get((lot_id, version))
            if draft and draft['allocations'] and set(named(draft)) <= holders and (lot_id, version) not in self.held:
                self.held.add((lot_id, version))
                self.log.add('held', at, lot_id=lot_id, version=version, organizations=named(draft))
        elif kind == 'human_decision':
            receipt_id = str(data.get('receipt_id') or '')
            self.log.add('approval', at, lot_id=lot_id, version=data['version'], terms_hash=data['terms_hash'],
                         organization_id=data['organization_id'], decision=data['decision'], receipt_id=receipt_id,
                         source='scripted_human' if receipt_id.startswith('script-') else 'human')
        elif kind == 'commitment':
            draft = self.versions[(lot_id, data['version'])]
            self.log.add('commitment', at, lot_id=lot_id, version=data['version'], terms_hash=data['terms_hash'],
                         organizations=named(draft), allocations=data['allocations'],
                         approval_seqs=[a['seq'] for a in self.log.events if a['kind'] == 'approval' and a['lot_id'] == lot_id
                                        and a['version'] == data['version']],
                         hold_seqs=[h['seq'] for h in self.log.events if h['kind'] == 'hold' and h['lot_id'] == lot_id
                                    and h['version'] == data['version']])
        elif kind == 'preserved_disagreement':
            current = max((v for (lot, v) in self.versions if lot == lot_id), default=None)
            self.log.add('stop', at, lot_id=lot_id, version=current, rule='preserved_disagreement',
                         status='preserved_disagreement', reason=data['reason'])
        elif kind == 'recall_refused':
            self.log.add('stop', at, lot_id=lot_id, version=None, rule='recalled', status='recalled',
                         reason=f"The lot has a {data['reason']}, so it is never offered.")
        else:
            self.log.add(kind, at, lot_id=lot_id, harness_data=data)


@dataclass
class JoinRun:
    scenario_id: str
    harness: dict
    events: list
    rule_checks: dict
    calculator_differences: list
    lane_b_runner: dict

    @property
    def passed(self):
        runner = self.lane_b_runner.get('rule_checks') or {}
        return all(c['passed'] for c in self.rule_checks.values()) and all(c['passed'] for c in runner.values())

    def to_dict(self):
        return {'scenario_id': self.scenario_id, 'passed': self.passed, 'rule_checks': self.rule_checks,
                'calculator_differences': self.calculator_differences, 'harness': {k: v for k, v in self.harness.items() if k != 'events'},
                'events': self.events, 'lane_b_runner': self.lane_b_runner}


def _checks(results, source):
    return {name: {'passed': r.passed, 'failures': list(r.failures), 'source': source} for name, r in results.items()}


def run_join(fixture, *, calculators=Calculators):
    """Run one fixture through Lane A's harness and Lane B's runner, and every rule check.

    ``calculators`` is a factory for the real calculators (Lane A's by default); each run
    gets its own instance."""
    raw = load_fixture(fixture)
    observer = HarnessLog(raw, calculators())
    records = Records()
    try:
        harness = run_fixture(copy.deepcopy(raw), records=records, calculators=observer.calc, observer=observer)
    finally:
        records.close()
    events = observer.log.events

    lane_a = harness['rule_checks']
    rule_checks = {}
    for name in dict.fromkeys([*raw['rule_checks'], *lane_a]):
        if name in lane_a:
            rule_checks[name] = {'passed': bool(lane_a[name]), 'source': LANE_A_SOURCE,
                                 'failures': [] if lane_a[name] else [f"Lane A's {name} check failed on the harness records"]}
        else:
            rule_checks[name] = {'passed': False, 'source': 'not_run',
                                 'failures': [f"the fixture asks for {name}, which Lane A's harness doesn't implement, so it was not run"]}
    rule_checks.update(_checks(run_lane_b_rule_checks(events, observer.calc.profiles), LANE_B_SOURCE))

    return JoinRun(scenario_id=raw['scenario_id'], harness=harness, events=events, rule_checks=rule_checks,
                   calculator_differences=[e for e in events if e['kind'] == 'calculator_call' and e.get('difference_from_stand_in')],
                   lane_b_runner=_lane_b_runner(raw, calculators, harness))


def _lane_b_runner(raw, calculators, harness):
    try:
        run = run_scenario(load_scenario(raw), calculators())
    except NotImplementedError as exc:
        return {'status': 'not_run', 'reason': str(exc), 'rule_checks': {}}
    scenario = next(e for e in run.events if e['kind'] == 'scenario')
    committed = [] if run.committed_draft is None else sorted(
        [a.food_bank_id, a.produce_id, a.pounds] for a in run.committed_draft.allocations if a.pounds > 0)
    in_harness = sorted([a['food_bank_id'], a['produce_id'], a['pounds']] for a in harness['commitments'] if a['pounds'] > 0)
    return {'status': run.status, 'committed_version': run.committed_version, 'calculators': scenario['calculators'],
            'compared_with': scenario['compared_with'], 'negotiators': scenario['negotiators'],
            'rule_checks': _checks(run.lane_b_rule_checks, LANE_B_RUNNER_SOURCE),
            'calculator_differences': run.calculator_differences, 'committed_allocations': committed,
            'same_commitment_as_harness': committed == in_harness, 'outcome': run.outcome,
            'cooler_failure_assessments': [e for e in run.events if e['kind'] == 'cooler_failure_assessment']}


def main(argv=None):
    """``python -m harvestnet_core.join``: every fixture's join result, one line each."""
    for path in FIXTURE_PATHS:
        run = run_join(path)
        failed = sorted(n for n, c in run.rule_checks.items() if not c['passed'])
        print(json.dumps({'fixture': path.relative_to(ROOT).as_posix(), 'passed': run.passed, 'failed_checks': failed,
                          'harness_commitments': len(run.harness['commitments']), 'calculator_differences': len(run.calculator_differences),
                          'lane_b_runner_status': run.lane_b_runner['status'],
                          'same_commitment_as_harness': run.lane_b_runner.get('same_commitment_as_harness')}))


if __name__ == '__main__':
    main()
