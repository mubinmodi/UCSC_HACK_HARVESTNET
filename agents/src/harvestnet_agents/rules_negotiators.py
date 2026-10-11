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
  amendment plus a reason, bids toward its households' fair-share gap only for produce
  it can receive, rejects produce not fit for people, and asks its human about any
  condition doubt.
- **Advocate**: never accepts, rejects, holds, or vetoes. It proposes one amendment
  toward the food bank with the largest fair-share gap, or passes.

Each organization requests holds on its own resources once every organization named in
the version has accepted it. Nothing here commits anything: commitment needs every
named organization's human to approve the same version, elsewhere.

The decision order and tie-breaks are **proposed** and listed in each class.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .calculators import Calculators, StandInCalculators
from .negotiation import (
    AdvocateFacts,
    AgentInput,
    Amendment,
    DonorFacts,
    DraftVersion,
    FoodBankFacts,
    FoodBankGap,
    HoldRequest,
    LotItem,
    Move,
    MoveKind,
    Mover,
    Role,
    SetPounds,
    SetTransport,
    ShiftPounds,
    Transport,
)
from .profiles import ProduceProfile, ProfileSet

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


class RulesFoodBank(_Negotiator):
    """Decision order (proposed): per allocated item, not fit for people -> reject; no
    profile or condition doubt -> ask a human. Then transport: no line -> ask the donor to
    drop off if offered and suitable, else collect with its own truck, else remove the item;
    a collection its truck can't do -> switch to the donor's drop-off if suitable, else
    reduce or remove. Then households can't collect before it spoils -> remove that item;
    storage at arrival is short -> reduce the longest-lived item in that storage. With no
    problem: bid toward its fair-share gap on the shortest-lived item it can receive; else
    request holds if everyone named accepted, accept if named, or pass."""

    role = Role.FOOD_BANK

    def move(self, agent_input: AgentInput) -> Move:
        facts = agent_input.facts
        self._check_turn(agent_input, FoodBankFacts, getattr(facts, "food_bank_id", None))
        draft = agent_input.draft
        problems = self.review(agent_input)
        if problems:
            p = problems[0]
            return self._move(draft, p.kind, p.text, p.amendment)
        bid = self._bid(draft, facts)
        if bid is not None:
            return bid
        me = self.organization_id
        if me not in draft.named_food_banks():
            return self._move(draft, MoveKind.PASS, self._pass_reason(draft, facts))
        if set(draft.named_organizations()) <= set(agent_input.turn.accepted_by):
            return self._holds(draft, facts)
        return self._move(draft, MoveKind.ACCEPT, self._accept_reason(draft, facts))

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

    def _truck_problem(self, draft: DraftVersion, facts: FoodBankFacts, tr: Transport) -> Problem | None:
        me, mine = self.organization_id, draft.allocations_to(self.organization_id)
        ids = [a.produce_id for a in mine]
        truck = facts.truck
        why = None
        if truck is None:
            why = "we have no truck free today"
        elif any(self._cold_chain(p) for p in ids) and not truck.refrigerated:
            why = "our truck isn't refrigerated"
        elif not (truck.window.contains(tr.departs_at) and truck.window.contains(tr.arrives_at)):
            why = f"our truck is only free {_clock(truck.window.start)} to {_clock(truck.window.end)}"
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
        me = self.organization_id
        demand = facts.demand
        gap = self.calculators.gap_after_plan(demand.below_fair_share_lb, draft.planned_lb(me))
        if gap.remaining_gap_lb <= 0:
            return None
        candidates = [i for i in draft.items if draft.unallocated_lb(i.produce_id) > 0]
        for item in sorted(candidates, key=lambda i: (i.usable_until, i.produce_id)):
            bid = self._bid_for(draft, facts, item, gap.remaining_gap_lb)
            if bid is not None:
                return bid
        return None

    def _bid_for(self, draft: DraftVersion, facts: FoodBankFacts, item: LotItem, shortfall: float) -> Move | None:
        me, pid = self.organization_id, item.produce_id
        if item.condition_grade == "not_for_people" or item.condition_doubt or self._profile(pid) is None:
            return None
        ids = [a.produce_id for a in draft.allocations_to(me)] + [pid]
        arrival = self._bid_arrival(draft, facts, ids)
        if arrival is None:
            return None
        pickup = self.calculators.pickup_feasibility(arrival.at, facts.pickup_windows, item.usable_until)
        if not pickup.feasible:
            return None
        cold = self._needs_cold_storage(pid)
        free = self.calculators.storage_at(facts.storage, arrival.at)
        free_lb = free.cold_free_lb if cold else free.dry_free_lb
        in_class = sum(a.pounds for a in draft.allocations_to(me) if self._needs_cold_storage(a.produce_id) == cold)
        room = self.calculators.capacity_fit(free_lb, in_class).room_left_lb
        limits = [draft.unallocated_lb(pid), room, shortfall]
        collecting = arrival.transport is not None and arrival.transport.mover is Mover.FOOD_BANK
        if collecting or (arrival.transport is None and not self._drop_off_suits(draft, ids)):
            limits.append(self.calculators.capacity_fit(facts.truck.capacity_lb, draft.planned_lb(me)).room_left_lb)
        bid = min(limits)
        if bid <= 0:
            return None
        name = self._item_name(pid).lower()
        label = "cold" if cold else "dry"
        reason = (
            f"Our {facts.demand.households} households are {_lb(shortfall)} lb below their fair share this week"
            + (f" after the {_lb(draft.planned_lb(me))} lb already planned for us" if draft.planned_lb(me) else "")
            + f". {_lb(draft.unallocated_lb(pid))} lb of {name} is unclaimed. Arriving at {_clock(arrival.at)}, we have "
            f"{_lb(room)} lb of {label} space for it, and households can collect it {_window(pickup.collect)}, before it "
            f"spoils. Asking for {_lb(bid)} lb."
        )
        return self._move(draft, MoveKind.COUNTER, reason, SetPounds(pid, me, draft.pounds(pid, me) + bid))

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

    def _holds(self, draft: DraftVersion, facts: FoodBankFacts) -> Move:
        me, tr = self.organization_id, draft.transport(self.organization_id)
        ends = [
            self.calculators.pickup_feasibility(tr.arrives_at, facts.pickup_windows, draft.item(a.produce_id).usable_until).collect.end
            for a in draft.allocations_to(me)
        ]
        holds = []
        for cold, resource in ((True, "storage_cold"), (False, "storage_dry")):
            lb = sum(a.pounds for a in draft.allocations_to(me) if self._needs_cold_storage(a.produce_id) == cold)
            if lb:
                holds.append(HoldRequest(resource, me, lb, tr.arrives_at, max(ends)))
        if tr.mover is Mover.FOOD_BANK:
            holds.append(HoldRequest("truck", me, draft.planned_lb(me), tr.departs_at, tr.arrives_at))
        what = "; ".join(f"{h.resource.replace('_', ' ')} {_lb(h.pounds)} lb, {_clock(h.start)} to {_clock(h.end)}" for h in holds)
        return self._move(draft, MoveKind.REQUEST_HOLD,
                          f"Everyone named has accepted version {draft.version}. Holding our own resources ({what}), "
                          "pending our manager's approval.", holds=holds)

    def _pass_reason(self, draft: DraftVersion, facts: FoodBankFacts) -> str:
        if facts.demand.below_fair_share_lb <= 0:
            return f"Our {facts.demand.households} households already have their fair share this week, so we ask for nothing in version {draft.version}."
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
    from the food bank furthest above its own gap. Otherwise pass."""

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

        return self._pass(draft, f"{target.name} is still {_lb(remaining)} lb below fair share, but nothing is unclaimed "
                                 "and no food bank is planned above its own gap")

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


def _clock(t: datetime) -> str:
    hour = t.hour % 12 or 12
    suffix = "am" if t.hour < 12 else "pm"
    return f"{hour} {suffix}" if t.minute == 0 else f"{hour}:{t.minute:02d} {suffix}"


def _window(w) -> str:
    if w.start.date() != w.end.date():
        return f"{_clock(w.start)} to {_clock(w.end)} the next day"
    return f"{_clock(w.start)} to {_clock(w.end)}"


def _lb(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def _join(words: Sequence[str]) -> str:
    words = list(dict.fromkeys(words))
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]
