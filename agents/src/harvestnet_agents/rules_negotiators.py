"""Rules-based negotiators for donors, food banks, and the advocate (ticket #11).

Each negotiator decides only for its own organization (ADR 0001). It reads the current
draft version, its own specialists' facts, and its turn, and returns one ``Move`` from
the proposed interface in ``negotiation.py``. Derived numbers come from the calculator
interface (stand-ins in ``calculators.py`` until Lane A's are joined), and every move's
reason is built only from the draft, the facts, and calculator results (ADR 0002). Rules
read produce profile fields, never crop names (ADR 0003).

What each says yes to (docs/MVP_DESIGN.md section 6, Proposed):

- **Donor**: accepts only a version where every allocated share leaves by its deadline
  and every drop-off fits its vehicle, route, and time; unallocated pounds are named as
  unclaimed. It offers a drop-off where its ability allows, and otherwise asks the food
  bank to collect. It asks its human about any condition doubt before offering.
- **Food bank**: accepts only what its facts allow (storage at arrival, pickup hours,
  truck, and households collecting before the produce spoils). It counters with one
  amendment plus a reason, bids toward its households' fair-share gap first, only for
  produce it can receive, rejects produce not fit for people, and asks its human about
  any condition doubt. Once the version plans its whole gap, it may bid **beyond fair
  share** for produce still unclaimed, so surplus goes out rather than waste
  (docs/MVP_DESIGN.md section 8; user direction, October 11, 2026). Those bids are
  bounded only by its own facts and calculators, and their reasons say "beyond fair
  share".
- **Food bank in a contest** (ADR 0013): while its households are below fair share and
  nothing unclaimed is something it can receive, it may **contest** another food bank's
  share, shifting pounds of one item from that food bank to itself, up to its own gap and
  within the same limits as its bids. When a contest takes pounds from its share, it
  concedes pounds beyond its own gap and may **take back** pounds within it. It sees only
  its own facts and the shared draft, never another food bank's gap.
- **Advocate**: never accepts, rejects, holds, or vetoes. It proposes one amendment
  toward the food bank with the largest fair-share gap, or passes. In a contest it may
  back either side, whichever food bank is further below fair share.

Each organization requests holds on its own resources once every organization named in
the version has accepted it. Nothing here commits anything: commitment needs every
named organization's human to approve the same version, elsewhere.

The decision order and tie-breaks are **proposed** and listed in each class.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from .calculators import Calculators, StandInCalculators
from .cooler_failure import (
    Candidate,
    ColdSpaceAnswer,
    CoolerFailure,
    CoolerFailureDecision,
    HeldItem,
    PickupWindow,
    assess_cooler_failure,
)
from .cooler_failure import Truck as CoolerTruck
from .negotiation import (
    AdvocateFacts,
    AgentInput,
    Amendment,
    DonorFacts,
    DraftError,
    DraftVersion,
    FoodBankFacts,
    FoodBankGap,
    HoldRequest,
    LotItem,
    Move,
    MoveKind,
    Mover,
    POUNDS_TOLERANCE,
    Role,
    SetPounds,
    SetTransport,
    ShiftPounds,
    Transport,
)
from .profiles import STORAGE_COLD, STORAGE_DRY, ProduceProfile, ProfileSet
from .wording import clock as _clock, join as _join, lb as _lb, window as _window

__all__ = [
    "Problem",
    "RulesAdvocate",
    "RulesDonor",
    "RulesFoodBank",
    "TurnError",
    "rules_negotiator",
]


class TurnError(ValueError):
    """A negotiator was asked to move out of turn, or with another organization's facts."""


@dataclass(frozen=True)
class Problem:
    """One reason this organization can't accept the version as it stands."""

    code: str
    kind: MoveKind  # the move it leads to: counter, reject, or ask_human
    text: str
    amendment: Amendment | None = None


class _Negotiator:
    role: Role

    def __init__(self, organization_id: str, calculators: Calculators | None = None):
        self.organization_id = organization_id
        self.calculators = calculators if calculators is not None else StandInCalculators()

    @property
    def profiles(self) -> ProfileSet:
        return self.calculators.profiles

    def _check_turn(self, agent_input: AgentInput, facts_type: type, facts_id: str | None) -> None:
        if agent_input.turn.organization_id != self.organization_id:
            raise TurnError(f"it is {agent_input.turn.organization_id}'s turn, not {self.organization_id}'s")
        if not isinstance(agent_input.facts, facts_type) or (facts_id is not None and facts_id != self.organization_id):
            raise TurnError(f"{self.organization_id} can only use its own specialists' facts")

    def _move(self, draft: DraftVersion, kind: MoveKind, reason: str, amendment: Amendment | None = None, holds=()) -> Move:
        return Move(self.organization_id, self.role, draft.version, kind, reason, amendment=amendment, holds=tuple(holds))

    def _profile(self, produce_id: str) -> ProduceProfile | None:
        return self.profiles.get(produce_id) if produce_id in self.profiles else None

    def _item_name(self, produce_id: str) -> str:
        profile = self._profile(produce_id)
        return profile.name if profile else produce_id


# --- Donor --------------------------------------------------------------------------------


class RulesDonor(_Negotiator):
    """Decision order (proposed): deadline passed -> reject; condition doubt -> ask a
    human; then, per food bank in draft order: no transport line -> offer a drop-off
    within ability, else ask the food bank to collect; departure after the deadline ->
    move it to the deadline; a drop-off beyond ability -> ask the food bank to collect.
    With no problem: request holds if everyone named accepted, else accept."""

    role = Role.DONOR

    def move(self, agent_input: AgentInput) -> Move:
        facts = agent_input.facts
        self._check_turn(agent_input, DonorFacts, getattr(facts, "donor_id", None))
        draft = agent_input.draft
        problems = self.review(agent_input)
        if problems:
            p = problems[0]
            return self._move(draft, p.kind, p.text, p.amendment)
        if not draft.named_food_banks():
            return self._move(draft, MoveKind.PASS,
                              f"Version {draft.version} names no food bank yet; waiting for bids before our "
                              f"{_clock(draft.deadline)} deadline. " + _unclaimed_sentence(draft, self._item_name))
        if set(draft.named_organizations()) <= set(agent_input.turn.accepted_by):
            return self._holds(draft, agent_input.turn.now)
        return self._move(draft, MoveKind.ACCEPT, self._accept_reason(draft, facts))

    def review(self, agent_input: AgentInput) -> list[Problem]:
        """Every problem with this version, in decision order. Empty means it can accept."""
        draft, facts, now = agent_input.draft, agent_input.facts, agent_input.turn.now
        deadline = _clock(draft.deadline)
        if now > draft.deadline:
            return [Problem("deadline_passed", MoveKind.REJECT,
                            f"Version {draft.version}: the {deadline} pickup deadline has passed with no commitment, "
                            "so the produce is unclaimed. Nothing is committed automatically.")]
        for item in draft.items:
            if item.condition_doubt:
                return [Problem("condition_doubt", MoveKind.ASK_HUMAN,
                                f"{self._item_name(item.produce_id)}: {item.condition_doubt}. Our staff must check its "
                                "condition before it is offered.")]

        problems: list[Problem] = []
        for fb in draft.named_food_banks():
            name = draft.name_of(fb)
            tr = draft.transport(fb)
            if tr is None:
                problems.append(self._propose_transport(draft, facts, fb))
                continue
            if tr.departs_at > draft.deadline:
                arrives = self._arrival(facts, fb, draft.deadline)
                problems.append(Problem(
                    "departs_after_deadline", MoveKind.COUNTER,
                    f"The share for {name} would leave at {_clock(tr.departs_at)}, after our {deadline} deadline. "
                    f"It must leave by {deadline}.",
                    SetTransport(fb, tr.mover, draft.deadline, arrives if arrives else draft.deadline),
                ))
                continue
            if tr.mover is Mover.DONOR:
                why = self._drop_off_problem(draft, facts, fb, tr.departs_at)
                drop = facts.drop_off
                if why and drop is not None and drop.window.start <= draft.deadline \
                        and self._drop_off_problem(draft, facts, fb, drop.window.start) is None \
                        and (arrives := self._arrival(facts, fb, drop.window.start)) is not None:
                    # Only the time is wrong: offer the drop-off at a time we can do it.
                    problems.append(Problem(
                        "retime_drop_off", MoveKind.COUNTER,
                        f"We can drop off at {name}, but {why}. Offering to leave at {_clock(drop.window.start)}, before "
                        f"our {deadline} deadline, arriving at {_clock(arrives)}.",
                        SetTransport(fb, Mover.DONOR, drop.window.start, arrives),
                    ))
                elif why:
                    problems.append(Problem(
                        "drop_off_beyond_ability", MoveKind.COUNTER,
                        f"We can't drop off at {name}: {why}. Asking {name} to collect at the same times.",
                        SetTransport(fb, Mover.FOOD_BANK, tr.departs_at, tr.arrives_at),
                    ))
        return problems

    def _propose_transport(self, draft: DraftVersion, facts: DonorFacts, fb: str) -> Problem:
        name = draft.name_of(fb)
        drop = facts.drop_off
        if drop is not None and drop.window.start <= draft.deadline:
            depart = drop.window.start
            why = self._drop_off_problem(draft, facts, fb, depart)
            arrives = self._arrival(facts, fb, depart)
            if why is None and arrives is not None:
                return Problem(
                    "offer_drop_off", MoveKind.COUNTER,
                    f"We can drop off {_lb(draft.planned_lb(fb))} lb at {name}: we leave at {_clock(depart)}, before our "
                    f"{_clock(draft.deadline)} deadline, and arrive at {_clock(arrives)}.",
                    SetTransport(fb, Mover.DONOR, depart, arrives),
                )
        arrives = self._arrival(facts, fb, draft.deadline)
        if arrives is None:
            return Problem("no_route", MoveKind.ASK_HUMAN,
                           f"We have no recorded travel time to {name}, so our staff must arrange how the produce moves.")
        reason = "we can't drop off there" if drop is None or fb not in drop.food_bank_ids else self._drop_off_problem(
            draft, facts, fb, drop.window.start) or "our drop-off window doesn't fit"
        return Problem(
            "ask_collection", MoveKind.COUNTER,
            f"Asking {name} to collect by our {_clock(draft.deadline)} deadline, since {reason}.",
            SetTransport(fb, Mover.FOOD_BANK, draft.deadline, arrives),
        )

    def _drop_off_problem(self, draft: DraftVersion, facts: DonorFacts, fb: str, departs_at: datetime) -> str | None:
        drop = facts.drop_off
        if drop is None:
            return "we have no vehicle free for drop-offs today"
        if fb not in drop.food_bank_ids:
            return f"{draft.name_of(fb)} isn't on a route we can drive"
        cold = [self._item_name(a.produce_id) for a in draft.allocations_to(fb) if self._needs_cold_chain(a.produce_id)]
        if cold and not drop.refrigerated:
            return f"our vehicle isn't refrigerated and {_join(cold)} needs a cold chain"
        if not drop.window.contains(departs_at):
            return f"we can only leave between {_clock(drop.window.start)} and {_clock(drop.window.end)}"
        # The drop-off window is when our vehicle is free, like a food bank's truck window:
        # the whole trip fits in it, arrival included (the harness checks the same, #20).
        arrives = self._arrival(facts, fb, departs_at)
        if arrives is not None and not drop.window.contains(arrives):
            return f"leaving at {_clock(departs_at)} we'd arrive at {_clock(arrives)}, but our vehicle is only free until {_clock(drop.window.end)}"
        load = sum(
            draft.planned_lb(other)
            for other in draft.named_food_banks()
            if other == fb or ((tr := draft.transport(other)) is not None and tr.mover is Mover.DONOR)
        )
        if load > drop.capacity_lb:
            return f"drop-offs would total {_lb(load)} lb, over our vehicle's {_lb(drop.capacity_lb)} lb"
        return None

    def _needs_cold_chain(self, produce_id: str) -> bool:
        profile = self._profile(produce_id)
        return profile is None or profile.transport.cold_required  # unknown: never assume it travels warm

    def _arrival(self, facts: DonorFacts, fb: str, departs_at: datetime) -> datetime | None:
        minutes = facts.travel_minutes.get(fb)
        return None if minutes is None else self.calculators.arrival_time(departs_at, minutes)

    def _accept_reason(self, draft: DraftVersion, facts: DonorFacts) -> str:
        parts = [f"Version {draft.version} works for us."]
        legs = []
        donor_lb = 0.0
        for fb in draft.named_food_banks():
            tr = draft.transport(fb)
            who = "we drop off" if tr.mover is Mover.DONOR else f"{draft.name_of(fb)} collects"
            legs.append(f"{draft.name_of(fb)} {_lb(draft.planned_lb(fb))} lb ({who}, leaving {_clock(tr.departs_at)})")
            if tr.mover is Mover.DONOR:
                donor_lb += draft.planned_lb(fb)
        if legs:
            parts.append(f"Every share leaves by our {_clock(draft.deadline)} deadline: " + "; ".join(legs) + ".")
        if donor_lb and facts.drop_off:
            parts.append(f"Our drop-offs total {_lb(donor_lb)} lb, within our vehicle's {_lb(facts.drop_off.capacity_lb)} lb.")
        parts.append(_unclaimed_sentence(draft, self._item_name))
        return " ".join(parts)

    def _holds(self, draft: DraftVersion, now: datetime) -> Move:
        total = sum(draft.planned_lb(fb) for fb in draft.named_food_banks())
        holds = [HoldRequest("lot", self.organization_id, total, min(now, draft.deadline), draft.deadline)]
        dropped = [draft.transport(fb) for fb in draft.named_food_banks() if draft.transport(fb).mover is Mover.DONOR]
        if dropped:
            donor_lb = sum(draft.planned_lb(tr.food_bank_id) for tr in dropped)
            holds.append(HoldRequest("drop_off", self.organization_id, donor_lb,
                                     min(tr.departs_at for tr in dropped), max(tr.arrives_at for tr in dropped)))
        reason = (f"Everyone named has accepted version {draft.version}. Holding the {_lb(total)} lb in the plan "
                  f"until our {_clock(draft.deadline)} deadline"
                  + (f", and our drop-off of {_lb(holds[1].pounds)} lb, {_clock(holds[1].start)} to {_clock(holds[1].end)}"
                     if dropped else "")
                  + ", pending our staff's approval.")
        return self._move(draft, MoveKind.REQUEST_HOLD, reason, holds=holds)


# --- Food bank ----------------------------------------------------------------------------


@dataclass(frozen=True)
class _Arrival:
    at: datetime
    transport: Transport | None  # None: estimated for a bid, before a transport line exists


@dataclass(frozen=True)
class _Seen:
    version: int  # the version we last moved on
    before: DraftVersion | None  # the draft after our turn before that one
    after: DraftVersion  # the draft after the move we sent on ``version``


@dataclass(frozen=True)
class _Loss:
    produce_id: str
    to_food_bank_id: str  # the food bank whose line of the item grew since our last turn
    lost_lb: float  # a calculator result: our line then, less our line now


@dataclass(frozen=True)
class _Receivable:
    arrival: _Arrival
    pickup: Any  # the pickup_feasibility result
    cold: bool
    uses_truck: bool
    room_lb: float  # storage room in the item's class, at arrival and until pickup ends
    limit_lb: float  # that room, and our truck's room when we collect


class RulesFoodBank(_Negotiator):
    """Decision order (proposed): per allocated item, not fit for people -> reject; no
    profile or condition doubt -> ask a human. Then transport: no line -> ask the donor to
    drop off if offered and suitable, else collect with its own truck, else remove the item;
    a collection its truck can't do -> switch to the donor's drop-off if suitable, else
    reduce or remove. Then households can't collect before it spoils (pickup hours, or its
    produce profile's usable days in the storage it would sit in) -> remove that item;
    storage at arrival is short -> reduce the longest-lived item in that storage. With no
    problem: bid toward its fair-share gap on the shortest-lived item it can receive; once
    the version plans its whole gap, bid beyond fair share the same way; else request
    holds if everyone named accepted, accept if named, or pass.

    Each bid is wholly toward fair share or wholly beyond it, never both: a bid toward the
    gap stops at the gap, and only the next bid can go past it. A bid's limits are the
    unclaimed pounds, its storage room in the item's storage class at arrival and when
    pickup ends (storage over time), its truck's room when it collects, and, toward fair
    share only, the gap. Beyond fair share has no other limit.

    The donor's drop-off capacity is the donor's fact, not ours, so an extra bid can ask
    more than its vehicle holds. The donor then asks us to collect. When we can't, and we
    hold pounds beyond fair share, we take some of those back (never fair-share pounds)
    before asking for the drop-off again, and we remember, for this lot, that the donor
    turned down our drop-off at that load: no more extra bids that rely on its drop-off.
    That memory is only what this organization saw in the shared draft (proposed).

    Contests (ADR 0013, decision order proposed): after its problems and bids, a food bank
    whose households are still below fair share first takes back pounds a contest took from
    its share since its last turn, then contests another food bank's share. Both are a
    ``ShiftPounds`` of one item from one other food bank to itself, no more than its remaining
    gap, and limited like a bid (``_receivable``). A take-back is also no more than the pounds
    it lost. A contest takes from the largest other line of the shortest-lived item it can
    receive (ties: food bank id). When its households already have their fair share, it
    concedes what it lost and says so. It never fights for pounds beyond fair share. What it
    lost is read from its own memory of the shared draft after its last turn, per lot."""

    role = Role.FOOD_BANK
    contests = True  # ADR 0013; the evaluation's baselines turn it off, to stay the old mechanism

    def __init__(self, organization_id: str, calculators: Calculators | None = None):
        super().__init__(organization_id, calculators)
        self._drop_off_refused_at: dict[str, float] = {}  # lot id -> our planned pounds when the donor said no
        self._seen: dict[str, _Seen] = {}  # lot id -> the shared draft around our last turn

    def move(self, agent_input: AgentInput) -> Move:
        facts = agent_input.facts
        self._check_turn(agent_input, FoodBankFacts, getattr(facts, "food_bank_id", None))
        draft = agent_input.draft
        self._note_drop_off_refusal(draft, facts)
        before = self._before(draft)
        move = self._decide(agent_input, facts, before)
        self.note_sent(agent_input, move, before)
        return move

    def note_sent(self, agent_input: AgentInput, move: Move, before: DraftVersion | None = None) -> None:
        """Remember the shared draft as it stands after the move we sent on this version, so
        next turn we can tell which of our pounds another organization moved. Whoever sends a
        move for us (our LLM negotiator) calls this with the move it actually sent."""
        draft = agent_input.draft
        if before is None:
            before = self._before(draft)
        after = draft
        if move.kind is MoveKind.COUNTER and move.amendment is not None:
            try:
                after = draft.amend(move.amendment, proposer_id=self.organization_id, reason=move.reason)
            except DraftError:
                after = draft
        self._seen[draft.lot_id] = _Seen(draft.version, before, after)

    def _before(self, draft: DraftVersion) -> DraftVersion | None:
        """The shared draft after our previous turn on this lot (the same answer if asked twice
        on one version), or None on our first turn."""
        seen = self._seen.get(draft.lot_id)
        if seen is None:
            return None
        return seen.before if seen.version == draft.version else seen.after

    def _decide(self, agent_input: AgentInput, facts: FoodBankFacts, before: DraftVersion | None) -> Move:
        draft = agent_input.draft
        problems = self.review(agent_input)
        if problems:
            p = problems[0]
            return self._move(draft, p.kind, p.text, p.amendment)
        bid = self._bid(draft, facts)
        if bid is not None:
            return bid
        losses = self._losses(draft, before)
        if self.contests:
            gap = self.calculators.gap_after_plan(facts.demand.below_fair_share_lb, draft.planned_lb(self.organization_id))
            if gap.remaining_gap_lb > 0:
                claim = self._take_back(draft, facts, losses, gap.remaining_gap_lb) or self._contest(draft, facts, gap.remaining_gap_lb)
                if claim is not None:
                    return claim
        concede = self._concession(draft, facts, losses)
        me = self.organization_id
        if me not in draft.named_food_banks():
            return self._move(draft, MoveKind.PASS, concede + self._pass_reason(draft, facts))
        if set(draft.named_organizations()) <= set(agent_input.turn.accepted_by):
            return self._holds(draft, facts, concede)
        return self._move(draft, MoveKind.ACCEPT, concede + self._accept_reason(draft, facts))

    def review(self, agent_input: AgentInput) -> list[Problem]:
        """Every problem with this food bank's share, in decision order. Empty: it fits."""
        draft, facts = agent_input.draft, agent_input.facts
        me = self.organization_id
        mine = draft.allocations_to(me)
        if not mine:
            return []
        problems: list[Problem] = []
        for a in mine:
            item, name = draft.item(a.produce_id), self._item_name(a.produce_id)
            if item.condition_grade == "not_for_people":
                problems.append(Problem("not_for_people", MoveKind.REJECT,
                                        f"{name} is graded not fit for people by the donor's check, so we can't take it."))
            elif self._profile(a.produce_id) is None:
                problems.append(Problem("no_profile", MoveKind.ASK_HUMAN,
                                        f"{name} has no produce profile, so our manager must check it before we decide."))
            elif item.condition_doubt:
                problems.append(Problem("condition_doubt", MoveKind.ASK_HUMAN,
                                        f"{name}: {item.condition_doubt}. Our manager must check its condition first."))
        if problems:
            return problems

        tr = draft.transport(me)
        if tr is None:
            return [self._propose_transport(draft, facts)]
        truck_problem = self._truck_problem(draft, facts, tr) if tr.mover is Mover.FOOD_BANK else None
        if truck_problem:
            problems.append(truck_problem)

        for a in mine:
            item, name = draft.item(a.produce_id), self._item_name(a.produce_id)
            check = self.calculators.pickup_feasibility(tr.arrives_at, facts.pickup_windows, item.usable_until)
            if not check.feasible:
                problems.append(Problem(
                    "cannot_collect_in_time", MoveKind.COUNTER,
                    f"Our households can't collect {name.lower()} before it spoils: "
                    + _pickup_problem_text(check, tr.arrives_at, item.usable_until, facts)
                    + ". Removing it from our share.",
                    SetPounds(a.produce_id, me, 0),
                ))
            elif not self._keeps_until(a.produce_id, tr.arrives_at, check.collect.end):
                problems.append(Problem(
                    "spoils_in_storage", MoveKind.COUNTER,
                    f"Our households can't collect {name.lower()} before it spoils: its produce profile doesn't keep it "
                    f"usable in {self._storage_label(a.produce_id)} storage until pickup ends at {_clock(check.collect.end)}. "
                    "Removing it from our share.",
                    SetPounds(a.produce_id, me, 0),
                ))

        problems.extend(self._storage_problems(draft, facts, tr.arrives_at))
        return problems

    # Transport

    def _drop_off_suits(self, draft: DraftVersion, produce_ids: Sequence[str]) -> bool:
        if self.organization_id not in draft.drop_off_to:
            return False
        return draft.drop_off_refrigerated or not any(self._cold_chain(p) for p in produce_ids)

    def _cold_chain(self, produce_id: str) -> bool:
        profile = self._profile(produce_id)
        return profile is None or profile.transport.cold_required

    def _needs_cold_storage(self, produce_id: str) -> bool:
        profile = self._profile(produce_id)
        return profile is None or profile.needs_cold

    def _storage_label(self, produce_id: str) -> str:
        return "cold" if self._needs_cold_storage(produce_id) else "dry"

    def _keeps_until(self, produce_id: str, arrives_at: datetime, until: datetime) -> bool:
        """Whether the produce profile keeps this item usable, in the storage class it would
        sit in here (cold if it needs cold, else dry), from arrival until ``until``. Uses
        the profile's shortest stated life; a profile with no life for that storage (for
        example, cold storage not recommended) never keeps it (ADR 0003)."""
        profile = self._profile(produce_id)
        if profile is None:
            return False
        days = profile.days_usable_cold if self._needs_cold_storage(produce_id) else profile.days_usable_room
        return days is not None and until - arrives_at <= timedelta(days=days.min)

    def _collection(self, draft: DraftVersion, facts: FoodBankFacts, produce_ids: Sequence[str], pounds: float):
        """(departs, arrives) for collecting with our own truck, or the reason we can't."""
        truck = facts.truck
        if truck is None:
            return None, "we have no truck free today"
        if facts.travel_minutes_from_donor is None:
            return None, "we have no recorded travel time from the donor"
        if any(self._cold_chain(p) for p in produce_ids) and not truck.refrigerated:
            return None, "our truck isn't refrigerated"
        if truck.window.start > draft.deadline:
            return None, f"our truck is only free from {_clock(truck.window.start)}, after the donor's deadline"
        depart = truck.window.start
        arrive = self.calculators.arrival_time(depart, facts.travel_minutes_from_donor)
        if arrive > truck.window.end:
            return None, f"our truck is only free until {_clock(truck.window.end)}"
        if pounds > truck.capacity_lb:
            return None, f"our truck holds {_lb(truck.capacity_lb)} lb"
        return (depart, arrive), None

    def _propose_transport(self, draft: DraftVersion, facts: FoodBankFacts) -> Problem:
        me, mine = self.organization_id, draft.allocations_to(self.organization_id)
        ids = [a.produce_id for a in mine]
        donor = draft.name_of(draft.donor_id)
        if self._drop_off_suits(draft, ids) and facts.travel_minutes_from_donor is not None:
            arrive = self.calculators.arrival_time(draft.deadline, facts.travel_minutes_from_donor)
            why = "we have no truck free today" if facts.truck is None else "that saves our truck for other runs"
            return Problem(
                "ask_drop_off", MoveKind.COUNTER,
                f"Asking {donor} to drop off our {_lb(draft.planned_lb(me))} lb, as it offered, since {why}. "
                f"Leaving by its {_clock(draft.deadline)} deadline, it arrives at {_clock(arrive)}.",
                SetTransport(me, Mover.DONOR, draft.deadline, arrive),
            )
        times, why_not = self._collection(draft, facts, ids, draft.planned_lb(me))
        if times is not None:
            return Problem(
                "offer_collection", MoveKind.COUNTER,
                f"We will collect our {_lb(draft.planned_lb(me))} lb with our truck, leaving {donor} at "
                f"{_clock(times[0])} and arriving at {_clock(times[1])}.",
                SetTransport(me, Mover.FOOD_BANK, times[0], times[1]),
            )
        return self._remove_unmovable(draft, why_not)

    def _cannot_collect(self, draft: DraftVersion, facts: FoodBankFacts, tr: Transport) -> str | None:
        """Why our truck can't do this collection (capacity aside), or None if it can."""
        ids = [a.produce_id for a in draft.allocations_to(self.organization_id)]
        truck = facts.truck
        if truck is None:
            return "we have no truck free today"
        if any(self._cold_chain(p) for p in ids) and not truck.refrigerated:
            return "our truck isn't refrigerated"
        if not (truck.window.contains(tr.departs_at) and truck.window.contains(tr.arrives_at)):
            return f"our truck is only free {_clock(truck.window.start)} to {_clock(truck.window.end)}"
        return None

    def _note_drop_off_refusal(self, draft: DraftVersion, facts: FoodBankFacts) -> None:
        """We never ask to collect when we can't, so a draft asking us to collect, where the
        donor offered us a suitable drop-off, means the donor turned that drop-off down. It
        counts on the donor's own version, or the first time we see it on someone else's;
        never on our own (that is us taking pounds back while the line still says collect)."""
        me, tr = self.organization_id, draft.transport(self.organization_id)
        ids = [a.produce_id for a in draft.allocations_to(me)]
        if not (tr is not None and tr.mover is Mover.FOOD_BANK and ids and self._drop_off_suits(draft, ids)
                and self._cannot_collect(draft, facts, tr) is not None):
            return
        seen = self._drop_off_refused_at.get(draft.lot_id)
        if draft.proposer_id == draft.donor_id or (seen is None and draft.proposer_id != me):
            self._drop_off_refused_at[draft.lot_id] = draft.planned_lb(me) if seen is None else min(seen, draft.planned_lb(me))

    def _take_back_beyond_fair_share(self, draft: DraftVersion, facts: FoodBankFacts, why: str) -> Problem | None:
        """After the donor turned down our drop-off at this load, take back pounds we asked
        for beyond fair share, on our longest-lived item, before asking again."""
        me = self.organization_id
        refused = self._drop_off_refused_at.get(draft.lot_id)
        if refused is None or draft.planned_lb(me) < refused:
            return None  # not refused at this load: we already took some back, so ask again
        above = self.calculators.gap_after_plan(facts.demand.below_fair_share_lb, draft.planned_lb(me)).above_gap_lb
        if above <= 0:
            return None
        a = max(draft.allocations_to(me), key=lambda a: (draft.item(a.produce_id).usable_until, a.produce_id))
        back = min(a.pounds, above)
        donor = draft.name_of(draft.donor_id)
        return Problem(
            "take_back_beyond_fair_share", MoveKind.COUNTER,
            f"{donor} asks us to collect our {_lb(draft.planned_lb(me))} lb instead of dropping it off, and we can't: {why}. "
            f"{_lb(above)} lb of our share is beyond fair share, so we take back {_lb(back)} lb of "
            f"{self._item_name(a.produce_id).lower()} we asked for beyond fair share and keep our households' fair share.",
            SetPounds(a.produce_id, me, self.calculators.adjust_pounds(a.pounds, -back)),
        )

    def _truck_problem(self, draft: DraftVersion, facts: FoodBankFacts, tr: Transport) -> Problem | None:
        me, mine = self.organization_id, draft.allocations_to(self.organization_id)
        ids = [a.produce_id for a in mine]
        truck = facts.truck
        why = self._cannot_collect(draft, facts, tr)
        if why is None and draft.planned_lb(me) > truck.capacity_lb:
            fit = self.calculators.capacity_fit(truck.capacity_lb, draft.planned_lb(me))
            a = max(mine, key=lambda a: (draft.item(a.produce_id).usable_until, a.produce_id))
            return Problem(
                "truck_capacity", MoveKind.COUNTER,
                f"Our truck holds {_lb(truck.capacity_lb)} lb, {_lb(fit.over_by_lb)} lb less than our share. "
                f"Taking {_lb(fit.over_by_lb)} lb less {self._item_name(a.produce_id).lower()}, which keeps longest.",
                SetPounds(a.produce_id, me, max(0.0, a.pounds - fit.over_by_lb)),
            )
        if why is None:
            return None
        if self._drop_off_suits(draft, ids):
            take_back = self._take_back_beyond_fair_share(draft, facts, why)
            if take_back is not None:
                return take_back
            return Problem(
                "ask_drop_off", MoveKind.COUNTER,
                f"We can't collect: {why}. Asking {draft.name_of(draft.donor_id)} to drop off instead, as it offered.",
                SetTransport(me, Mover.DONOR, tr.departs_at, tr.arrives_at),
            )
        return self._remove_unmovable(draft, why)

    def _remove_unmovable(self, draft: DraftVersion, why: str) -> Problem:
        me, mine = self.organization_id, draft.allocations_to(self.organization_id)
        # Remove a cold-chain item first: it is the one most likely to block the move.
        a = sorted(mine, key=lambda a: (not self._cold_chain(a.produce_id), a.produce_id))[0]
        offer = "the donor's drop-off isn't offered here"
        if me in draft.drop_off_to:
            offer = "the donor's drop-off isn't refrigerated"
        return Problem(
            "cannot_move", MoveKind.COUNTER,
            f"We have no way to move {self._item_name(a.produce_id).lower()} here: {why}, and {offer}. "
            "Removing it from our share.",
            SetPounds(a.produce_id, me, 0),
        )

    # Storage

    def _storage_problems(self, draft: DraftVersion, facts: FoodBankFacts, arrives_at: datetime) -> list[Problem]:
        me, mine = self.organization_id, draft.allocations_to(self.organization_id)
        free = self.calculators.storage_at(facts.storage, arrives_at)
        problems = []
        for cold, free_lb, label in ((True, free.cold_free_lb, "cold"), (False, free.dry_free_lb, "dry")):
            lines = [a for a in mine if self._needs_cold_storage(a.produce_id) == cold]
            if not lines:
                continue
            needed = sum(a.pounds for a in lines)
            fit = self.calculators.capacity_fit(free_lb, needed)
            if fit.fits:
                continue
            a = max(lines, key=lambda a: (draft.item(a.produce_id).usable_until, a.produce_id))
            problems.append(Problem(
                "storage_short", MoveKind.COUNTER,
                f"At arrival ({_clock(arrives_at)}) we have {_lb(free_lb)} lb of {label} space free and our share needs "
                f"{_lb(needed)} lb, {_lb(fit.over_by_lb)} lb too much. Taking {_lb(fit.over_by_lb)} lb less "
                f"{self._item_name(a.produce_id).lower()}.",
                SetPounds(a.produce_id, me, max(0.0, a.pounds - fit.over_by_lb)),
            ))
        return problems

    # Bidding

    def _bid(self, draft: DraftVersion, facts: FoodBankFacts) -> Move | None:
        """Fair share first (docs/MVP_DESIGN.md section 8): while this version leaves our
        households below fair share, every bid goes toward that gap. Only once it plans our
        whole gap do we bid beyond it, so surplus still goes out rather than waste. What we
        see is our own facts and the shared draft; other food banks' gaps are the
        advocate's to argue, and it can shift pounds planned above our gap to theirs."""
        me = self.organization_id
        gap = self.calculators.gap_after_plan(facts.demand.below_fair_share_lb, draft.planned_lb(me))
        shortfall = gap.remaining_gap_lb if gap.remaining_gap_lb > 0 else None  # None: beyond fair share
        candidates = [i for i in draft.items if draft.unallocated_lb(i.produce_id) > 0]
        for item in sorted(candidates, key=lambda i: (i.usable_until, i.produce_id)):
            bid = self._bid_for(draft, facts, item, shortfall)
            if bid is not None:
                return bid
        return None

    def _receivable(self, draft: DraftVersion, facts: FoodBankFacts, item: LotItem) -> _Receivable | None:
        """How many more pounds of ``item`` we could receive and hand out under this version, by
        our own facts only: storage room in its class at arrival and when pickup ends (storage
        over time), our truck's room when we collect, pickup hours before it spoils, and its
        produce profile. None when we can't take any of it."""
        me, pid = self.organization_id, item.produce_id
        if item.condition_grade == "not_for_people" or item.condition_doubt or self._profile(pid) is None:
            return None
        ids = [a.produce_id for a in draft.allocations_to(me)] + [pid]
        arrival = self._bid_arrival(draft, facts, ids)
        if arrival is None:
            return None
        collecting = arrival.transport is not None and arrival.transport.mover is Mover.FOOD_BANK
        uses_truck = collecting or (arrival.transport is None and not self._drop_off_suits(draft, ids))
        pickup = self.calculators.pickup_feasibility(arrival.at, facts.pickup_windows, item.usable_until)
        if not pickup.feasible or not self._keeps_until(pid, arrival.at, pickup.collect.end):
            return None
        cold = self._needs_cold_storage(pid)
        # Storage over time: the produce sits here from arrival until pickup ends.
        free_lb = min(
            s.cold_free_lb if cold else s.dry_free_lb
            for s in (self.calculators.storage_at(facts.storage, t) for t in (arrival.at, pickup.collect.end))
        )
        in_class = sum(a.pounds for a in draft.allocations_to(me) if self._needs_cold_storage(a.produce_id) == cold)
        room = self.calculators.capacity_fit(free_lb, in_class).room_left_lb
        limit = room
        if uses_truck:
            limit = min(limit, self.calculators.capacity_fit(facts.truck.capacity_lb, draft.planned_lb(me)).room_left_lb)
        return _Receivable(arrival, pickup, cold, uses_truck, room, limit)

    def counter_problems(self, agent_input: AgentInput, amended: DraftVersion) -> list[str]:
        """Why a counter (from anyone speaking for us, such as our LLM negotiator) asks for more
        than our own facts allow. It reuses the limits our bids respect (``_receivable``) and our
        truck check; it never limits what we give back. Empty: the counter fits our facts."""
        draft, facts = agent_input.draft, agent_input.facts
        me = self.organization_id
        problems = []
        for item in draft.items:
            more = amended.pounds(item.produce_id, me) - draft.pounds(item.produce_id, me)
            if more <= POUNDS_TOLERANCE:
                continue
            name = self._item_name(item.produce_id).lower()
            can = self._receivable(draft, facts, item)
            if can is None or can.limit_lb <= 0:
                problems.append(f"our facts don't let us receive and hand out more {name} under version {draft.version} "
                                "(storage, pickup hours before it spoils, transport, or its condition)")
            elif more > can.limit_lb + POUNDS_TOLERANCE:
                problems.append(f"we can receive at most {_lb(can.limit_lb)} lb more {name} (our storage at arrival and until "
                                f"pickup ends{', and our truck' if can.uses_truck else ''}), not {_lb(more)} lb")
        tr = amended.transport(me)
        if tr is not None and tr != draft.transport(me) and tr.mover is Mover.FOOD_BANK and amended.allocations_to(me):
            why = self._cannot_collect(amended, facts, tr)
            if why is None and amended.planned_lb(me) > facts.truck.capacity_lb + POUNDS_TOLERANCE:
                why = f"our truck holds {_lb(facts.truck.capacity_lb)} lb"
            if why is not None:
                problems.append(f"our truck can't do that collection: {why}")
        problems.extend(self._contest_problems(draft, facts, amended))
        return problems

    def _contest_problems(self, draft: DraftVersion, facts: FoodBankFacts, amended: DraftVersion) -> list[str]:
        """Why a counter changes another food bank's share in a way we may not (ADR 0001, 0013).
        We may give our own pounds away; we may take another food bank's pounds of an item only
        to our own share, only while our households are below fair share, no further than our
        gap, and only when nothing unclaimed is produce we can receive."""
        me = self.organization_id
        problems, contested = [], False
        for fb in dict.fromkeys([*draft.named_food_banks(), *amended.named_food_banks()]):
            if fb == me:
                continue
            if amended.transport(fb) != draft.transport(fb):
                problems.append(f"you can't set {draft.name_of(fb)}'s transport; only it can")
            for item in draft.items:
                pid = item.produce_id
                change = amended.pounds(pid, fb) - draft.pounds(pid, fb)
                ours = amended.pounds(pid, me) - draft.pounds(pid, me)
                if change < -POUNDS_TOLERANCE:
                    if ours > POUNDS_TOLERANCE:
                        contested = True
                    else:
                        problems.append(f"you can take {draft.name_of(fb)}'s {self._item_name(pid).lower()} only to your own "
                                        "share, as a contest; you can't set or move another food bank's pounds elsewhere")
                elif change > POUNDS_TOLERANCE and ours >= -POUNDS_TOLERANCE:
                    problems.append(f"you can't add pounds to {draft.name_of(fb)}'s share except by giving it your own")
        if not contested:
            return problems
        before = self.calculators.gap_after_plan(facts.demand.below_fair_share_lb, draft.planned_lb(me))
        after = self.calculators.gap_after_plan(facts.demand.below_fair_share_lb, amended.planned_lb(me))
        if before.remaining_gap_lb <= 0:
            problems.append(f"your households already have their fair share under version {draft.version}, so you can't contest "
                            "another food bank's share; beyond fair share, ask only for unclaimed pounds")
        elif after.above_gap_lb > POUNDS_TOLERANCE:
            problems.append(f"a contest goes no further than your households' fair-share gap: contest at most "
                            f"{_lb(before.remaining_gap_lb)} lb")
        for item in draft.items:
            can = self._receivable(draft, facts, item) if draft.unallocated_lb(item.produce_id) > POUNDS_TOLERANCE else None
            if can is not None and can.limit_lb > 0:
                problems.append(f"{_lb(draft.unallocated_lb(item.produce_id))} lb of {self._item_name(item.produce_id).lower()} "
                                "is unclaimed and you can receive it: ask for unclaimed pounds before contesting another food bank's share")
        return problems

    # Contests (ADR 0013)

    def _losses(self, draft: DraftVersion, before: DraftVersion | None) -> list[_Loss]:
        """Pounds of our share that moved to another food bank's share since our last turn."""
        if before is None:
            return []
        me, out = self.organization_id, []
        for item in draft.items:
            pid = item.produce_id
            then, now = before.pounds(pid, me), draft.pounds(pid, me)
            if now >= then - POUNDS_TOLERANCE:
                continue
            gains = {fb: draft.pounds(pid, fb) - before.pounds(pid, fb) for fb in draft.named_food_banks() if fb != me}
            gainers = sorted((fb for fb, g in gains.items() if g > POUNDS_TOLERANCE), key=lambda fb: (-gains[fb], fb))
            if gainers:
                out.append(_Loss(pid, gainers[0], self.calculators.adjust_pounds(then, -now)))
        return sorted(out, key=lambda l: (draft.item(l.produce_id).usable_until, l.produce_id))

    def _gap_phrase(self, draft: DraftVersion, facts: FoodBankFacts, shortfall: float) -> str:
        planned = draft.planned_lb(self.organization_id)
        return (f"Our {facts.demand.households} households are {_lb(shortfall)} lb below their fair share this week"
                + (f" after the {_lb(planned)} lb already planned for us" if planned else ""))

    def _claim(self, draft: DraftVersion, item: LotItem, can: _Receivable, source: str, pounds: float, opening: str, ask: str) -> Move:
        label = "cold" if can.cold else "dry"
        reason = (f"{opening} Arriving at {_clock(can.arrival.at)}, we have {_lb(can.room_lb)} lb of {label} space for it, and "
                  f"households can collect it {_window(can.pickup.collect)}, before it spoils. {ask}")
        return self._move(draft, MoveKind.COUNTER, reason, ShiftPounds(item.produce_id, source, self.organization_id, pounds))

    def _take_back(self, draft: DraftVersion, facts: FoodBankFacts, losses: Sequence[_Loss], shortfall: float) -> Move | None:
        """Take back pounds a contest took from our share, within our fair-share gap."""
        for loss in losses:
            item, other = draft.item(loss.produce_id), draft.name_of(loss.to_food_bank_id)
            line = draft.pounds(loss.produce_id, loss.to_food_bank_id)
            can = self._receivable(draft, facts, item)
            if can is None or line <= 0:
                continue
            back = min(shortfall, loss.lost_lb, line, can.limit_lb)
            if back <= 0:
                continue
            name = self._item_name(item.produce_id).lower()
            opening = (f"Since our last turn, {_lb(loss.lost_lb)} lb of our {name} moved to {other}'s share. "
                       f"{self._gap_phrase(draft, facts, shortfall)}, so those pounds are within our households' fair-share gap.")
            return self._claim(draft, item, can, loss.to_food_bank_id, back, opening,
                               f"We take back {_lb(back)} lb of {name} from {other}, within our fair-share gap.")
        return None

    def _contest(self, draft: DraftVersion, facts: FoodBankFacts, shortfall: float) -> Move | None:
        """Contest another food bank's share: nothing unclaimed is produce we can receive (our
        bids came first), so take pounds of the shortest-lived item we can receive from the
        largest other line of it, up to our gap."""
        me = self.organization_id
        for item in sorted(draft.items, key=lambda i: (i.usable_until, i.produce_id)):
            lines = sorted((a for a in draft.allocations if a.produce_id == item.produce_id and a.food_bank_id != me and a.pounds > 0),
                           key=lambda a: (-a.pounds, a.food_bank_id))
            if not lines:
                continue
            can = self._receivable(draft, facts, item)
            if can is None or can.limit_lb <= 0:
                continue
            a, name, other = lines[0], self._item_name(item.produce_id).lower(), draft.name_of(lines[0].food_bank_id)
            amount = min(shortfall, can.limit_lb, a.pounds)
            opening = (f"{self._gap_phrase(draft, facts, shortfall)}, and nothing unclaimed in version {draft.version} is produce "
                       f"we can receive and hand out in time. {other} has {_lb(a.pounds)} lb of {name} in this version.")
            return self._claim(draft, item, can, a.food_bank_id, amount, opening,
                               f"We contest {_lb(amount)} lb of it for our households, within our fair-share gap; "
                               f"{other} answers for its own share.")
        return None

    def _concession(self, draft: DraftVersion, facts: FoodBankFacts, losses: Sequence[_Loss]) -> str:
        """What we say about pounds a contest took and we don't take back (empty if none)."""
        if not losses:
            return ""
        gap = self.calculators.gap_after_plan(facts.demand.below_fair_share_lb, draft.planned_lb(self.organization_id))
        moved = "; ".join(f"{_lb(l.lost_lb)} lb of our {self._item_name(l.produce_id).lower()} moved to "
                          f"{draft.name_of(l.to_food_bank_id)}'s share" for l in losses)
        if gap.remaining_gap_lb <= 0:
            return (f"Since our last turn, {moved}. Our households still have their fair share in what is planned for us, so "
                    "those pounds were beyond fair share and we concede them. ")
        return (f"Since our last turn, {moved}. Our households are {_lb(gap.remaining_gap_lb)} lb below their fair share, but "
                "our storage, pickup hours and transport don't let us take those pounds back. ")

    def _bid_for(self, draft: DraftVersion, facts: FoodBankFacts, item: LotItem, shortfall: float | None) -> Move | None:
        """A bid for one unclaimed item: toward our gap (``shortfall``), or beyond fair share
        (``shortfall`` is None). The same facts bound both; only the gap differs."""
        me, pid = self.organization_id, item.produce_id
        can = self._receivable(draft, facts, item)
        if can is None:
            return None
        arrival, pickup, cold, uses_truck, room = can.arrival, can.pickup, can.cold, can.uses_truck, can.room_lb
        if shortfall is None and not uses_truck and draft.lot_id in self._drop_off_refused_at:
            return None  # the donor turned our drop-off down at a load we can't see past
        limits = [draft.unallocated_lb(pid), can.limit_lb] + ([shortfall] if shortfall is not None else [])
        bid = min(limits)
        if bid <= 0:
            return None
        pounds = self.calculators.adjust_pounds(draft.pounds(pid, me), bid)
        name = self._item_name(pid).lower()
        label = "cold" if cold else "dry"
        space = f"Arriving at {_clock(arrival.at)}, we have {_lb(room)} lb of {label} space for it"
        if shortfall is not None:
            reason = (
                f"Our {facts.demand.households} households are {_lb(shortfall)} lb below their fair share this week"
                + (f" after the {_lb(draft.planned_lb(me))} lb already planned for us" if draft.planned_lb(me) else "")
                + f". {_lb(draft.unallocated_lb(pid))} lb of {name} is unclaimed. {space}, and households can collect it "
                f"{_window(pickup.collect)}, before it spoils. Asking for {_lb(bid)} lb."
            )
        else:
            met = (f"Our {facts.demand.households} households already have their fair share this week"
                   if facts.demand.below_fair_share_lb <= 0 else
                   f"Our {facts.demand.households} households' {_lb(facts.demand.below_fair_share_lb)} lb fair-share gap "
                   f"is already planned in the {_lb(draft.planned_lb(me))} lb for us")
            reason = (
                f"{met}. {_lb(draft.unallocated_lb(pid))} lb of {name} is still unclaimed, so rather than let it go to "
                f"waste we ask for some beyond fair share. {space} from arrival until pickup ends, households can collect "
                f"it {_window(pickup.collect)}, and its produce profile keeps it usable in {label} storage until then. "
                f"Asking for {_lb(bid)} lb more, beyond fair share."
            )
        return self._move(draft, MoveKind.COUNTER, reason, SetPounds(pid, me, pounds))

    def _bid_arrival(self, draft: DraftVersion, facts: FoodBankFacts, produce_ids: Sequence[str]) -> _Arrival | None:
        tr = draft.transport(self.organization_id)
        if tr is not None:
            if tr.mover is Mover.DONOR and not self._drop_off_suits(draft, produce_ids):
                return None
            if tr.mover is Mover.FOOD_BANK and self._collection(draft, facts, produce_ids, 0)[0] is None:
                return None
            return _Arrival(tr.arrives_at, tr)
        if self._drop_off_suits(draft, produce_ids) and facts.travel_minutes_from_donor is not None:
            return _Arrival(self.calculators.arrival_time(draft.deadline, facts.travel_minutes_from_donor), None)
        times, _ = self._collection(draft, facts, produce_ids, draft.planned_lb(self.organization_id))
        return None if times is None else _Arrival(times[1], None)

    # Cooler failure (Workflow 4): each food bank answers for itself; the failed one chooses

    def answer_cold_space_request(self, facts: FoodBankFacts, committed: DraftVersion, at: datetime) -> ColdSpaceAnswer:
        """Our own answer when another food bank's cooler fails and it asks who has cold space:
        cold space free at ``at`` by our storage records, less the cold-dependent pounds already
        committed to us, and our pickup hours. Only our own facts and the shared draft."""
        if facts.food_bank_id != self.organization_id:
            raise TurnError(f"{self.organization_id} can only answer from its own specialists' facts")
        free = self.calculators.storage_at(facts.storage, at).cold_free_lb
        held_cold = sum(a.pounds for a in committed.allocations_to(self.organization_id) if self._needs_cold_storage(a.produce_id))
        room = self.calculators.capacity_fit(free, held_cold).room_left_lb
        return ColdSpaceAnswer(self.organization_id, facts.name, room,
                               tuple(PickupWindow(w.start, w.end) for w in facts.pickup_windows))

    def cooler_failure(self, facts: FoodBankFacts, committed: DraftVersion, at: datetime) -> CoolerFailure | None:
        """What our failed cooler puts at risk, from our own facts: our committed items, when our
        households planned to collect them, and our truck. None when we have no pickup hours
        recorded, so there is no households' pickup time to plan a move around."""
        me, mine, tr = self.organization_id, committed.allocations_to(self.organization_id), committed.transport(self.organization_id)
        collect = [c.collect for a in mine
                   if (c := self.calculators.pickup_feasibility(tr.arrives_at, facts.pickup_windows,
                                                                committed.item(a.produce_id).usable_until)).collect]
        window = min(collect, key=lambda w: w.start) if collect else (facts.pickup_windows[0] if facts.pickup_windows else None)
        if window is None:
            return None
        truck = None
        if facts.truck is not None and facts.truck.window.end > at:
            truck = CoolerTruck(refrigerated=facts.truck.refrigerated, available_from=max(at, facts.truck.window.start))
        return CoolerFailure(
            food_bank_id=me, food_bank_name=facts.name, lot_id=committed.lot_id, current_version=committed.version,
            detected_at=at, items=tuple(HeldItem(a.produce_id, a.pounds) for a in mine),
            households_pickup=PickupWindow(window.start, window.end),
            own_pickup_windows=tuple(PickupWindow(w.start, w.end) for w in facts.pickup_windows), truck=truck,
        )

    def choose_cooler_receiver(self, failure: CoolerFailure, answers: Sequence[ColdSpaceAnswer],
                               travel_minutes: Mapping[str, float]) -> CoolerFailureDecision:
        """As the food bank whose cooler failed: weigh every other food bank's own answer with our
        recorded travel minutes to it, and choose, with a reason card for each (#15). A food bank
        we have no recorded route to counts as not answering, since we can't plan a run there."""
        candidates = [Candidate(food_bank_id=a.food_bank_id, name=a.name,
                                response="answered" if travel_minutes.get(a.food_bank_id) is not None else "no_answer",
                                cold_space_lb=a.cold_space_lb, pickup_windows=a.pickup_windows,
                                travel_minutes=travel_minutes.get(a.food_bank_id))
                      for a in answers]
        return assess_cooler_failure(failure, candidates, profiles=self.profiles)

    # Accepting, holding, passing

    def _accept_reason(self, draft: DraftVersion, facts: FoodBankFacts) -> str:
        me = self.organization_id
        tr = draft.transport(me)
        free = self.calculators.storage_at(facts.storage, tr.arrives_at)
        parts = [f"Version {draft.version} fits our facts."]
        for cold, free_lb, label in ((True, free.cold_free_lb, "cold"), (False, free.dry_free_lb, "dry")):
            needed = sum(a.pounds for a in draft.allocations_to(me) if self._needs_cold_storage(a.produce_id) == cold)
            if needed:
                parts.append(f"Storage: {_lb(needed)} lb {label} needed, {_lb(free_lb)} lb free at {_clock(tr.arrives_at)}.")
        for a in draft.allocations_to(me):
            check = self.calculators.pickup_feasibility(tr.arrives_at, facts.pickup_windows, draft.item(a.produce_id).usable_until)
            parts.append(f"Households can collect {_lb(a.pounds)} lb {self._item_name(a.produce_id).lower()} {_window(check.collect)}.")
        if tr.mover is Mover.FOOD_BANK:
            kind = "refrigerated truck" if facts.truck.refrigerated else "truck"
            parts.append(f"Our {kind} collects {_lb(draft.planned_lb(me))} lb of its {_lb(facts.truck.capacity_lb)} lb, "
                         f"{_clock(tr.departs_at)} to {_clock(tr.arrives_at)}.")
        else:
            parts.append(f"{draft.name_of(draft.donor_id)} drops it off at {_clock(tr.arrives_at)}.")
        return " ".join(parts)

    def _holds(self, draft: DraftVersion, facts: FoodBankFacts, concede: str = "") -> Move:
        me, tr = self.organization_id, draft.transport(self.organization_id)
        ends = [
            self.calculators.pickup_feasibility(tr.arrives_at, facts.pickup_windows, draft.item(a.produce_id).usable_until).collect.end
            for a in draft.allocations_to(me)
        ]
        holds = []
        for cold, resource in ((True, STORAGE_COLD), (False, STORAGE_DRY)):
            lb = sum(a.pounds for a in draft.allocations_to(me) if self._needs_cold_storage(a.produce_id) == cold)
            if lb:
                holds.append(HoldRequest(resource, me, lb, tr.arrives_at, max(ends)))
        if tr.mover is Mover.FOOD_BANK:
            holds.append(HoldRequest("truck", me, draft.planned_lb(me), tr.departs_at, tr.arrives_at))
        what = "; ".join(f"{h.resource.replace('_', ' ')} {_lb(h.pounds)} lb, {_clock(h.start)} to {_clock(h.end)}" for h in holds)
        return self._move(draft, MoveKind.REQUEST_HOLD,
                          f"{concede}Everyone named has accepted version {draft.version}. Holding our own resources ({what}), "
                          "pending our manager's approval.", holds=holds)

    def _pass_reason(self, draft: DraftVersion, facts: FoodBankFacts) -> str:
        if facts.demand.below_fair_share_lb <= 0:
            return (f"Our {facts.demand.households} households already have their fair share this week, and nothing "
                    f"unclaimed in version {draft.version} fits our storage, pickup hours, and transport beyond it, so we "
                    "ask for nothing.")
        return (f"Nothing unclaimed in version {draft.version} fits our storage, pickup hours, and transport, "
                "so we ask for nothing.")


# --- Advocate -----------------------------------------------------------------------------


class RulesAdvocate(_Negotiator):
    """Proposes one amendment toward the food bank with the largest fair-share gap after
    this version, or passes. It has no accept, reject, or hold path at all, and ``Move``
    refuses one anyway.

    Decision order (proposed): the target is the largest remaining gap (ties: low-access
    area first, then more households, then id). Offer it unclaimed pounds, shortest-lived
    item first, skipping items it already declined. If nothing is unclaimed, shift pounds
    from the food bank furthest above its own gap. Otherwise, in a contest recorded in the
    shared records (``AdvocateFacts.contests``, ADR 0013), back whichever of the two food
    banks is further below fair share: shift the contested item from the other one to it, up
    to its remaining gap (several contests: the largest such gap first). Otherwise pass."""

    role = Role.ADVOCATE

    def __init__(self, organization_id: str = "advocate", calculators: Calculators | None = None):
        super().__init__(organization_id, calculators)

    def move(self, agent_input: AgentInput) -> Move:
        self._check_turn(agent_input, AdvocateFacts, None)
        draft, facts = agent_input.draft, agent_input.facts
        plans = {g.food_bank_id: self.calculators.gap_after_plan(g.below_fair_share_lb, draft.planned_lb(g.food_bank_id)) for g in facts.gaps}
        target = max(facts.gaps, key=lambda g: (plans[g.food_bank_id].remaining_gap_lb, g.low_access, g.households, g.food_bank_id))
        remaining = plans[target.food_bank_id].remaining_gap_lb
        if remaining <= 0:
            return self._pass(draft, "no food bank's households remain below fair share")

        declined = set(facts.declined)
        unclaimed = [
            i for i in draft.items
            if draft.unallocated_lb(i.produce_id) > 0 and (target.food_bank_id, i.produce_id) not in declined
            and i.condition_grade != "not_for_people" and not i.condition_doubt
        ]
        if unclaimed:
            item = min(unclaimed, key=lambda i: (i.usable_until, i.produce_id))
            amount = min(draft.unallocated_lb(item.produce_id), remaining)
            reason = (self._gap_sentence(draft, facts, target, plans)
                      + f" {_lb(draft.unallocated_lb(item.produce_id))} lb of {self._item_name(item.produce_id).lower()} is unclaimed. "
                      f"Proposing {_lb(amount)} lb of it for {target.name}.")
            return self._move(draft, MoveKind.COUNTER, reason,
                              SetPounds(item.produce_id, target.food_bank_id, draft.pounds(item.produce_id, target.food_bank_id) + amount))

        sources = [g for g in facts.gaps if g.food_bank_id != target.food_bank_id and plans[g.food_bank_id].above_gap_lb > 0]
        for source in sorted(sources, key=lambda g: (-plans[g.food_bank_id].above_gap_lb, g.food_bank_id)):
            lines = [a for a in draft.allocations_to(source.food_bank_id) if (target.food_bank_id, a.produce_id) not in declined]
            if not lines:
                continue
            line = max(lines, key=lambda a: (a.pounds, a.produce_id))
            above = plans[source.food_bank_id].above_gap_lb
            amount = min(remaining, above, line.pounds)
            reason = (self._gap_sentence(draft, facts, target, plans)
                      + f" {source.name} is planned {_lb(above)} lb above its households' fair-share gap. "
                      f"Proposing {_lb(amount)} lb of its {self._item_name(line.produce_id).lower()} move to {target.name}.")
            return self._move(draft, MoveKind.COUNTER, reason,
                              ShiftPounds(line.produce_id, source.food_bank_id, target.food_bank_id, amount))

        backing = self._back_a_side(draft, facts, plans)
        if backing is not None:
            return backing
        return self._pass(draft, f"{target.name} is still {_lb(remaining)} lb below fair share, but nothing is unclaimed "
                                 "and no food bank is planned above its own gap")

    def _sides(self, facts: AdvocateFacts, plans, a: str, b: str) -> tuple[FoodBankGap, FoodBankGap] | None:
        """(backed, other) of a contest between ``a`` and ``b``: the one further below fair share
        is backed (ties: low-access area, more households, id). None if either has no gap."""
        gaps = {g.food_bank_id: g for g in facts.gaps}
        if a not in gaps or b not in gaps:
            return None
        backed, other = sorted((gaps[a], gaps[b]), key=lambda g: (plans[g.food_bank_id].remaining_gap_lb, g.low_access,
                                                                   g.households, g.food_bank_id), reverse=True)
        return backed, other

    def _back_a_side(self, draft: DraftVersion, facts: AdvocateFacts, plans) -> Move | None:
        """In a contest (ADR 0013), back whichever of the two food banks is further below fair
        share: propose pounds of the contested item from the other one's share to it, up to its
        remaining gap. The advocate has no vote; each food bank still answers for itself."""
        declined = set(facts.declined)
        options = []
        for a, b, pid in dict.fromkeys(facts.contests):
            sides = self._sides(facts, plans, a, b)
            if sides is None or pid not in {i.produce_id for i in draft.items}:
                continue
            backed, other = sides
            rem, line = plans[backed.food_bank_id].remaining_gap_lb, draft.pounds(pid, other.food_bank_id)
            if rem <= plans[other.food_bank_id].remaining_gap_lb or line <= 0 or (backed.food_bank_id, pid) in declined:
                continue
            options.append((rem, backed, other, pid, line))
        if not options:
            return None
        rem, backed, other, pid, line = max(options, key=lambda o: (o[0], o[1].low_access, o[1].households, o[1].food_bank_id, o[3]))
        amount = min(rem, line)
        name = self._item_name(pid).lower()
        reason = (f"{backed.name} and {other.name} contest the {name}. {backed.name}'s {backed.households} households are "
                  f"{_lb(rem)} lb below fair share under version {draft.version}, and {other.name}'s {other.households} are "
                  f"{_lb(plans[other.food_bank_id].remaining_gap_lb)} lb below, so we back {backed.name}: proposing {_lb(amount)} lb "
                  f"of {other.name}'s {name} move to it."
                  + (" It is in a low-access area (USDA Food Access Research Atlas)." if backed.low_access else "")
                  + f" We have no vote; {other.name} answers for its own share.")
        return self._move(draft, MoveKind.COUNTER, reason, ShiftPounds(pid, other.food_bank_id, backed.food_bank_id, amount))

    def counter_problems(self, agent_input: AgentInput, amended: DraftVersion) -> list[str]:
        """Why a counter from the advocate (such as its LLM negotiator's) isn't one this advocate
        may propose: pounds go only toward a food bank still below fair share under this version,
        no further than its gap, never on an item it already declined or one not fit to hand out,
        and pounds are taken only from above another food bank's gap. Beyond fair share is each
        food bank's own bid. The same gap calculator as ``move``; empty means it fits."""
        draft, facts = agent_input.draft, agent_input.facts
        gaps = {g.food_bank_id: g for g in facts.gaps}
        declined = set(facts.declined)
        problems = []
        if amended.transports != draft.transports:
            problems.append("the advocate proposes pounds, not transport terms")
        banks = list(dict.fromkeys([*draft.named_food_banks(), *amended.named_food_banks()]))
        for fb in banks:
            before, after = draft.planned_lb(fb), amended.planned_lb(fb)
            g = gaps.get(fb)
            if g is None:
                if abs(after - before) > POUNDS_TOLERANCE:
                    problems.append(f"{fb} has no fair-share gap in your facts, so you can't move pounds for it")
                continue
            plan_before = self.calculators.gap_after_plan(g.below_fair_share_lb, before)
            plan_after = self.calculators.gap_after_plan(g.below_fair_share_lb, after)
            gained = [i for i in draft.items if amended.pounds(i.produce_id, fb) - draft.pounds(i.produce_id, fb) > POUNDS_TOLERANCE]
            if gained:
                if plan_before.remaining_gap_lb <= 0:
                    problems.append(f"{g.name}'s households already have their fair share under version {draft.version}; "
                                    "asking for pounds beyond fair share is that food bank's own call")
                elif plan_after.above_gap_lb > POUNDS_TOLERANCE:
                    problems.append(f"that takes {g.name} {_lb(plan_after.above_gap_lb)} lb past its households' fair-share gap; "
                                    f"propose at most {_lb(plan_before.remaining_gap_lb)} lb more")
                for i in gained:
                    if (fb, i.produce_id) in declined:
                        problems.append(f"{g.name} already declined {self._item_name(i.produce_id).lower()}")
                    if i.condition_grade == "not_for_people" or i.condition_doubt:
                        problems.append(f"{self._item_name(i.produce_id).lower()} is not fit to hand out, or a human must check it first")
            if after < before - POUNDS_TOLERANCE and plan_after.remaining_gap_lb > plan_before.remaining_gap_lb + POUNDS_TOLERANCE \
                    and not self._backs_a_contest(draft, facts, amended, fb, plan_before.remaining_gap_lb):
                problems.append(f"that takes pounds {g.name}'s households need for their fair share; shift only pounds "
                                "planned above its gap, or, in a contest, back the food bank further below fair share")
        return problems

    def _backs_a_contest(self, draft: DraftVersion, facts: AdvocateFacts, amended: DraftVersion, fb: str, fb_remaining: float) -> bool:
        """Whether every pound taken from ``fb`` goes, on a contested item, to the food bank it
        contests with, which is further below fair share than ``fb`` (ADR 0013)."""
        gaps = {g.food_bank_id: g for g in facts.gaps}
        for item in draft.items:
            pid = item.produce_id
            if amended.pounds(pid, fb) >= draft.pounds(pid, fb) - POUNDS_TOLERANCE:
                continue
            gainers = [o for o in gaps if o != fb and amended.pounds(pid, o) > draft.pounds(pid, o) + POUNDS_TOLERANCE]
            ok = [o for o in gainers if ((o, fb, pid) in facts.contests or (fb, o, pid) in facts.contests)
                  and self.calculators.gap_after_plan(gaps[o].below_fair_share_lb, draft.planned_lb(o)).remaining_gap_lb > fb_remaining]
            if not gainers or len(ok) != len(gainers):
                return False
        return True

    def _gap_sentence(self, draft: DraftVersion, facts: AdvocateFacts, target: FoodBankGap, plans) -> str:
        others = ", ".join(
            f"{g.name} {_lb(plans[g.food_bank_id].remaining_gap_lb)} lb" for g in facts.gaps if g.food_bank_id != target.food_bank_id
        )
        access = " It is in a low-access area (USDA Food Access Research Atlas)." if target.low_access else ""
        return (f"{target.name}'s {target.households} households are {_lb(plans[target.food_bank_id].remaining_gap_lb)} lb "
                f"below fair share under version {draft.version}, the largest gap (others: {others}).{access}")

    def _pass(self, draft: DraftVersion, why: str) -> Move:
        unclaimed = _unclaimed_sentence(draft, self._item_name)
        return self._move(draft, MoveKind.PASS, f"No change proposed to version {draft.version}: {why}. {unclaimed}")


def rules_negotiator(role: Role | str, organization_id: str, calculators: Calculators | None = None) -> _Negotiator:
    role = Role(role)
    if role is Role.DONOR:
        return RulesDonor(organization_id, calculators)
    if role is Role.FOOD_BANK:
        return RulesFoodBank(organization_id, calculators)
    return RulesAdvocate(organization_id, calculators)


# --- Wording (formats facts; never adds new ones) -----------------------------------------


def _unclaimed_sentence(draft: DraftVersion, item_name) -> str:
    left = [f"{_lb(draft.unallocated_lb(i.produce_id))} lb {item_name(i.produce_id).lower()}" for i in draft.items
            if draft.unallocated_lb(i.produce_id) > 0]
    return ("Unclaimed so far: " + ", ".join(left) + ".") if left else "Every pound has a destination."


def _pickup_problem_text(check, arrives_at: datetime, usable_until: datetime, facts: FoodBankFacts) -> str:
    if check.problem == "no_pickup_hours":
        return "we have no pickup hours recorded"
    if check.problem == "arrives_after_pickup_ends":
        return f"it arrives at {_clock(arrives_at)}, after pickup ends at {_clock(check.last_pickup_end)}"
    opens = min((w.start for w in facts.pickup_windows if w.end > arrives_at), default=None)
    opens_text = f"pickup opens at {_clock(opens)}" if opens else "no pickup opens after it arrives"
    return f"{opens_text}, and it is usable only until {_clock(usable_until)}"
