"""Stand-in calculators (#11). Synthetic inputs; numbers come from #12's placeholder table."""

from datetime import datetime

import pytest

from harvestnet_agents.calculators import (
    CalculatorError,
    HouseholdBalance,
    StandInCalculators,
)
from harvestnet_agents.negotiation import StorageSlot, TimeWindow

calc = StandInCalculators()


def t(hhmm):
    return datetime.fromisoformat(f"2026-10-13T{hhmm}")


def test_fair_share_gap_sums_pounds_below_fair_share_and_ignores_households_at_or_above_it():
    # Placeholder table: 1 person 4 lb, 4 people 12 lb, 5 people 14 lb.
    result = calc.fair_share_gap(
        [HouseholdBalance(4, 2), HouseholdBalance(1, 4), HouseholdBalance(5, 0), HouseholdBalance(1, 9)]
    )
    assert result.gap_lb == 24  # (12 - 2) + 0 + (14 - 0) + 0
    assert result.households == 4
    assert result.households_below == 2
    assert result.table_version == "0.1.0-placeholder"


def test_gap_after_plan_reports_remaining_gap_and_pounds_above_it():
    assert calc.gap_after_plan(310, 250).remaining_gap_lb == 60
    assert calc.gap_after_plan(310, 250).above_gap_lb == 0
    over = calc.gap_after_plan(40, 100)
    assert (over.remaining_gap_lb, over.above_gap_lb) == (0, 60)


def test_storage_at_reads_the_slot_covering_the_time_and_treats_no_record_as_no_space():
    slots = (
        StorageSlot(TimeWindow(t("12:00"), t("16:00")), cold_free_lb=100, dry_free_lb=500),
        StorageSlot(TimeWindow(t("16:00"), t("22:00")), cold_free_lb=250, dry_free_lb=400),
    )
    assert calc.storage_at(slots, t("16:10")).cold_free_lb == 250
    assert calc.storage_at(slots, t("13:00")).dry_free_lb == 500
    missing = calc.storage_at(slots, t("23:00"))
    assert (missing.cold_free_lb, missing.dry_free_lb, missing.recorded) == (0, 0, False)


def test_capacity_fit_gives_room_left_or_how_far_over():
    assert calc.capacity_fit(free_lb=250, needed_lb=200).room_left_lb == 50
    over = calc.capacity_fit(free_lb=150, needed_lb=200)
    assert (over.fits, over.over_by_lb, over.room_left_lb) == (False, 50, 0)


def test_pickup_feasibility_needs_a_window_after_arrival_that_opens_before_the_produce_spoils():
    windows = (TimeWindow(t("18:00"), t("20:00")),)
    ok = calc.pickup_feasibility(t("16:10"), windows, usable_until=t("23:00"))
    assert ok.feasible and ok.collect == TimeWindow(t("18:00"), t("20:00"))

    late = calc.pickup_feasibility(t("20:30"), windows, usable_until=datetime(2026, 10, 15))
    assert not late.feasible and late.problem == "arrives_after_pickup_ends"

    spoils = calc.pickup_feasibility(t("16:10"), windows, usable_until=t("17:00"))
    assert not spoils.feasible and spoils.problem == "spoils_before_pickup"

    assert calc.pickup_feasibility(t("16:10"), (), usable_until=t("23:00")).problem == "no_pickup_hours"


def test_arrival_time_adds_recorded_travel_minutes():
    assert calc.arrival_time(t("15:00"), 40) == t("15:40")
    with pytest.raises(CalculatorError):
        calc.arrival_time(t("15:00"), -5)


def test_to_pounds_converts_through_produce_profiles():
    assert calc.to_pounds("apples", 300, "lb") == 300
    assert calc.to_pounds("apples", 10, "case", lb_per_unit=40) == 400
    with pytest.raises(CalculatorError):
        calc.to_pounds("apples", 10, "case")  # no pack weight: never guessed


def test_every_call_is_logged_with_inputs_and_result():
    c = StandInCalculators()
    c.gap_after_plan(310, 250)
    assert c.calls[-1].name == "gap_after_plan"
    assert c.calls[-1].inputs == {"gap_lb": 310, "planned_lb": 250}
