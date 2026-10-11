"""Lane B's rule checks catch what they claim to (#20).

Each test takes the normal afternoon's passing event log, breaks one rule in a copy, and
checks that exactly the matching rule check fails. All numbers are synthetic."""

import copy
from pathlib import Path

import pytest

from harvestnet_agents.lane_b_rule_checks import LANE_B_RULE_CHECKS, run_lane_b_rule_checks
from harvestnet_agents.scenario import load_scenario
from harvestnet_agents.scenario_runner import run_scenario

CONTRACT_EXAMPLE = Path(__file__).parents[2] / "docs" / "contracts" / "examples" / "scenario-normal-afternoon.json"


@pytest.fixture(scope="module")
def run():
    return run_scenario(load_scenario(CONTRACT_EXAMPLE))


@pytest.fixture
def events(run):
    return copy.deepcopy(run.events)


def failing(events):
    return {name for name, r in run_lane_b_rule_checks(events).items() if not r.passed}


def first(events, kind, **match):
    return next(e for e in events if e["kind"] == kind and all(e.get(k) == v for k, v in match.items()))


def move(events, org, action):
    return next(e for e in events if e["kind"] == "move" and e["organization_id"] == org and e["move"]["action"] == action)


def test_the_untouched_log_passes_every_check(events):
    assert failing(events) == set()


def test_lane_b_check_names_never_collide_with_the_fixtures_lane_a_checks(run):
    assert not set(LANE_B_RULE_CHECKS) & set(run.fixture_rule_checks)
    merged = {**{name: True for name in run.fixture_rule_checks}, **run.rule_checks()}
    assert len(merged) == len(LANE_B_RULE_CHECKS) + len(run.fixture_rule_checks)


# no_central_decider


def test_a_move_made_for_another_organization_fails(events):
    move(events, "city", "accept")["move"]["organization_id"] = "rural"
    assert "no_central_decider" in failing(events)


def test_facts_belonging_to_another_organization_fail(events):
    move(events, "rural", "accept")["facts"]["food_bank_id"] = "city"
    assert failing(events) == {"no_central_decider"}


def test_facts_that_name_a_household_fail(events):
    first(events, "facts", organization_id="advocate")["facts"]["gaps"][0]["name"] = "K7P4"
    assert failing(events) == {"no_central_decider"}


def test_a_food_bank_changing_another_food_banks_share_fails(events):
    move(events, "rural", "counter")["move"]["amendment"]["food_bank_id"] = "eastside"
    assert "no_central_decider" in failing(events)


def test_an_approval_not_from_the_organizations_own_human_fails(events):
    first(events, "approval", organization_id="rural")["source"] = "harness"
    assert "no_central_decider" in failing(events)


# every_move_has_reason


def test_a_move_without_a_reason_fails(events):
    move(events, "eastside", "accept")["move"]["reason"] = "  "
    assert "every_move_has_reason" in failing(events)


# advocate_never_votes


def test_an_advocate_accept_fails(events):
    move(events, "advocate", "pass")["move"]["action"] = "accept"
    assert failing(events) == {"advocate_never_votes"}


def test_an_advocate_hold_fails(events):
    first(events, "hold", organization_id="market").update(organization_id="advocate", owner_id="advocate")
    assert "advocate_never_votes" in failing(events)


# numbers_trace_to_inputs


def test_an_invented_number_in_a_reason_fails(events):
    m = move(events, "city", "counter")
    m["move"]["reason"] = m["move"]["reason"].replace("Asking for 31 lb", "Asking for 45 lb")
    assert failing(events) == {"numbers_trace_to_inputs"}


def test_arithmetic_in_a_reason_fails(events):
    m = move(events, "market", "accept")
    m["move"]["reason"] += " That is 32 + 19 lb by drop-off."
    assert failing(events) == {"numbers_trace_to_inputs"}


def test_an_invented_amendment_amount_fails(events):
    move(events, "eastside", "counter")["move"]["amendment"]["pounds"] = 23.0
    assert "numbers_trace_to_inputs" in failing(events)


def test_an_invented_time_fails(events):
    m = move(events, "city", "accept")
    m["move"]["reason"] = m["move"]["reason"].replace("3:20 pm", "3:35 pm")
    assert failing(events) == {"numbers_trace_to_inputs"}


def test_a_fair_share_gap_that_no_calculator_gave_fails(events):
    first(events, "facts", organization_id="rural")["facts"]["demand"]["below_fair_share_lb"] = 40
    assert failing(events) == {"numbers_trace_to_inputs"}


def test_offer_pounds_that_no_unit_calculator_gave_fail(events):
    first(events, "version", version=1)["terms"]["items"][2]["pounds"] = 450
    assert "numbers_trace_to_inputs" in failing(events)


# commits_only_with_every_named_approval


def test_a_commitment_missing_one_named_approval_fails(events):
    events.remove(first(events, "approval", organization_id="eastside"))
    assert failing(events) == {"commits_only_with_every_named_approval"}


def test_an_approval_of_other_terms_fails(events):
    first(events, "approval", organization_id="city")["terms_hash"] = "0" * 64
    assert failing(events) == {"commits_only_with_every_named_approval"}


def test_a_commitment_after_the_deadline_fails(events):
    first(events, "commitment")["at"] = "2026-10-13T15:05:00-07:00"
    assert "commits_only_with_every_named_approval" in failing(events)


def test_a_commitment_without_a_named_organizations_holds_fails(events):
    for h in [e for e in events if e["kind"] == "hold" and e["organization_id"] == "rural"]:
        events.remove(h)
    assert failing(events) == {"commits_only_with_every_named_approval"}


def test_a_move_marked_as_committing_fails(events):
    move(events, "market", "request_hold")["commits"] = True
    assert failing(events) == {"commits_only_with_every_named_approval"}


# cold_dependent_produce_follows_profiles


def test_cold_chain_produce_on_an_unrefrigerated_drop_off_fails(events):
    held = first(events, "held")
    terms = first(events, "version", version=held["version"])["terms"]
    for a in terms["allocations"]:
        if a["produce_id"] == "romaine":
            a["food_bank_id"] = "rural"  # rural is dropped off by the donor's unrefrigerated vehicle
    assert "cold_dependent_produce_follows_profiles" in failing(events)


def test_cold_produce_beyond_cold_space_at_arrival_fails(events):
    city = first(events, "facts", organization_id="city")
    city["facts"]["storage"][0]["cold_free_lb"] = 20
    assert failing(events) == {"cold_dependent_produce_follows_profiles"}


def test_moving_produce_that_does_not_depend_on_cold_after_a_cooler_failure_fails(events):
    first(events, "cooler_failure_assessment")["items_to_move"].append({"produce_id": "apples", "pounds": 5, "reason": "x"})
    assert failing(events) == {"cold_dependent_produce_follows_profiles"}
