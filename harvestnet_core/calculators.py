"""Real deterministic calculators; no stand-in inheritance or model arithmetic."""
from dataclasses import asdict
import math
from datetime import timedelta
from harvestnet_agents.calculators import CalculatorCall, CapacityFit, GapAfterPlan, GapResult, PickupCheck, StorageAt
from harvestnet_agents.calculators import CalculatorError as AgentsCalculatorError
from harvestnet_agents.fair_share import FairShareError, fair_share, load_fair_share_table
from harvestnet_agents.profiles import UnitConversionError, load_profiles, to_pounds
from harvestnet_agents.negotiation import TimeWindow
from . import protocol


class CalculatorError(AgentsCalculatorError):
    """Bad calculator input. A ``ValueError`` and Lane B's ``CalculatorError``, so the
    scenario runner logs it as a calculator error instead of crashing."""


class UnknownProduce(CalculatorError, KeyError):
    """No produce profile. Still a ``KeyError`` for callers that map it to not found."""


class BadUnit(CalculatorError, UnitConversionError):
    """A unit the profile can't convert. Still a ``UnitConversionError``."""


def number(value):
    """A finite nonnegative number, or a ``CalculatorError``."""
    try:
        return protocol.number(value)
    except ValueError as exc:
        raise CalculatorError(str(exc)) from exc


def finite(value):
    """A finite number of either sign (a change, or a free space that may be negative)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CalculatorError("a finite number is required")
    return float(value)


class Calculators:
    label = "deterministic core calculators"

    # Where these answers can differ from Lane B's stand-ins for the same input, and why.
    # The recorder adds the sentence to each difference it logs (#20). Elsewhere the
    # answers match; these calculators also refuse inputs the stand-ins pass through
    # (NaN, infinity, booleans, a zero pack weight), which shows as an error, not an answer.
    stand_in_differences = {
        "storage_at": "where storage readings overlap at that moment, the core calculator takes the smallest free space "
                      "among them, so it never counts space a reading doesn't promise; the stand-in reads only the first "
                      "reading that covers the moment.",
    }

    def __init__(self):
        self.profiles = load_profiles()
        self.table = load_fair_share_table()
        self.calls = []

    def log(self, name, inputs, result):
        self.calls.append(CalculatorCall(name, inputs, result))
        return result

    def fair_share(self, household_size):
        if isinstance(household_size, bool) or not isinstance(household_size, int) or household_size < 1:
            raise CalculatorError("household size must be a positive integer")
        try:
            share = fair_share(household_size, self.table)
        except FairShareError as exc:
            raise CalculatorError(str(exc)) from exc
        return self.log("fair_share", {"household_size": household_size}, share)

    def fair_share_gap(self, households):
        gaps = [max(0, self.fair_share(h.household_size).pounds - number(h.received_lb)) for h in households]
        return self.log("fair_share_gap", {"households": [asdict(h) for h in households]}, GapResult(sum(gaps), len(gaps), sum(x > 0 for x in gaps), self.table.version))

    def household_portions(self, pounds_available, households):
        available = number(pounds_available)
        codes = [h["request_code"] for h in households]
        if len(codes) != len(set(codes)):
            raise CalculatorError("duplicate household")
        shares = [self.fair_share(h["household_size"]).pounds for h in households]
        gaps = [max(0, s - number(h["received_lb"])) for s, h in zip(shares, households)]
        # Water-fill the largest deficits until they meet the next deficit.
        remaining = min(available, sum(gaps))
        residual = gaps.copy()
        while remaining > 1e-9 and max(residual, default=0) > 1e-9:
            largest = max(residual)
            group = [i for i, g in enumerate(residual) if abs(g - largest) < 1e-9]
            next_level = max((g for g in residual if g < largest - 1e-9), default=0)
            each = min(largest - next_level, remaining / len(group))
            for i in group:
                residual[i] -= each
            remaining -= each * len(group)
        portions = [{"request_code": c, "pounds": g-r, "fair_share_lb": s, "still_below_lb": r} for c,g,r,s in zip(codes,gaps,residual,shares)]
        return self.log("household_portions", {"pounds_available": available, "households": households}, {"portions": portions, "left_over_lb": max(0, available - sum(p["pounds"] for p in portions)), "table_version": self.table.version})

    def storage_at(self, storage, at):
        candidates = [s for s in storage if s.window.start <= at < s.window.end]
        # Overlapping readings are conservative, never summed as extra capacity.
        result = StorageAt(min((finite(s.cold_free_lb) for s in candidates), default=0), min((finite(s.dry_free_lb) for s in candidates), default=0), bool(candidates))
        return self.log("storage_at", {"at": at.isoformat(), "storage": [asdict(s) for s in storage]}, result)

    def capacity_fit(self, free_lb, needed_lb):
        # Negative free space (an overfull store) counts as no room, like the stand-in.
        recorded, needed = finite(free_lb), number(needed_lb)
        free = max(0.0, recorded)
        return self.log("capacity_fit", {"free_lb": recorded, "needed_lb": needed}, CapacityFit(needed <= free, max(0, free-needed), max(0, needed-free)))

    def gap_after_plan(self, gap_lb, planned_lb):
        gap, planned = number(gap_lb), number(planned_lb)
        return self.log("gap_after_plan", {"gap_lb": gap, "planned_lb": planned}, GapAfterPlan(max(0, gap-planned), max(0, planned-gap)))

    def adjust_pounds(self, current_lb, change_lb):
        # change_lb may be negative (removing pounds); the result never goes below zero.
        current, change = number(current_lb), finite(change_lb)
        result=number(max(0.0,current+change))
        return self.log("adjust_pounds", {"current_lb": current, "change_lb": change}, result)

    def arrival_time(self, departs_at, travel_minutes):
        return self.log("arrival_time", {"departs_at": departs_at.isoformat(), "travel_minutes": number(travel_minutes)}, departs_at + timedelta(minutes=travel_minutes))

    def pickup_feasibility(self, arrives_at, pickup_windows, usable_until):
        last = max((w.end for w in pickup_windows), default=None)
        result = PickupCheck(False, None, "no_pickup_hours" if last is None else "arrives_after_pickup_ends" if last <= arrives_at else "spoils_before_pickup", last)
        for w in sorted(pickup_windows, key=lambda w: w.start):
            start, end = max(arrives_at, w.start), min(usable_until, w.end)
            if start < end:
                result = PickupCheck(True, TimeWindow(start, end), None, last)
                break
        return self.log("pickup_feasibility", {"arrives_at": arrives_at.isoformat(), "usable_until": usable_until.isoformat(), "pickup_windows": [asdict(w) for w in pickup_windows]}, result)

    def to_pounds(self, produce_id, quantity, unit, lb_per_unit=None):
        number(quantity)
        if lb_per_unit is not None:
            if number(lb_per_unit) == 0:
                raise CalculatorError("pack weight must be positive")
        if produce_id not in self.profiles:
            raise UnknownProduce(f"no produce profile for {produce_id!r}")
        try:
            result = number(to_pounds(self.profiles.get(produce_id), quantity, unit, lb_per_unit))
        except UnitConversionError as exc:
            raise BadUnit(str(exc)) from exc
        return self.log("to_pounds", {"produce_id": produce_id, "quantity": quantity, "unit": unit, "lb_per_unit": lb_per_unit}, result)
