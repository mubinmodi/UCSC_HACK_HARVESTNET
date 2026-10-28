"""Cooler-failure decision logic for a food bank's agent (ticket #15, Workflow 4).

When a food bank's walk-in cooler fails, its agent:

1. decides which held items must move, from each item's produce profile
   (``ProduceProfile.needs_cold``), never from crop names (ADR 0003). An item with no
   profile is not assumed either way; it goes to a human;
2. assesses every candidate food bank from a recorded candidate list (Directory results
   plus each candidate's answer: free cold space, pickup windows, travel time);
3. writes a reason card for every candidate, chosen or not, built only from those
   recorded facts and the profiles;
4. proposes a new draft version naming one receiving food bank. The proposal is a
   draft awaiting that food bank's own decision and fresh approvals. Nothing is
   committed here (ADR 0001, ADR 0004);
5. if no candidate fits, or the chosen one has room for only part, proposes a same-day
   offer to its own households or an unclaimed outcome, each with a reason.

All times and travel minutes are inputs from calculators or recorded data. The only
arithmetic is arrival time = truck departure + recorded travel minutes, and summing
pounds (ADR 0002).

Every shape here is **proposed**, pending ticket #1 (contract day). It's kept to plain
frozen dataclasses with a JSON loader (``parse_scenario``) so it's easy to adapt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Mapping, Sequence

from .profiles import ProduceProfile, ProfileSet, load_profiles
from .serialize import as_datetime as _dt
from .wording import clock as _clock, join as _join, lb as _lb, lb as _num, window as _window

__all__ = [
    "Candidate",
    "ColdSpaceAnswer",
    "CoolerFailure",
    "CoolerFailureDecision",
    "FallbackOutcome",
    "HeldItem",
    "ItemDecision",
    "PickupWindow",
    "ProposedVersion",
    "ReasonCard",
    "Truck",
    "assess_cooler_failure",
    "parse_scenario",
]

Response = Literal["answered", "declined", "no_answer"]
CardOutcome = Literal["chosen", "fits_not_chosen", "rejected"]


# --- Inputs (proposed shapes) ------------------------------------------------------------


@dataclass(frozen=True)
class PickupWindow:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class HeldItem:
    produce_id: str
    pounds: float


@dataclass(frozen=True)
class Truck:
    """The failing food bank's own truck, from its truck specialist."""

    refrigerated: bool
    available_from: datetime


@dataclass(frozen=True)
class CoolerFailure:
    food_bank_id: str
    food_bank_name: str
    lot_id: str
    current_version: int
    detected_at: datetime
    items: tuple[HeldItem, ...]
    households_pickup: PickupWindow  # when the affected households planned to collect
    own_pickup_windows: tuple[PickupWindow, ...]  # the failing food bank's own pickup hours
    truck: Truck | None


@dataclass(frozen=True)
class ColdSpaceAnswer:
    """One food bank's own answer to a request for cold space, built by its own agent from its
    own facts: the cold space it has free for the moved produce, and its pickup hours."""

    food_bank_id: str
    name: str
    cold_space_lb: float
    pickup_windows: tuple[PickupWindow, ...]


@dataclass(frozen=True)
class Candidate:
    """One food bank from the Directory, with its recorded answer."""

    food_bank_id: str
    name: str
    response: Response
    cold_space_lb: float | None = None
    pickup_windows: tuple[PickupWindow, ...] = ()
    travel_minutes: float | None = None
    declined_reason: str | None = None


# --- Outputs (proposed shapes) -----------------------------------------------------------


@dataclass(frozen=True)
class ItemDecision:
    produce_id: str
    pounds: float
    reason: str


@dataclass(frozen=True)
class ReasonCard:
    food_bank_id: str
    name: str
    outcome: CardOutcome
    facts: Mapping[str, Any]
    reasons: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class ProposedVersion:
    """A proposed new draft-agreement version. The receiving food bank decides for itself."""

    lot_id: str
    based_on_version: int
    version: int
    proposer_id: str
    receiving_food_bank_id: str
    receiving_food_bank_name: str
    items: tuple[HeldItem, ...]
    mover: str
    departs_at: datetime
    arrives_at: datetime
    households_collect: PickupWindow
    needs_approval_from: tuple[str, ...]
    reason: str
    status: str = "awaiting_receiver_decision"
    approvals: tuple[str, ...] = ()

    @property
    def committed(self) -> bool:
        # A proposal never commits anyone. Commitment needs every named organization's
        # human to approve this exact version, which happens elsewhere.
        return False


@dataclass(frozen=True)
class FallbackOutcome:
    produce_id: str
    pounds: float
    kind: Literal["same_day_offer", "unclaimed"]
    reason: str


@dataclass(frozen=True)
class CoolerFailureDecision:
    food_bank_id: str
    profile_set_version: str
    items_to_move: tuple[ItemDecision, ...]
    items_staying: tuple[ItemDecision, ...]
    items_unsupported: tuple[ItemDecision, ...]
    reason_cards: tuple[ReasonCard, ...]
    proposal: ProposedVersion | None
    fallback: tuple[FallbackOutcome, ...] = field(default=())


# --- Decision ----------------------------------------------------------------------------


def assess_cooler_failure(
    failure: CoolerFailure,
    candidates: Sequence[Candidate],
    profiles: ProfileSet | None = None,
) -> CoolerFailureDecision:
    profiles = profiles or load_profiles()
    to_move, staying, unsupported = _sort_items(failure.items, profiles)

    if not to_move:
        return CoolerFailureDecision(
            food_bank_id=failure.food_bank_id,
            profile_set_version=profiles.version,
            items_to_move=(),
            items_staying=staying,
            items_unsupported=unsupported,
            reason_cards=(),
            proposal=None,
        )

    moving_profiles = [profiles.get(i.produce_id) for i in to_move]
    needed_lb = sum(i.pounds for i in to_move)
    items_phrase = _join([p.name.lower() for p in _unique(moving_profiles)])
    truck_problem = _truck_problem(failure, moving_profiles, items_phrase)

    assessments = [_assess(c, failure, needed_lb, items_phrase, truck_problem) for c in candidates]
    fitting = sorted(
        (a for a in assessments if a.fits),
        key=lambda a: (not a.full_fit, a.candidate.travel_minutes, -a.candidate.cold_space_lb, a.candidate.food_bank_id),
    )
    chosen = fitting[0] if fitting else None

    cards = tuple(_card(a, chosen, needed_lb) for a in assessments)
    proposal = None
    leftover = list(to_move)
    if chosen is not None:
        moved, leftover = _allocate(to_move, profiles, chosen.candidate.cold_space_lb)
        proposal = _proposal(failure, chosen, moved, next(c for c in cards if c.outcome == "chosen").text)

    fallback = tuple(_fallback(item, failure, profiles, chosen) for item in leftover)
    return CoolerFailureDecision(
        food_bank_id=failure.food_bank_id,
        profile_set_version=profiles.version,
        items_to_move=to_move,
        items_staying=staying,
        items_unsupported=unsupported,
        reason_cards=cards,
        proposal=proposal,
        fallback=fallback,
    )


def _sort_items(items: Sequence[HeldItem], profiles: ProfileSet):
    to_move, staying, unsupported = [], [], []
    for item in items:
        if item.produce_id not in profiles:
            unsupported.append(
                ItemDecision(item.produce_id, item.pounds, "no produce profile, so a human must check it; not assumed safe to stay or move")
            )
            continue
        profile = profiles.get(item.produce_id)
        cite = f"(produce profiles v{profiles.version})"
        if profile.moves_when_cooler_fails:
            what = "needs a fridge" if profile.needs_fridge else "needs a cold chain"
            to_move.append(ItemDecision(item.produce_id, item.pounds, f"{profile.name}: profile says it {what} {cite}, and the cooler failed, so it must move"))
        else:
            staying.append(ItemDecision(item.produce_id, item.pounds, f"{profile.name}: profile says it keeps without a fridge {cite}, so it stays"))
    return tuple(to_move), tuple(staying), tuple(unsupported)


def _truck_problem(failure: CoolerFailure, moving: Sequence[ProduceProfile], items_phrase: str) -> str | None:
    if failure.truck is None:
        return f"{failure.food_bank_name} has no truck free to move {items_phrase}"
    if not failure.truck.refrigerated and any(p.transport.cold_required for p in moving):
        return f"{failure.food_bank_name}'s truck isn't refrigerated, so {items_phrase} can't keep its cold chain"
    return None


@dataclass(frozen=True)
class _Assessment:
    candidate: Candidate
    fits: bool
    full_fit: bool
    positives: tuple[str, ...]
    problems: tuple[str, ...]
    facts: Mapping[str, Any]
    arrives_at: datetime | None
    collect: PickupWindow | None


def _assess(c: Candidate, failure: CoolerFailure, needed_lb: float, items_phrase: str, truck_problem: str | None) -> _Assessment:
    facts: dict[str, Any] = {"response": c.response}
    positives: list[str] = []
    problems: list[str] = []

    if c.response == "declined":
        facts["declined_reason"] = c.declined_reason
        problems.append(f"declined: {c.declined_reason}" if c.declined_reason else "declined")
        return _Assessment(c, False, False, (), tuple(problems), facts, None, None)
    if c.response == "no_answer":
        problems.append("didn't answer the request for cold space")
        return _Assessment(c, False, False, (), tuple(problems), facts, None, None)

    facts.update(cold_space_lb=c.cold_space_lb, travel_minutes=c.travel_minutes, pickup_windows=c.pickup_windows)

    full_fit = False
    if c.cold_space_lb is None:
        problems.append("didn't report its free cold space")
    elif c.cold_space_lb <= 0:
        problems.append("has no free cold space")
    elif c.cold_space_lb >= needed_lb:
        full_fit = True
        positives.append(f"has cold space for {_lb(c.cold_space_lb)} lb")
    else:
        positives.append(f"has cold space for only {_lb(c.cold_space_lb)} lb of the {_lb(needed_lb)} lb")

    if c.travel_minutes is not None:
        positives.append(f"{_num(c.travel_minutes)} minutes away")

    arrives_at = collect = None
    if c.travel_minutes is None:
        problems.append("has no recorded travel time")
    elif failure.truck is not None:
        departs_at = max(failure.detected_at, failure.truck.available_from)
        arrives_at = departs_at + timedelta(minutes=c.travel_minutes)
        facts["arrives_at"] = arrives_at
        collect, pickup_problem = _pickup_fit(c.pickup_windows, arrives_at, failure.households_pickup, items_phrase)
        if collect is not None:
            positives.append(f"households can collect {_window(collect)}")
        else:
            problems.append(pickup_problem)

    if truck_problem:
        problems.append(truck_problem)

    fits = not problems
    return _Assessment(c, fits, full_fit and fits, tuple(positives), tuple(problems), facts, arrives_at, collect)


def _pickup_fit(windows: Sequence[PickupWindow], arrives_at: datetime, households: PickupWindow, items_phrase: str):
    """The time households can collect at this candidate tonight, or the reason they can't."""
    earliest = max(arrives_at, households.start)
    for w in sorted(windows, key=lambda w: w.start):
        start, end = max(w.start, earliest), min(w.end, households.end)
        if start < end:
            return PickupWindow(start, end), None

    if not windows:
        return None, "has no pickup hours today"
    last_end = max(w.end for w in windows)
    first_start = min(w.start for w in windows)
    if last_end <= arrives_at:
        return None, f"pickup ends at {_clock(last_end)}, before the produce could arrive at {_clock(arrives_at)}, so households can't collect {items_phrase} tonight"
    if last_end <= households.start:
        return None, f"pickup ends at {_clock(last_end)}, so households can't collect {items_phrase} tonight"
    if first_start >= households.end:
        return None, f"pickup opens at {_clock(first_start)}, after households' pickup time ends at {_clock(households.end)}"
    return None, f"its pickup hours don't overlap households' pickup time, {_window(households)}"


def _card(a: _Assessment, chosen: _Assessment | None, needed_lb: float) -> ReasonCard:
    problems = list(a.problems)
    if a is chosen:
        outcome: CardOutcome = "chosen"
    elif a.fits:
        outcome = "fits_not_chosen"
        problems.append(_why_not_chosen(a, chosen, needed_lb))
    else:
        outcome = "rejected"

    text = f"{a.candidate.name}: " + ", ".join(a.positives)
    if problems:
        text += (", but " if a.positives else "") + "; ".join(problems)
    text += ". Chosen." if outcome == "chosen" else ". Not chosen."
    return ReasonCard(
        food_bank_id=a.candidate.food_bank_id,
        name=a.candidate.name,
        outcome=outcome,
        facts=dict(a.facts),
        reasons=tuple(a.positives) + tuple(problems),
        text=text,
    )


def _why_not_chosen(a: _Assessment, chosen: _Assessment, needed_lb: float) -> str:
    if chosen.full_fit and not a.full_fit:
        return f"{chosen.candidate.name} has cold space for all {_lb(needed_lb)} lb"
    if chosen.candidate.travel_minutes < a.candidate.travel_minutes:
        return f"{chosen.candidate.name} is closer ({_num(chosen.candidate.travel_minutes)} minutes)"
    if not a.full_fit and chosen.candidate.cold_space_lb > a.candidate.cold_space_lb:
        return f"{chosen.candidate.name} has more cold space ({_lb(chosen.candidate.cold_space_lb)} lb)"
    return f"{chosen.candidate.name} has the same facts and is listed first"


def _allocate(to_move: Sequence[ItemDecision], profiles: ProfileSet, cold_space_lb: float):
    """Fill the receiver's cold space, shortest room-temperature life first."""

    def room_life(item: ItemDecision) -> float:
        room = profiles.get(item.produce_id).days_usable_room
        return room.min if room else 0.0

    moved: list[HeldItem] = []
    leftover: list[ItemDecision] = []
    space = cold_space_lb
    for item in sorted(to_move, key=room_life):
        take = min(item.pounds, space)
        if take > 0:
            moved.append(HeldItem(item.produce_id, take))
            space -= take
        if take < item.pounds:
            leftover.append(ItemDecision(item.produce_id, item.pounds - take, item.reason))
    return tuple(moved), leftover


def _proposal(failure: CoolerFailure, chosen: _Assessment, moved: tuple[HeldItem, ...], reason: str) -> ProposedVersion:
    truck = failure.truck
    kind = "refrigerated truck" if truck.refrigerated else "truck"
    return ProposedVersion(
        lot_id=failure.lot_id,
        based_on_version=failure.current_version,
        version=failure.current_version + 1,
        proposer_id=failure.food_bank_id,
        receiving_food_bank_id=chosen.candidate.food_bank_id,
        receiving_food_bank_name=chosen.candidate.name,
        items=moved,
        mover=f"{failure.food_bank_name}'s {kind}",
        departs_at=max(failure.detected_at, truck.available_from),
        arrives_at=chosen.arrives_at,
        households_collect=chosen.collect,
        # The receiver's manager approves the delivery; the proposer's manager approves the truck run.
        needs_approval_from=(chosen.candidate.food_bank_id, failure.food_bank_id),
        reason=reason,
    )


def _fallback(item: ItemDecision, failure: CoolerFailure, profiles: ProfileSet, chosen: _Assessment | None) -> FallbackOutcome:
    profile = profiles.get(item.produce_id)
    if chosen is None:
        why = "no other food bank can take it in time"
    else:
        why = f"{chosen.candidate.name} has no cold space for these {_lb(item.pounds)} lb"

    today = failure.detected_at.date()
    windows = sorted(
        (w for w in failure.own_pickup_windows if w.end > failure.detected_at and w.end.date() == today),
        key=lambda w: w.start,
    )
    if not windows:
        return FallbackOutcome(item.produce_id, item.pounds, "unclaimed", f"{why}, and {failure.food_bank_name} has no pickup left today")

    window = windows[0]
    room = profile.days_usable_room
    hours_needed = (window.end - failure.detected_at).total_seconds() / 3600
    if room is None or hours_needed > room.min * 24:
        kept = "no room-temperature life given" if room is None else f"{_num(room.min)} day minimum at room temperature"
        return FallbackOutcome(
            item.produce_id,
            item.pounds,
            "unclaimed",
            f"{why}, and {profile.name.lower()} won't keep at room temperature until pickup ends at {_clock(window.end)} "
            f"(profile: {kept}, v{profiles.version})",
        )

    return FallbackOutcome(
        item.produce_id,
        item.pounds,
        "same_day_offer",
        f"{why}; offer it tonight to {failure.food_bank_name} households who can come {_window(window)}, "
        f"since {profile.name.lower()} keeps {_num(room.min)} to {_num(room.max)} days at room temperature "
        f"(profile v{profiles.version})",
    )


# --- Recorded scenario loader --------------------------------------------------------------


def parse_scenario(data: Mapping[str, Any]) -> tuple[CoolerFailure, tuple[Candidate, ...]]:
    """Build inputs from a recorded scenario: ``{"failure": {...}, "candidates": [...]}``."""
    f = data["failure"]
    truck = f.get("truck")
    failure = CoolerFailure(
        food_bank_id=f["food_bank_id"],
        food_bank_name=f["food_bank_name"],
        lot_id=f["lot_id"],
        current_version=int(f["current_version"]),
        detected_at=_dt(f["detected_at"]),
        items=tuple(_item(i) for i in f["items"]),
        households_pickup=_pickup(f["households_pickup"]),
        own_pickup_windows=tuple(_pickup(w) for w in f.get("own_pickup_windows", [])),
        truck=None if truck is None else Truck(refrigerated=bool(truck["refrigerated"]), available_from=_dt(truck["available_from"])),
    )
    candidates = tuple(_candidate(c) for c in data.get("candidates", []))
    return failure, candidates


def _item(raw: Mapping[str, Any]) -> HeldItem:
    pounds = float(raw["pounds"])
    if pounds <= 0:
        raise ValueError(f"held item {raw['produce_id']!r} must have positive pounds")
    return HeldItem(produce_id=raw["produce_id"], pounds=pounds)


def _candidate(raw: Mapping[str, Any]) -> Candidate:
    response = raw.get("response")
    if response not in ("answered", "declined", "no_answer"):
        raise ValueError(f"candidate {raw.get('food_bank_id')!r} has unknown response {response!r}")
    return Candidate(
        food_bank_id=raw["food_bank_id"],
        name=raw["name"],
        response=response,
        cold_space_lb=None if raw.get("cold_space_lb") is None else float(raw["cold_space_lb"]),
        pickup_windows=tuple(_pickup(w) for w in raw.get("pickup_windows", [])),
        travel_minutes=None if raw.get("travel_minutes") is None else float(raw["travel_minutes"]),
        declined_reason=raw.get("declined_reason"),
    )


def _pickup(raw: Mapping[str, Any]) -> PickupWindow:
    window = PickupWindow(start=_dt(raw["start"]), end=_dt(raw["end"]))
    if window.end <= window.start:
        raise ValueError(f"pickup window ends before it starts: {raw}")
    return window


def _unique(profiles: Sequence[ProduceProfile]) -> list[ProduceProfile]:
    seen: dict[str, ProduceProfile] = {}
    for p in profiles:
        seen.setdefault(p.id, p)
    return list(seen.values())
