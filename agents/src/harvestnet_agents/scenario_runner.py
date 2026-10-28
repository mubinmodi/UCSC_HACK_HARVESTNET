"""Run a scenario fixture with the real negotiators, and log every step (ticket #20).

Lane A owns the scenario harness (#7, ``harvestnet_core.engine``) and the real
calculators (#8, ``harvestnet_core.calculators``). This is Lane B's runner: it runs a
contract fixture (``scenario.py``) through the real rules-based negotiators and produce
profiles, behind the agreed agent move interface. The join (``harvestnet_core.join``)
runs every fixture through Lane A's harness and through this runner, both with Lane A's
real calculators, and reads both rule-check sets from the harness run.

**What the runner does, and only that.** It publishes turns in the fixture's turn order
and applies each organization's move to the shared draft. It never decides for anyone
(ADR 0001):

- a ``counter`` creates the next version, and every accept and hold on the old version
  stops counting;
- an ``accept`` or ``request_hold`` is bound to the version it names;
- ``reject`` stands for that organization on that version, and the negotiation goes on
  until a stop rule;
- the stop rules come from the design (docs/MVP_DESIGN.md §8): **ask a human** (any
  ``ask_human`` move), **keep the disagreement** (``rounds_without_new_terms`` rounds with
  no counter, or counters that bring back terms already seen at the same point in the turn
  order: a ``counter_cycle``), and **deadline** (no commitment by the donor's deadline means
  unclaimed). The harness clock moves ``DEFAULT_MINUTES_PER_TURN`` per turn, so the deadline
  can fire;
- quiet rounds where an organization's latest move was invalid are not a disagreement: the
  run stops as ``negotiator_failure`` (rule ``invalid_moves``), naming the organization;
- once every organization named in a version has requested its holds, the runner asks
  each named organization's human, using the fixture's scripted human decisions.
  **Agreement** is only when every named organization's human approves that exact
  version (same terms hash) before the deadline and before any hold ends. Nothing ever
  commits otherwise, including at the deadline.

After a commitment, a fault in the fixture is applied at its time. A cooler failure at
a food bank holding committed cold-dependent produce runs Lane B's cooler-failure logic
(#15), which proposes a new version awaiting the receiving food bank's own decision and
fresh approvals. The runner commits nothing after that.

**Calculators are a required parameter.** ``run_scenario(scenario, calculators)`` takes
any ``Calculators`` implementation. The harness passes Lane A's real ones
(``harvestnet_core.calculators.Calculators``); only unit tests pass the stand-ins, and
nothing picks them silently. Every call goes through ``RecordedCalculators``, which logs
its inputs and output and, when the calculators aren't the stand-ins, also asks the
stand-ins and records any difference (``difference_from_stand_in``) with a sentence
saying why, so each difference is explained in the log.

**Negotiators are a parameter.** ``negotiator_factory(role, organization_id,
calculators)`` builds each organization's negotiator: rules-based by default, or an
``LLMNegotiator`` for any role (``llm_negotiators_for``). Tests never call the API.

**The event log** is a list of plain JSON objects with a sequence number, the harness
clock, and a kind: ``scenario``, ``facts``, ``calculator_call``, ``version``, ``move``,
``invalid_move``, ``hold``, ``held``, ``approval_requested``, ``approval``,
``no_approval``, ``commitment``, ``stop``, ``fault``, ``cooler_failure_assessment``, and
``outcome``. Lane B's rule checks (``lane_b_rule_checks.py``) run over it.

The runner's own choices (turn timing, what a reject means, a human's decline) are
**proposed**, and listed as open questions in the PR for #20.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from .calculators import CalculatorCall, CalculatorError, Calculators, StandInCalculators
from .terms import terms_hash
from .negotiation import (
    AdvocateFacts,
    AgentInput,
    DraftError,
    DraftVersion,
    Facts,
    Move,
    MoveError,
    MoveKind,
    Role,
    SetPounds,
    Turn,
    Claim,
    amendment_to_dict,
    claim_of,
    draft_terms,
)
from .lane_b_rule_checks import RuleCheckResult, run_lane_b_rule_checks
from .llm_negotiators import LLMNegotiator, SpendingCap
from .profiles import ProfileSet
from .rules_negotiators import RulesFoodBank, TurnError, _Negotiator, rules_negotiator
from .serialize import jsonable
from .scenario import Fault, Scenario, SurplusOffer, facts_for, offer_draft

__all__ = [
    "DEFAULT_MINUTES_PER_TURN",
    "FIXTURE_CHECKS_IN_HARNESS",
    "EventLog",
    "Negotiation",
    "Negotiator",
    "RecordedCalculators",
    "ScenarioRun",
    "draft_terms",
    "llm_negotiators_for",
    "negotiate",
    "negotiator_label",
    "run_scenario",
]

# The fixture's own rule checks read Lane A's records (holds, pickups, pathways), which
# this runner doesn't keep. Lane A's harness runs them, and the join reports the results.
FIXTURE_CHECKS_IN_HARNESS = "not run by Lane B's runner: Lane A's harness runs this check (see harvestnet_core.join)"


# How far the harness clock moves per turn (proposed; the contract doesn't say). A turn is one
# agent exchange: its specialists' facts, its calculators and, for an LLM negotiator, a model
# call or two, so a few minutes is realistic. At 2 minutes, the fixtures' negotiations (up to
# about 30 turns after the 12:00 offer, then 15 minutes of scripted approvals) commit by about
# 1:10 pm, well before their 3 pm deadline, and one that keeps going for 90 turns hits that
# deadline instead of running forever.
DEFAULT_MINUTES_PER_TURN = 2.0


class Negotiator(Protocol):
    def move(self, agent_input: AgentInput) -> Move: ...


NegotiatorFactory = Callable[[Role, str, Calculators], Negotiator]


# --- The event log ------------------------------------------------------------------------


class EventLog:
    """Every step of a run, as plain JSON objects in order."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def add(self, kind: str, at: datetime, **fields: Any) -> dict[str, Any]:
        event = {"seq": len(self.events) + 1, "at": at.isoformat(), "kind": kind, **jsonable(fields)}
        self.events.append(event)
        return event


# --- Calculators, recorded ----------------------------------------------------------------

_INPUT_NAMES = {
    "fair_share": ("household_size",),
    "household_portions": ("pounds_available", "households"),
    "fair_share_gap": ("households",),
    "gap_after_plan": ("gap_lb", "planned_lb"),
    "storage_at": ("storage", "at"),
    "capacity_fit": ("free_lb", "needed_lb"),
    "pickup_feasibility": ("arrives_at", "pickup_windows", "usable_until"),
    "arrival_time": ("departs_at", "travel_minutes"),
    "adjust_pounds": ("current_lb", "change_lb"),
    "to_pounds": ("produce_id", "quantity", "unit", "lb_per_unit"),
    "proportional_split": ("held_lb", "gaps_lb"),
}


def _contract_output(name: str, result: Any) -> dict[str, Any]:
    """A result in the calculator contract's JSON shape (bare numbers and times wrapped)."""
    if name in ("to_pounds", "adjust_pounds"):
        return {"pounds": result}
    if name == "arrival_time":
        return {"arrives_at": result.isoformat()}
    return jsonable(result)


def _label(calculators: Any) -> str:
    return str(getattr(calculators, "label", type(calculators).__name__))


class RecordedCalculators:
    """Any ``Calculators``, with every call logged and compared with the stand-ins.

    ``reference`` is the stand-in to compare with, or ``None`` when ``primary`` is the
    stand-in. A call's ``difference_from_stand_in`` is ``None`` when both agree (or no
    comparison was made), else the differing fields with both outputs and a sentence.
    When the stand-ins have no such calculator (``fair_share``, ``household_portions``),
    the call says so in ``not_compared``. ``explanations`` maps a calculator name to why
    the primary's answers can differ from the stand-in's, and is added to the sentence;
    it defaults to the primary's own ``stand_in_differences``, if it has any.
    """

    def __init__(self, primary: Calculators, log: EventLog, clock: Callable[[], datetime], *, reference: Calculators | None = None,
                 explanations: Mapping[str, str] | None = None):
        self.primary = primary
        self.reference = reference
        self.explanations = dict(explanations if explanations is not None else getattr(primary, "stand_in_differences", None) or {})
        self.log = log
        self.clock = clock
        self.profiles: ProfileSet = primary.profiles
        self.calls: list[CalculatorCall] = []
        self.actor = "harness"
        self.purpose = "harness"
        self._seqs: list[int] | None = None

    @property
    def label(self) -> str:
        return _label(self.primary)

    def capture(self, actor: str, purpose: str) -> list[int]:
        """Attribute the following calls to ``actor`` and collect their event numbers."""
        self.actor, self.purpose, self._seqs = actor, purpose, []
        return self._seqs

    def fair_share(self, household_size):
        return self._call("fair_share", household_size)

    def household_portions(self, pounds_available, households):
        return self._call("household_portions", pounds_available, households)

    def fair_share_gap(self, households):
        return self._call("fair_share_gap", households)

    def gap_after_plan(self, gap_lb, planned_lb):
        return self._call("gap_after_plan", gap_lb, planned_lb)

    def storage_at(self, storage, at):
        return self._call("storage_at", storage, at)

    def capacity_fit(self, free_lb, needed_lb):
        return self._call("capacity_fit", free_lb, needed_lb)

    def pickup_feasibility(self, arrives_at, pickup_windows, usable_until):
        return self._call("pickup_feasibility", arrives_at, pickup_windows, usable_until)

    def arrival_time(self, departs_at, travel_minutes):
        return self._call("arrival_time", departs_at, travel_minutes)

    def adjust_pounds(self, current_lb, change_lb):
        return self._call("adjust_pounds", current_lb, change_lb)

    def to_pounds(self, produce_id, quantity, unit, lb_per_unit=None):
        return self._call("to_pounds", produce_id, quantity, unit, lb_per_unit)

    def proportional_split(self, held_lb, gaps_lb):
        return self._call("proportional_split", held_lb, gaps_lb)

    def _call(self, name: str, *args: Any) -> Any:
        inputs = dict(zip(_INPUT_NAMES[name], args))
        base = {"actor": self.actor, "purpose": self.purpose, "calculator": name, "input": inputs}
        try:
            result = getattr(self.primary, name)(*args)
        except CalculatorError as exc:
            self._record(self.log.add("calculator_call", self.clock(), **base, error={"code": "calculator_error", "message": str(exc)},
                                      difference_from_stand_in=None))
            raise
        output = _contract_output(name, result)
        if self.reference is not None and not hasattr(self.reference, name):
            base["not_compared"] = f"the stand-ins have no {name} calculator, so this call isn't compared"
        event = self.log.add("calculator_call", self.clock(), **base, output=output,
                             difference_from_stand_in=self._difference(name, args, output))
        self._record(event)
        self.calls.append(CalculatorCall(name, jsonable(inputs), result))
        return result

    def _record(self, event: dict[str, Any]) -> None:
        if self._seqs is not None:
            self._seqs.append(event["seq"])

    def _difference(self, name: str, args: Sequence[Any], output: dict[str, Any]) -> dict[str, Any] | None:
        if self.reference is None or not hasattr(self.reference, name):
            return None
        try:
            ref = _contract_output(name, getattr(self.reference, name)(*args))
        except CalculatorError as exc:
            return {"fields": sorted(output), "output": output, "stand_in_error": str(exc),
                    "explanation": f"{self.label} answered where the stand-in gave an error ({exc}); the run used {self.label}'s answer."}
        fields = [k for k in ref if not _same(output.get(k), ref[k])]
        if not fields:
            return None
        why = f" Why: {self.explanations[name]}" if name in self.explanations else ""
        return {"fields": fields, "output": output, "stand_in_output": ref,
                "explanation": f"{self.label} gave a different {', '.join(fields)} than the stand-in for the same input; "
                               f"the run used {self.label}'s answer.{why}"}


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


# --- The negotiation loop (promoted from the #11 test-only loop) ------------------------------


@dataclass
class Negotiation:
    """Where a negotiation stopped."""

    draft: DraftVersion
    status: str  # held, waiting_for_human, preserved_disagreement, negotiator_failure, unclaimed_deadline, move_limit
    now: datetime
    moves: list[Move] = field(default_factory=list)
    holds: list[dict[str, Any]] = field(default_factory=list)  # hold events on the final version
    reason: str = ""


def negotiate(
    draft: DraftVersion,
    *,
    turn_order: Sequence[str],
    roles: Mapping[str, Role],
    facts_at: Callable[[str, datetime], Facts],
    negotiators: Mapping[str, Negotiator],
    start: datetime,
    log: EventLog | None = None,
    calculators: RecordedCalculators | None = None,
    rounds_without_new_terms: int = 3,
    minutes_per_turn: float = DEFAULT_MINUTES_PER_TURN,
    max_rounds: int = 30,
    labels: Mapping[str, str] | None = None,
) -> Negotiation:
    """Publish turns in order and apply each move to the shared draft until a stop rule.

    ``facts_at(organization_id, now)`` returns that organization's own facts. The loop
    never makes a move itself and never commits anything.
    """
    log = log if log is not None else EventLog()
    labels = labels or {}
    accepted: set[str] = set()
    holds: list[dict[str, Any]] = []
    declined: set[tuple[str, str]] = set()  # (food bank, item) a food bank countered down
    contests: list[tuple[str, str, str]] = []  # (food bank, food bank it took pounds from, item), ADR 0013
    claims: list[Claim] = []  # every contest and take-back, with the gap it stated, for every negotiator to read
    moves: list[Move] = []
    quiet_rounds = 0
    turn_number = 0
    now = start
    last_invalid: dict[str, str] = {}  # organization -> problem, while its latest turn was an invalid move
    # Terms already seen, with the position in turn order of the organization that made them,
    # mapped to their version: the same terms again at the same point in the order is a cycle.
    seen_terms = {_terms_key(draft, len(turn_order) - 1): draft.version}
    versions = {draft.version: draft}

    def stop(status: str, rule: str, reason: str, **extra: Any) -> Negotiation:
        log.add("stop", now, lot_id=draft.lot_id, version=draft.version, rule=rule, status=status, reason=reason, **extra)
        return Negotiation(draft, status, now, moves, [h for h in holds if h["version"] == draft.version], reason)

    for round_number in range(1, max_rounds + 1):
        changed = False
        for org in turn_order:
            turn_number += 1
            now = start + timedelta(minutes=minutes_per_turn * (turn_number - 1))
            if now > draft.deadline:
                return stop("unclaimed_deadline", "deadline",
                            f"The {draft.deadline.isoformat()} deadline passed with no commitment on any version, so the lot is "
                            "unclaimed. Nothing is committed automatically.")
            facts = facts_at(org, now)
            if isinstance(facts, AdvocateFacts):
                facts = replace(facts, declined=tuple(sorted(declined)), contests=tuple(dict.fromkeys(contests)))
            turn = Turn(org, turn_number, now, tuple(sorted(accepted)))
            seqs = calculators.capture(org, "move") if calculators is not None else []
            try:
                move = negotiators[org].move(AgentInput(draft, facts, turn, claims=tuple(claims)))
                problem = _move_problem(move, org, roles[org], draft)
            except (TurnError, MoveError, DraftError, CalculatorError) as exc:
                move, problem = None, f"{type(exc).__name__}: {exc}"
            if problem is None and move.kind is MoveKind.COUNTER:
                try:
                    next_draft = draft.amend(move.amendment, proposer_id=org, reason=move.reason)
                except DraftError as exc:
                    problem = f"the amendment doesn't apply to version {draft.version}: {exc}"
            if problem is not None:
                log.add("invalid_move", now, lot_id=draft.lot_id, version=draft.version, organization_id=org, round=round_number,
                        problem=problem, move=move.to_dict() if isinstance(move, Move) else None)
                last_invalid[org] = problem
                continue  # an invalid move changes nothing; it counts as no new terms

            last_invalid.pop(org, None)
            moves.append(move)
            event = log.add(
                "move", now, lot_id=draft.lot_id, version=draft.version, round=round_number, organization_id=org,
                role=roles[org].value, negotiator=labels.get(org, negotiator_label(negotiators[org])),
                turn=turn, facts=facts, claims=list(claims), move=move.to_dict(), commits=move.commits, calculator_call_seqs=list(seqs),
                llm=_llm_record(negotiators[org]),
            )
            match move.kind:
                case MoveKind.COUNTER:
                    a = move.amendment
                    if isinstance(a, SetPounds) and a.food_bank_id == org and a.pounds < draft.pounds(a.produce_id, org):
                        declined.add((org, a.produce_id))
                    if (c := claim_of(org, roles[org], a, next_draft.version)) is not None:
                        claims.append(c)
                        contests.append((org, c.from_food_bank_id, c.produce_id))
                    draft = next_draft
                    accepted, changed = set(), True
                    log.add("version", now, lot_id=draft.lot_id, version=draft.version, based_on_version=draft.based_on_version,
                            proposer_id=org, reason=draft.reason, move_seq=event["seq"], amendment=amendment_to_dict(a),
                            terms=draft_terms(draft), terms_hash=terms_hash(draft_terms(draft)),
                            named_organizations=list(draft.named_organizations()))
                    key = _terms_key(draft, turn_order.index(org))
                    versions[draft.version] = draft
                    if key in seen_terms:
                        first = seen_terms[key]
                        last = {m.organization_id: {"organization_id": m.organization_id, "version": m.version, "action": m.kind.value,
                                                    "reason": m.reason} for m in moves}
                        return stop("preserved_disagreement", "counter_cycle",
                                    f"Version {draft.version} has the same terms as version {first}, at the same point in "
                                    f"the turn order, so the counters are going round in a cycle (versions {first} to "
                                    f"{draft.version}). The involved dashboards show each organization's last reason.",
                                    options=_cycle_sides(versions, first, draft.version), reasons=list(last.values()))
                    seen_terms[key] = draft.version
                case MoveKind.ACCEPT:
                    accepted.add(org)
                case MoveKind.REQUEST_HOLD:
                    for h in move.holds:
                        holds.append(log.add("hold", now, lot_id=draft.lot_id, version=draft.version, organization_id=org,
                                             owner_id=h.owner_id, resource=h.resource, pounds=h.pounds, start=h.start, end=h.end,
                                             move_seq=event["seq"]))
                case MoveKind.ASK_HUMAN:
                    return stop("waiting_for_human", "ask_human", f"{org} asks its human first: {move.reason}")
                case _:
                    pass  # reject stands for this organization on this version; pass changes nothing

            named = set(draft.named_organizations())
            held_by = {h["organization_id"] for h in holds if h["version"] == draft.version}
            if draft.named_food_banks() and named <= held_by:
                log.add("held", now, lot_id=draft.lot_id, version=draft.version, organizations=sorted(named))
                return Negotiation(draft, "held", now, moves, [h for h in holds if h["version"] == draft.version])
        quiet_rounds = 0 if changed else quiet_rounds + 1
        if quiet_rounds >= rounds_without_new_terms and last_invalid:
            # Not a disagreement: an organization's latest word is an invalid move, so there is no
            # reason of its own to show. Its negotiator failed, and a human has to look.
            failed = ", ".join(f"{o} ({p})" for o, p in sorted(last_invalid.items()))
            return stop("negotiator_failure", "invalid_moves",
                        f"Stalled by invalid moves: {quiet_rounds} rounds with no new terms on version {draft.version}, and the "
                        f"latest move from {failed} was invalid. This is a negotiator failure, not a preserved disagreement; "
                        "nothing commits.")
        if quiet_rounds >= rounds_without_new_terms:
            return stop("preserved_disagreement", "preserved_disagreement",
                        f"{quiet_rounds} rounds with no new terms on version {draft.version}. The involved dashboards show each "
                        "organization's last reason.")
    return stop("move_limit", "move_limit", f"No stop rule after {max_rounds} rounds.")


def _cycle_sides(versions: Mapping[int, DraftVersion], first: int, last: int) -> list[dict[str, Any]]:
    """The versions a cycle went through, newest first, one per distinct plan, each with its
    proposer and reason: what the involved dashboards show for a kept disagreement (for a
    contest, both food banks' versions and reasons, ADR 0013)."""
    out, seen = [], set()
    for v in range(last, first, -1):
        d = versions.get(v)
        if d is None:
            continue
        plan = tuple((a.produce_id, a.food_bank_id, a.pounds) for a in d.allocations)
        if plan in seen:
            continue
        seen.add(plan)
        out.append({"version": d.version, "proposer_id": d.proposer_id, "reason": d.reason,
                    "allocations": [{"produce_id": p, "food_bank_id": fb, "pounds": lb} for p, fb, lb in plan]})
    return out


def _terms_key(draft: DraftVersion, position: int) -> tuple[str, int]:
    """A version's terms without its numbering and proposer, hashed, with the turn-order
    position of the organization that made them."""
    terms = draft_terms(draft)
    for name in ("version", "based_on_version", "proposer_id"):
        terms.pop(name, None)
    return terms_hash(terms), position


def _move_problem(move: Move, org: str, role: Role, draft: DraftVersion) -> str | None:
    if not isinstance(move, Move):
        return f"not a move: {move!r}"
    if move.organization_id != org:
        return f"it is {org}'s turn, but the move is {move.organization_id}'s"
    if move.role is not role:
        return f"{org} is a {role.value}, but the move is a {move.role.value}'s"
    if move.version != draft.version:
        return f"the move names version {move.version}; the current version is {draft.version}"
    return None


def negotiator_label(negotiator: Any) -> str:
    """``rules``, ``llm``, or the class name: which kind of negotiator made a move."""
    if isinstance(negotiator, LLMNegotiator):
        return "llm"
    if isinstance(negotiator, _Negotiator):
        return "rules"
    return type(negotiator).__name__


def _llm_record(negotiator: Any) -> dict[str, Any] | None:
    d = getattr(negotiator, "last_decision", None)
    if d is None:
        return None
    return {"source": d.source, "model": d.model, "model_calls": d.model_calls, "number_check_failures": d.number_check_failures,
            "check_problems": list(d.check_problems), "fallback_reason": d.fallback_reason, "cost_usd": d.cost_usd}


def llm_negotiators_for(roles: Iterable[Role | str], **llm_kwargs: Any) -> NegotiatorFactory:
    """A factory giving ``LLMNegotiator`` to these roles and rules-based ones to the rest.

    ``llm_kwargs`` go to ``LLMNegotiator`` (``cap``, ``client``, ``config``). Without a
    ``cap``, every negotiator from this factory shares ``SpendingCap.from_env()``
    (``CLAUDE_RUN_CAP_USD``, default 0, and the total cap in the spend ledger).
    """
    llm_roles = {Role(r) for r in roles}
    if llm_kwargs.get("cap") is None:
        llm_kwargs["cap"] = SpendingCap.from_env(caller="negotiator")

    def factory(role: Role, organization_id: str, calculators: Calculators) -> Negotiator:
        if role in llm_roles:
            return LLMNegotiator(role, organization_id, calculators=calculators, **llm_kwargs)
        return rules_negotiator(role, organization_id, calculators)

    return factory


# --- Running a scenario ---------------------------------------------------------------------


@dataclass
class ScenarioRun:
    scenario_id: str
    mode: str
    status: str
    events: list[dict[str, Any]]
    final_draft: DraftVersion | None
    committed_draft: DraftVersion | None
    outcome: dict[str, Any]
    lane_b_rule_checks: dict[str, RuleCheckResult]
    fixture_rule_checks: dict[str, str]
    number_check_failures: int
    calculator_differences: list[dict[str, Any]]

    @property
    def committed_version(self) -> int | None:
        return None if self.committed_draft is None else self.committed_draft.version

    def rule_checks(self) -> dict[str, bool]:
        """Lane B's rule checks as booleans, named to merge with Lane A's (#7)."""
        return {name: r.passed for name, r in self.lane_b_rule_checks.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "mode": self.mode,
            "status": self.status,
            "committed_version": self.committed_version,
            "outcome": self.outcome,
            "lane_b_rule_checks": {n: {"passed": r.passed, "failures": list(r.failures)} for n, r in self.lane_b_rule_checks.items()},
            "fixture_rule_checks": dict(self.fixture_rule_checks),
            "number_check_failures": self.number_check_failures,
            "calculator_differences": self.calculator_differences,
            "events": self.events,
        }


def run_scenario(
    scenario: Scenario,
    calculators: Calculators,
    *,
    negotiator_factory: NegotiatorFactory = rules_negotiator,
    compare_with_stand_in: bool | None = None,
    minutes_per_turn: float = DEFAULT_MINUTES_PER_TURN,
    max_rounds: int = 30,
) -> ScenarioRun:
    """Run one fixture's negotiation, approvals, and faults, and check Lane B's rules.

    ``calculators`` is required: Lane A's real ones in the harness, the stand-ins only in
    unit tests. ``compare_with_stand_in`` defaults to comparing whenever ``calculators``
    aren't the stand-ins themselves. ``minutes_per_turn`` is how far the harness clock
    moves per turn (the contract doesn't say; **proposed** default ``DEFAULT_MINUTES_PER_TURN``).
    """
    if calculators is None:
        raise TypeError("run_scenario needs calculators: Lane A's real ones, or the stand-ins in a unit test")
    primary = calculators
    if compare_with_stand_in is None:
        compare_with_stand_in = type(primary) is not StandInCalculators
    log = EventLog()
    clock = {"now": scenario.start}
    calc = RecordedCalculators(primary, log, lambda: clock["now"],
                               reference=StandInCalculators(profiles=primary.profiles) if compare_with_stand_in else None)

    if len(scenario.offers) != 1:
        raise NotImplementedError(
            "this runner negotiates one surplus lot per fixture; competing lots share storage and trucks, "
            "and holding those across lots is Lane A's harness (#7)"
        )
    offer = scenario.offers[0]
    negotiators = {org: negotiator_factory(scenario.role_of(org), org, calc) for org in scenario.turn_order}
    labels = {org: negotiator_label(n) for org, n in negotiators.items()}
    log.add("scenario", scenario.start, scenario_id=scenario.scenario_id, title=scenario.title, mode=scenario.mode,
            synthetic=scenario.synthetic, note=scenario.note, lot_ids=[o.lot_id for o in scenario.offers],
            organizations=[{"organization_id": o.organization_id, "role": o.role.value, "name": o.name} for o in scenario.organizations],
            turn_order=list(scenario.turn_order), calculators=calc.label,
            compared_with=None if calc.reference is None else _label(calc.reference), negotiators=labels,
            request_codes=[r.request_code for r in scenario.requests], humans_are_scripted=True,
            rounds_without_new_terms=scenario.rounds_without_new_terms, minutes_per_turn=minutes_per_turn)

    run = _Run(scenario, offer, log, calc, clock)
    status, final, committed = run.go(negotiators, labels, minutes_per_turn, max_rounds)

    events = log.events
    checks = run_lane_b_rule_checks(events, primary.profiles)
    llm_failures = sum((e.get("llm") or {}).get("number_check_failures", 0) for e in events if e["kind"] == "move")
    return ScenarioRun(
        scenario_id=scenario.scenario_id,
        mode=scenario.mode,
        status=status,
        events=events,
        final_draft=final,
        committed_draft=committed,
        outcome=next((e for e in reversed(events) if e["kind"] == "outcome"), {}),
        lane_b_rule_checks=checks,
        fixture_rule_checks={name: FIXTURE_CHECKS_IN_HARNESS for name in scenario.rule_checks},
        number_check_failures=llm_failures,
        calculator_differences=[e for e in events if e["kind"] == "calculator_call" and e.get("difference_from_stand_in")],
    )


class _Run:
    def __init__(self, scenario: Scenario, offer: SurplusOffer, log: EventLog, calc: RecordedCalculators, clock: dict[str, datetime]):
        self.scenario, self.offer, self.log, self.calc, self.clock = scenario, offer, log, calc, clock
        self._facts: dict[str, tuple[int, Facts]] = {}
        self.negotiators: Mapping[str, Negotiator] = {}
        self._faults_logged: set[int] = set()

    def at(self, t: datetime) -> datetime:
        self.clock["now"] = t
        return t

    # Facts, rebuilt only when a newly known fault changes them

    def facts(self, org: str, now: datetime) -> Facts:
        self.at(now)
        known = self.scenario.faults_known_at(now)
        for i, fault in enumerate(self.scenario.faults):
            if fault in known and i not in self._faults_logged:
                self._log_fault(i, fault)
        cached = self._facts.get(org)
        if cached is not None and cached[0] == len(known):
            return cached[1]
        seqs = self.calc.capture(org, "facts")
        facts = facts_for(self.scenario, org, now, self.calc, lot=self.offer)
        self.log.add("facts", now, organization_id=org, role=self.scenario.role_of(org).value, facts=facts,
                     calculator_call_seqs=list(seqs), known_faults=[f.kind + "@" + f.food_bank_id for f in known])
        self._facts[org] = (len(known), facts)
        return facts

    def _log_fault(self, index: int, fault: Fault) -> dict[str, Any]:
        self._faults_logged.add(index)
        return self.log.add("fault", fault.at, fault_kind=fault.kind, food_bank_id=fault.food_bank_id, reading=fault.reading,
                            source=fault.source, synthetic=fault.synthetic)

    # The whole run

    def go(self, negotiators, labels, minutes_per_turn, max_rounds):
        s, offer, log = self.scenario, self.offer, self.log
        self.negotiators = negotiators
        now = self.at(max(s.start, offer.reported_at))
        if offer.recall_notice:
            log.add("stop", now, lot_id=offer.lot_id, version=None, rule="recalled", status="recalled",
                    reason="The lot has a recall notice, so it is never offered.")
            self._outcome(None, None, "recalled", "recalled: never offered")
            return "recalled", None, None

        for org in s.turn_order:
            self.facts(org, now)
        seqs = self.calc.capture(offer.donor_id, "offer")
        draft, skipped = offer_draft(s, offer, self.calc)
        log.add("version", now, lot_id=draft.lot_id, version=1, based_on_version=None, proposer_id=offer.donor_id, reason=draft.reason,
                move_seq=None, amendment=None, terms=draft_terms(draft), terms_hash=terms_hash(draft_terms(draft)),
                named_organizations=list(draft.named_organizations()), calculator_call_seqs=list(seqs),
                not_offered=[{"produce_id": n.produce_id, "reason": n.reason} for n in skipped])

        result = negotiate(
            draft, turn_order=s.turn_order, roles={o: s.role_of(o) for o in s.turn_order}, facts_at=self.facts,
            negotiators=negotiators, start=now, log=log, calculators=self.calc,
            rounds_without_new_terms=s.rounds_without_new_terms, minutes_per_turn=minutes_per_turn, max_rounds=max_rounds,
            labels=labels,
        )
        self.at(result.now)
        if result.status != "held":
            self._remaining_faults(None, None)
            self._outcome(result.draft, None, result.status, result.reason, skipped)
            return result.status, result.draft, None

        status, committed_at, why = self._approvals(result.draft, result.holds, result.now)
        committed = result.draft if status == "committed" else None
        self._remaining_faults(committed, committed_at)
        self._outcome(result.draft, committed, status, why, skipped)
        return status, result.draft, committed

    # Approvals: one per named organization, from its own (scripted) human, on this exact version

    def _approvals(self, draft: DraftVersion, holds: list[dict[str, Any]], now: datetime) -> tuple[str, datetime | None, str]:
        log, s = self.log, self.scenario
        th = terms_hash(draft_terms(draft))
        named = list(draft.named_organizations())
        log.add("approval_requested", now, lot_id=draft.lot_id, version=draft.version, terms_hash=th, organizations=named)
        answers, missing = [], []
        for org in named:
            script = s.humans.get(org)
            if script is None:
                missing.append(org)
                log.add("no_approval", now, lot_id=draft.lot_id, version=draft.version, organization_id=org,
                        reason="The fixture scripts no human for this organization, so it never approves.")
            else:
                answers.append((now + timedelta(minutes=script.after_minutes), org, script))
        for t, org, script in sorted(answers, key=lambda a: (a[0], a[1])):
            log.add("approval", t, lot_id=draft.lot_id, version=draft.version, terms_hash=th, organization_id=org,
                    decision=script.decision, source="scripted_human", after_minutes=script.after_minutes)
        declined = [org for _, org, script in answers if script.decision != "approve"]
        last = max((t for t, _, _ in answers), default=now)
        self.at(last)

        def stop(status: str, rule: str, reason: str):
            log.add("stop", last, lot_id=draft.lot_id, version=draft.version, rule=rule, status=status, reason=reason)
            return status, None, reason

        if declined:
            return stop("declined_by_human", "human_declined",
                        f"{', '.join(declined)} declined version {draft.version}, so nothing commits. The negotiation does not "
                        "resume in this run.")
        if missing:
            return stop("no_human_response", "no_human_response",
                        f"No approval from {', '.join(missing)} on version {draft.version}, so nothing commits.")
        hold_end = min((datetime.fromisoformat(h["end"]) for h in holds), default=draft.deadline)
        if last > draft.deadline or last > hold_end:
            return stop("unclaimed_deadline", "deadline",
                        f"The last approval came at {last.isoformat()}, after the {draft.deadline.isoformat()} deadline or a hold's "
                        "end, so nothing commits. Nothing is committed automatically.")
        log.add("commitment", last, lot_id=draft.lot_id, version=draft.version, terms_hash=th, organizations=named,
                approval_seqs=[e["seq"] for e in log.events if e["kind"] == "approval" and e["version"] == draft.version],
                hold_seqs=[h["seq"] for h in holds])
        return "committed", last, "Every named organization's human approved this version."

    # Faults after the negotiation

    def _remaining_faults(self, committed: DraftVersion | None, committed_at: datetime | None) -> None:
        for i, fault in enumerate(self.scenario.faults):
            if i in self._faults_logged or fault.at > self.scenario.end:
                continue
            self.at(fault.at)
            self._log_fault(i, fault)
            if fault.kind == "cooler_failure" and committed is not None and committed_at is not None and fault.at >= committed_at:
                self._cooler_failure(fault, committed)

    def _cooler_failure(self, fault: Fault, committed: DraftVersion) -> None:
        """Workflow 4 after a commitment. The failed food bank's own agent says what is at risk
        and asks the others; each candidate food bank's own agent answers from its own facts
        (standing in for its answer over AGNTCY, #21, #23); the failed food bank's agent chooses,
        with a reason card for every candidate. The runner only passes the messages."""
        s, calc, fb = self.scenario, self.calc, fault.food_bank_id
        if not committed.allocations_to(fb):
            return
        own = self.facts(fb, fault.at)
        first = len(self.log.events)
        agent = self._food_bank_agent(fb)
        calc.capture(fb, "cooler_failure")
        failure = agent.cooler_failure(own, committed, fault.at)
        if failure is None:
            # No pickup hours recorded: there is no households' pickup time to plan a move around.
            self.log.add("cooler_failure_assessment", fault.at, lot_id=committed.lot_id, version=committed.version, food_bank_id=fb,
                         items_to_move=[], items_staying=[], items_unsupported=[], reason_cards=[], proposal=None, fallback=[],
                         answers=[], not_assessed=True, problem=f"{own.name} has no pickup hours recorded, so there is no households' "
                         "pickup time to plan around. Its staff decide where the produce goes; nothing is proposed or committed.",
                         calculator_call_seqs=[e["seq"] for e in self.log.events[first:] if e["kind"] == "calculator_call"],
                         note="Lane B's cooler-failure logic (#15) needs the households' pickup time; none is recorded.")
            return
        answers = []
        for other in s.turn_order:
            if other == fb or s.role_of(other) is not Role.FOOD_BANK:
                continue
            theirs = self.facts(other, fault.at)  # that food bank's own facts, for its own agent
            calc.capture(other, "cooler_failure_answer")
            answers.append(self._food_bank_agent(other).answer_cold_space_request(theirs, committed, fault.at))
        calc.capture(fb, "cooler_failure_choice")
        d = agent.choose_cooler_receiver(failure, answers, s.travel_minutes_between_food_banks.get(fb, {}))
        p = d.proposal
        self.log.add(
            "cooler_failure_assessment", fault.at, lot_id=committed.lot_id, version=committed.version, food_bank_id=fb,
            items_to_move=d.items_to_move, items_staying=d.items_staying, items_unsupported=d.items_unsupported,
            reason_cards=[{"food_bank_id": c.food_bank_id, "name": c.name, "outcome": c.outcome, "text": c.text} for c in d.reason_cards],
            proposal=None if p is None else {**jsonable(p), "committed": p.committed},
            fallback=d.fallback,
            answers=[{**jsonable(a), "answered_by": a.food_bank_id} for a in answers],
            calculator_call_seqs=[e["seq"] for e in self.log.events[first:] if e["kind"] == "calculator_call"],
            note="Lane B's cooler-failure logic (#15). Each candidate food bank's own agent answered from its own facts (answers), "
                 "standing in for its answer over AGNTCY (#21, #23), and the failed food bank's agent chose from those answers. The "
                 "proposal awaits the receiving food bank's own decision and fresh approvals; nothing commits here.",
        )

    def _food_bank_agent(self, org: str) -> RulesFoodBank:
        """The food bank's own rules agent: its negotiator, or the rules agent an LLM negotiator
        falls back on. A negotiator with neither gets a rules agent for that organization only."""
        n = self.negotiators.get(org)
        for agent in (n, getattr(n, "rules", None)):
            if isinstance(agent, RulesFoodBank):
                return agent
        return RulesFoodBank(org, self.calc)

    # The outcome: every pound allocated or visibly unclaimed, with a reason

    def _outcome(self, draft: DraftVersion | None, committed: DraftVersion | None, status: str, why: str, skipped=()) -> None:
        log, calc = self.log, self.calc
        calc.capture("records", "outcome")
        items = []
        source = committed
        reason_unclaimed = why
        fair_share = []
        if committed is not None:
            # Fair-share accounting from the pooled counts: pounds beyond a food bank's gap are
            # recorded as beyond fair share and never count toward it.
            advocate = next((o for o in self.scenario.turn_order if self.scenario.role_of(o) is Role.ADVOCATE), None)
            gaps = self._facts[advocate][1].gaps if advocate is not None else ()
            for g in gaps:
                planned = committed.planned_lb(g.food_bank_id)
                after = calc.gap_after_plan(g.below_fair_share_lb, planned)
                fair_share.append({"food_bank_id": g.food_bank_id, "below_fair_share_lb": g.below_fair_share_lb,
                                   "planned_lb": planned, "remaining_gap_lb": after.remaining_gap_lb,
                                   "beyond_fair_share_lb": after.above_gap_lb})
            reason_unclaimed = (f"No food bank could store it, move it, or hand it out before it spoils under version "
                                f"{committed.version}, toward its households' fair share or beyond it.")
        lot_items = draft.items if draft is not None else ()
        for item in lot_items:
            allocations = [] if source is None else [
                {"food_bank_id": a.food_bank_id, "pounds": a.pounds,
                 "mover": None if source.transport(a.food_bank_id) is None else source.transport(a.food_bank_id).mover.value}
                for a in source.allocations if a.produce_id == item.produce_id
            ]
            unclaimed = item.pounds - sum(a["pounds"] for a in allocations)
            items.append({"produce_id": item.produce_id, "pounds": item.pounds, "allocations": allocations,
                          "unclaimed_lb": unclaimed, "unclaimed_reason": reason_unclaimed if unclaimed else None})
        log.add("outcome", self.clock["now"], lot_id=self.offer.lot_id, status=status, reason=why,
                committed_version=None if committed is None else committed.version, items=items, fair_share=fair_share,
                not_offered=[{"produce_id": n.produce_id, "reason": n.reason} for n in skipped],
                pathways_after_commitment="pickup notices, confirmations, and releases are Lane A's harness (#7)")
