"""Stand-in calculators behind a small calculator interface (tickets #11 and #13).

**These are stand-ins.** Lane A (ticket #8) owns the real calculators, and ticket #1
(contract day) was meant to agree their interface. Neither exists yet, so this module
proposes a minimal interface (``Calculators``) and a deterministic stand-in
(``StandInCalculators``) that both the rules-based negotiators (#11) and the LLM
negotiators' calculator tools (#13) call. Ticket #20 swaps in Lane A's real ones.

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
- ``to_pounds``: unit conversion through produce profiles (#12).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol, Sequence

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
    "StandInCalculators",
    "StorageAt",
    "result_to_dict",
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
    def to_pounds(self, produce_id: str, quantity: float, unit: str, lb_per_unit: float | None = None) -> float: ...


@dataclass
class StandInCalculators:
    """Deterministic stand-ins for Lane A's calculators. Labeled stand-ins everywhere."""

    profiles: ProfileSet = field(default_factory=load_profiles)
    table: FairShareTable = field(default_factory=load_fair_share_table)
    calls: list[CalculatorCall] = field(default_factory=list)

    label = "stand-in calculators (Lane B, pending Lane A ticket #8)"

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

    def to_pounds(self, produce_id: str, quantity: float, unit: str, lb_per_unit: float | None = None) -> float:
        if produce_id not in self.profiles:
            raise CalculatorError(f"no produce profile for {produce_id!r}")
        try:
            result = _profile_to_pounds(self.profiles.get(produce_id), quantity, unit, lb_per_unit)
        except UnitConversionError as exc:
            raise CalculatorError(str(exc)) from exc
        return self._log("to_pounds", {"produce_id": produce_id, "quantity": quantity, "unit": unit, "lb_per_unit": lb_per_unit}, result)

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
