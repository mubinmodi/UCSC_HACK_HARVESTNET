"""Stand-in calculators behind a small calculator interface (tickets #11 and #13).

**These are stand-ins, for unit tests only.** Lane A (ticket #8) owns the real
calculators, ``harvestnet_core.calculators.Calculators``, which implement this module's
interface (``Calculators``) plus ``fair_share`` and ``household_portions``. The harness
join (ticket #20, ``harvestnet_core.join``) runs every fixture with Lane A's real ones
and compares each call with these stand-ins. The deterministic stand-in
(``StandInCalculators``) stays so Lane B's unit tests run without Lane A's code; a
negotiator built without calculators still falls back to it, and ``run_scenario`` needs
calculators passed explicitly.

Calculators are the only source of derived numbers (ADR 0002). Every call is logged in
``calls`` with its inputs and result, so the LLM layer can check that each number in a
move traces back to an input or a calculator result.

The named calculators:

- ``fair_share_gap``: pounds a set of households is below fair share (uses #12's table).
- ``gap_after_plan``: a food bank's gap after the pounds a draft plans for it.
- ``storage_at``: storage over time (free cold and dry space at a moment).
- ``capacity_fit``: whether pounds fit a free space or a truck, and by how much.
- ``pickup_feasibility``: can households collect it after arrival and before it spoils?
- ``arrival_time``: departure plus recorded travel minutes.
- ``adjust_pounds``: a share after adding or removing pounds (never below zero), so
  no negotiator, rules-based or LLM, does arithmetic in its own words.
- ``to_pounds``: unit conversion through produce profiles (#12).
- ``proportional_split``: the pounds of one item two food banks hold, split in proportion to
  their fair-share gaps (ADR 0013, concede toward need), in whole tenths of a pound.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Mapping, Protocol, Sequence

from .fair_share import FairShareTable, fair_share, load_fair_share_table
from .negotiation import StorageSlot, TimeWindow
from .profiles import ProfileSet, UnitConversionError, load_profiles
from .profiles import to_pounds as _profile_to_pounds

__all__ = [
    "CalculatorCall",
    "CalculatorError",
    "Calculators",
    "CapacityFit",
    "GapAfterPlan",
    "GapResult",
    "HouseholdBalance",
    "PickupCheck",
    "ProportionalSplit",
    "StandInCalculators",
    "StorageAt",
    "result_to_dict",
    "split_in_proportion",
]


class CalculatorError(ValueError):
    """A calculator can't answer from the inputs given."""


@dataclass(frozen=True)
class HouseholdBalance:
    """One household's size and pounds received this week. Counts only, no identity."""

    household_size: int
    received_lb: float


@dataclass(frozen=True)
class GapResult:
    gap_lb: float
    households: int
    households_below: int
    table_version: str


@dataclass(frozen=True)
class GapAfterPlan:
    remaining_gap_lb: float
    above_gap_lb: float


@dataclass(frozen=True)
class StorageAt:
    cold_free_lb: float
    dry_free_lb: float
    recorded: bool  # False: no storage record covers that time, so no space is assumed


@dataclass(frozen=True)
class CapacityFit:
    fits: bool
    room_left_lb: float
    over_by_lb: float


PickupProblem = Literal["no_pickup_hours", "arrives_after_pickup_ends", "spoils_before_pickup"]


@dataclass(frozen=True)
class PickupCheck:
    feasible: bool
    collect: TimeWindow | None  # when households can collect, if feasible
    problem: PickupProblem | None
    last_pickup_end: datetime | None


@dataclass(frozen=True)
class ProportionalSplit:
    """The pounds of one item two (or more) food banks hold, split in proportion to their gaps."""

    total_lb: float  # the pounds they hold between them
    shares_lb: dict[str, float]  # each one's proportional share, in whole pounds, capped at its gap
    short_lb: dict[str, float]  # how far each one's holding is below its share (0 if at or above it)
    unassigned_lb: float  # pounds beyond every gap, or under a pound left by rounding (it stays where it is)


# Shares are counted in whole pounds (proposed): a food bank hands out pounds, not ounces, and a
# coarser unit keeps the split from being chased a tenth of a pound at a time.
SPLIT_UNIT_LB = 1


def split_in_proportion(held_lb: Mapping[str, float], gaps_lb: Mapping[str, float]) -> ProportionalSplit:
    """``proportional_split``, shared by the stand-ins and the core's calculators so both give
    the same answer. Shares are whole pounds (``SPLIT_UNIT_LB``), each at most its gap; the
    pounds left after rounding down go to the largest remainders (ties: food bank id). With
    pounds enough for every gap, each share is its gap and the rest is unassigned."""
    if set(held_lb) != set(gaps_lb) or not gaps_lb:
        raise CalculatorError("proportional_split needs the pounds held and the gap of the same food banks")
    for x in (*held_lb.values(), *gaps_lb.values()):
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0:
            raise CalculatorError("pounds held and gaps must be finite, nonnegative numbers")
    ids = sorted(gaps_lb)
    total = round(sum(float(held_lb[k]) for k in ids), 9)
    need = sum(float(gaps_lb[k]) for k in ids)
    if need <= 0:
        shares = {k: 0.0 for k in ids}
    elif total >= need:
        shares = {k: float(gaps_lb[k]) for k in ids}
    else:
        per = 1 / SPLIT_UNIT_LB
        count = math.floor(round(total * per, 6))
        quota = {k: count * gaps_lb[k] / need for k in ids}
        cap = {k: math.floor(round(gaps_lb[k] * per, 6)) for k in ids}
        units = {k: min(math.floor(round(quota[k], 6)), cap[k]) for k in ids}
        left = count - sum(units.values())
        for k in sorted(ids, key=lambda k: (-(quota[k] - units[k]), k)):
            if left <= 0:
                break
            if units[k] < cap[k]:
                units[k] += 1
                left -= 1
        shares = {k: float(units[k] * SPLIT_UNIT_LB) for k in ids}
    short = {k: round(max(0.0, shares[k] - held_lb[k]), 9) for k in ids}
    return ProportionalSplit(total, shares, short, round(max(0.0, total - sum(shares.values())), 9))


@dataclass(frozen=True)
class CalculatorCall:
    name: str
    inputs: dict[str, Any]
    result: Any


class Calculators(Protocol):
    """The proposed calculator interface. Lane A's real calculators should match it."""

    profiles: ProfileSet
    calls: list[CalculatorCall]

    def fair_share_gap(self, households: Sequence[HouseholdBalance]) -> GapResult: ...
    def gap_after_plan(self, gap_lb: float, planned_lb: float) -> GapAfterPlan: ...
    def storage_at(self, storage: Sequence[StorageSlot], at: datetime) -> StorageAt: ...
    def capacity_fit(self, free_lb: float, needed_lb: float) -> CapacityFit: ...
    def pickup_feasibility(self, arrives_at: datetime, pickup_windows: Sequence[TimeWindow], usable_until: datetime) -> PickupCheck: ...
    def arrival_time(self, departs_at: datetime, travel_minutes: float) -> datetime: ...
    def adjust_pounds(self, current_lb: float, change_lb: float) -> float: ...
    def to_pounds(self, produce_id: str, quantity: float, unit: str, lb_per_unit: float | None = None) -> float: ...
    def proportional_split(self, held_lb: Mapping[str, float], gaps_lb: Mapping[str, float]) -> ProportionalSplit: ...


@dataclass
class StandInCalculators:
    """Deterministic stand-ins for Lane A's calculators. Labeled stand-ins everywhere."""

    profiles: ProfileSet = field(default_factory=load_profiles)
    table: FairShareTable = field(default_factory=load_fair_share_table)
    calls: list[CalculatorCall] = field(default_factory=list)

    label = "stand-in calculators (Lane B, unit tests only; the harness uses Lane A's #8)"

    def fair_share_gap(self, households: Sequence[HouseholdBalance]) -> GapResult:
        gap = 0.0
        below = 0
        for h in households:
            if h.received_lb < 0:
                raise CalculatorError("received pounds can't be negative")
            short = fair_share(h.household_size, self.table).pounds - h.received_lb
            if short > 0:
                gap += short
                below += 1
        result = GapResult(gap_lb=gap, households=len(households), households_below=below, table_version=self.table.version)
        return self._log("fair_share_gap", {"households": [asdict(h) for h in households]}, result)

    def gap_after_plan(self, gap_lb: float, planned_lb: float) -> GapAfterPlan:
        if gap_lb < 0 or planned_lb < 0:
            raise CalculatorError("gap and planned pounds can't be negative")
        result = GapAfterPlan(remaining_gap_lb=max(0.0, gap_lb - planned_lb), above_gap_lb=max(0.0, planned_lb - gap_lb))
        return self._log("gap_after_plan", {"gap_lb": gap_lb, "planned_lb": planned_lb}, result)

    def storage_at(self, storage: Sequence[StorageSlot], at: datetime) -> StorageAt:
        slot = next((s for s in storage if s.window.start <= at < s.window.end), None)
        if slot is None:
            result = StorageAt(cold_free_lb=0.0, dry_free_lb=0.0, recorded=False)
        else:
            result = StorageAt(cold_free_lb=slot.cold_free_lb, dry_free_lb=slot.dry_free_lb, recorded=True)
        return self._log("storage_at", {"at": at.isoformat(), "slots": len(storage)}, result)

    def capacity_fit(self, free_lb: float, needed_lb: float) -> CapacityFit:
        if needed_lb < 0:
            raise CalculatorError("needed pounds can't be negative")
        free = max(0.0, free_lb)
        result = CapacityFit(fits=needed_lb <= free, room_left_lb=max(0.0, free - needed_lb), over_by_lb=max(0.0, needed_lb - free))
        return self._log("capacity_fit", {"free_lb": free_lb, "needed_lb": needed_lb}, result)

    def pickup_feasibility(self, arrives_at: datetime, pickup_windows: Sequence[TimeWindow], usable_until: datetime) -> PickupCheck:
        inputs = {"arrives_at": arrives_at.isoformat(), "usable_until": usable_until.isoformat(), "windows": len(pickup_windows)}
        if not pickup_windows:
            return self._log("pickup_feasibility", inputs, PickupCheck(False, None, "no_pickup_hours", None))
        last_end = max(w.end for w in pickup_windows)
        for w in sorted(pickup_windows, key=lambda w: w.start):
            start, end = max(w.start, arrives_at), min(w.end, usable_until)
            if start < end:
                return self._log("pickup_feasibility", inputs, PickupCheck(True, TimeWindow(start, end), None, last_end))
        problem: PickupProblem = "arrives_after_pickup_ends" if last_end <= arrives_at else "spoils_before_pickup"
        return self._log("pickup_feasibility", inputs, PickupCheck(False, None, problem, last_end))

    def arrival_time(self, departs_at: datetime, travel_minutes: float) -> datetime:
        if travel_minutes < 0:
            raise CalculatorError("travel minutes can't be negative")
        result = departs_at + timedelta(minutes=travel_minutes)
        return self._log("arrival_time", {"departs_at": departs_at.isoformat(), "travel_minutes": travel_minutes}, result)

    def adjust_pounds(self, current_lb: float, change_lb: float) -> float:
        if current_lb < 0:
            raise CalculatorError("current pounds can't be negative")
        result = max(0.0, current_lb + change_lb)
        return self._log("adjust_pounds", {"current_lb": current_lb, "change_lb": change_lb}, result)

    def to_pounds(self, produce_id: str, quantity: float, unit: str, lb_per_unit: float | None = None) -> float:
        if produce_id not in self.profiles:
            raise CalculatorError(f"no produce profile for {produce_id!r}")
        try:
            result = _profile_to_pounds(self.profiles.get(produce_id), quantity, unit, lb_per_unit)
        except UnitConversionError as exc:
            raise CalculatorError(str(exc)) from exc
        return self._log("to_pounds", {"produce_id": produce_id, "quantity": quantity, "unit": unit, "lb_per_unit": lb_per_unit}, result)

    def proportional_split(self, held_lb: Mapping[str, float], gaps_lb: Mapping[str, float]) -> ProportionalSplit:
        result = split_in_proportion(held_lb, gaps_lb)
        return self._log("proportional_split", {"held_lb": dict(held_lb), "gaps_lb": dict(gaps_lb)}, result)

    def _log(self, name: str, inputs: dict[str, Any], result: Any) -> Any:
        self.calls.append(CalculatorCall(name=name, inputs=inputs, result=result))
        return result


def result_to_dict(result: Any) -> Any:
    """A calculator result as JSON-ready data (datetimes as ISO strings)."""
    if is_dataclass(result):
        return {k: result_to_dict(v) for k, v in asdict(result).items()}
    if isinstance(result, dict):
        return {k: result_to_dict(v) for k, v in result.items()}
    if isinstance(result, datetime):
        return result.isoformat()
    return result
