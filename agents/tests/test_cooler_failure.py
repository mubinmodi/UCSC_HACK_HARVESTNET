"""Cooler-failure decision logic (ticket #15), tested on recorded candidate lists."""

import copy
import dataclasses
import json
from datetime import datetime
from importlib import resources
from pathlib import Path

import pytest

from harvestnet_agents.cooler_failure import PickupWindow, assess_cooler_failure, parse_scenario
from harvestnet_agents.profiles import load_profiles

FIXTURES = Path(__file__).parent / "fixtures" / "cooler_failure"


def recorded(name):
    return json.loads((FIXTURES / name).read_text())


def run(name, profiles=None, **failure_changes):
    failure, candidates = parse_scenario(recorded(name))
    if failure_changes:
        failure = dataclasses.replace(failure, **failure_changes)
    return assess_cooler_failure(failure, candidates, profiles=profiles)


def card(decision, food_bank_id):
    return next(c for c in decision.reason_cards if c.food_bank_id == food_bank_id)


# --- Which items must move: read from profiles, not crop names --------------------------


def test_only_items_whose_profile_needs_cold_move():
    decision = run("city_cooler_fails.json")
    assert [(i.produce_id, i.pounds) for i in decision.items_to_move] == [("romaine", 200)]
    assert {i.produce_id for i in decision.items_staying} == {"apples", "potatoes", "tomatoes"}


def test_item_reasons_cite_the_profile_version():
    decision = run("city_cooler_fails.json")
    version = load_profiles().version
    romaine = decision.items_to_move[0]
    assert "needs a fridge" in romaine.reason and version in romaine.reason
    apples = next(i for i in decision.items_staying if i.produce_id == "apples")
    assert "without a fridge" in apples.reason and version in apples.reason


def _profiles_with(changes):
    data = json.loads(resources.files("harvestnet_agents").joinpath("data", "produce_profiles.json").read_text())
    data = copy.deepcopy(data)
    for profile in data["profiles"]:
        for field, value in changes.get(profile["id"], {}).items():
            profile[field]["value"] = value
    return load_profiles(data)


def test_changing_the_profile_changes_the_decision():
    # ADR 0003: flip the profile fields and the same crop names behave differently.
    profiles = _profiles_with(
        {
            "romaine": {"needs_fridge": False, "transport_temperature": {
                "target_min_c": 0, "target_max_c": 5, "cold_required": False,
                "chilling_injury_below_c": None, "freezing_injury_at_c": -0.2}},
            "apples": {"needs_fridge": True},
        }
    )
    decision = run("city_cooler_fails.json", profiles=profiles)
    assert [i.produce_id for i in decision.items_to_move] == ["apples"]
    assert "romaine" in {i.produce_id for i in decision.items_staying}


def test_item_without_a_profile_goes_to_a_human_not_assumed():
    failure, candidates = parse_scenario(recorded("city_cooler_fails.json"))
    failure = dataclasses.replace(failure, items=failure.items + (dataclasses.replace(failure.items[0], produce_id="kale", pounds=30),))
    decision = assess_cooler_failure(failure, candidates)
    assert [i.produce_id for i in decision.items_unsupported] == ["kale"]
    assert "no produce profile" in decision.items_unsupported[0].reason
    assert "kale" not in {i.produce_id for i in decision.items_to_move + decision.items_staying}


# --- Reason cards: every candidate, built from recorded facts ----------------------------


def test_every_candidate_gets_a_reason_card():
    decision = run("city_cooler_fails.json")
    assert {c.food_bank_id for c in decision.reason_cards} == {"rural", "eastside", "westside", "southside", "northside"}
    assert [c.food_bank_id for c in decision.reason_cards if c.outcome == "chosen"] == ["eastside"]


def test_chosen_card_states_its_facts():
    text = card(run("city_cooler_fails.json"), "eastside").text
    assert text.startswith("Eastside food bank:")
    assert "cold space for 250 lb" in text
    assert "15 minutes away" in text
    assert "6 pm to 8 pm" in text
    assert text.endswith("Chosen.")


def test_rejected_for_pickup_ending_too_early():
    rural = card(run("city_cooler_fails.json"), "rural")
    assert rural.outcome == "rejected"
    assert "has cold space for 300 lb" in rural.text
    assert "pickup ends at 6 pm, so households can't collect romaine lettuce tonight" in rural.text
    assert rural.text.endswith("Not chosen.")


def test_fitting_but_farther_candidate_is_not_chosen_with_comparison():
    westside = card(run("city_cooler_fails.json"), "westside")
    assert westside.outcome == "fits_not_chosen"
    assert "30 minutes away" in westside.text
    assert "Eastside food bank is closer (15 minutes)" in westside.text


def test_declined_and_unanswered_candidates_get_cards():
    decision = run("city_cooler_fails.json")
    southside = card(decision, "southside")
    assert southside.outcome == "rejected"
    assert "declined: walk-in cooler is full until tomorrow's distribution" in southside.text
    assert "didn't answer" in card(decision, "northside").text


def test_card_facts_are_the_recorded_inputs():
    eastside = card(run("city_cooler_fails.json"), "eastside")
    assert eastside.facts["cold_space_lb"] == 250
    assert eastside.facts["travel_minutes"] == 15
    assert eastside.facts["arrives_at"] == datetime(2026, 10, 13, 16, 15)


def test_rejected_when_produce_cannot_arrive_before_pickup_ends():
    hilltop = card(run("no_candidate_fits.json"), "hilltop")
    assert "pickup ends at 7 pm, before the produce could arrive at 7:20 pm" in hilltop.text


def test_rejected_for_no_cold_space():
    assert "has no free cold space" in card(run("no_candidate_fits.json"), "eastside").text


def test_unrefrigerated_truck_rejects_every_candidate_with_the_reason():
    failure, candidates = parse_scenario(recorded("city_cooler_fails.json"))
    failure = dataclasses.replace(failure, truck=dataclasses.replace(failure.truck, refrigerated=False))
    decision = assess_cooler_failure(failure, candidates)
    assert decision.proposal is None
    for c in decision.reason_cards:
        assert c.outcome == "rejected"
    assert "City food bank's truck isn't refrigerated" in card(decision, "eastside").text


# --- The proposal: a draft that the receiving food bank still decides on -------------------


def test_proposal_names_the_receiver_and_awaits_its_decision():
    proposal = run("city_cooler_fails.json").proposal
    assert proposal.receiving_food_bank_id == "eastside"
    assert proposal.lot_id == "lot-farmers-market-1"
    assert (proposal.based_on_version, proposal.version) == (3, 4)
    assert proposal.proposer_id == "city"
    assert [(i.produce_id, i.pounds) for i in proposal.items] == [("romaine", 200)]
    assert proposal.status == "awaiting_receiver_decision"
    assert proposal.approvals == ()
    assert proposal.committed is False
    assert set(proposal.needs_approval_from) == {"eastside", "city"}
    assert proposal.arrives_at == datetime(2026, 10, 13, 16, 15)
    assert "City food bank's refrigerated truck" in proposal.mover


def test_partial_fit_moves_what_fits_and_offers_the_rest_same_day():
    data = recorded("city_cooler_fails.json")
    for c in data["candidates"]:
        if c["food_bank_id"] in ("eastside", "westside"):
            c["cold_space_lb"] = 150
    failure, candidates = parse_scenario(data)
    decision = assess_cooler_failure(failure, candidates)
    assert decision.proposal.receiving_food_bank_id == "eastside"
    assert [(i.produce_id, i.pounds) for i in decision.proposal.items] == [("romaine", 150)]
    assert [(f.produce_id, f.pounds, f.kind) for f in decision.fallback] == [("romaine", 50, "same_day_offer")]
    assert "cold space for only 150 lb of the 200 lb" in card(decision, "eastside").text
    assert "Eastside food bank has no cold space for these 50 lb" in decision.fallback[0].reason


def test_equal_distance_partial_fits_prefer_more_cold_space():
    data = recorded("city_cooler_fails.json")
    for c in data["candidates"]:
        if c["food_bank_id"] == "eastside":
            c["cold_space_lb"] = 120
        if c["food_bank_id"] == "westside":
            c.update(cold_space_lb=180, travel_minutes=15)
    failure, candidates = parse_scenario(data)
    decision = assess_cooler_failure(failure, candidates)
    assert decision.proposal.receiving_food_bank_id == "westside"
    assert "Westside food bank has more cold space (180 lb)" in card(decision, "eastside").text


# --- No candidate fits: same-day offer or unclaimed, with a reason -----------------------


def test_no_candidate_fits_gives_same_day_offer_with_reason():
    decision = run("no_candidate_fits.json")
    assert decision.proposal is None
    assert all(c.outcome == "rejected" for c in decision.reason_cards)
    (offer,) = decision.fallback
    assert (offer.produce_id, offer.pounds, offer.kind) == ("romaine", 200, "same_day_offer")
    assert "no other food bank can take it in time" in offer.reason
    assert "6 pm to 8 pm" in offer.reason


def test_no_candidate_and_pickup_already_over_is_unclaimed_with_reason():
    decision = run("no_candidate_fits.json", detected_at=datetime(2026, 10, 13, 20, 30))
    (outcome,) = decision.fallback
    assert outcome.kind == "unclaimed"
    assert "no pickup left today" in outcome.reason


def test_no_candidate_and_item_wont_keep_until_pickup_is_unclaimed():
    # A profile whose room-temperature life (0.1 day) ends before tonight's pickup ends.
    profiles = _profiles_with({"romaine": {"days_usable_room": {"min": 0.1, "max": 0.1}}})
    decision = run("no_candidate_fits.json", profiles=profiles)
    (outcome,) = decision.fallback
    assert outcome.kind == "unclaimed"
    assert "won't keep at room temperature until pickup ends at 8 pm" in outcome.reason


def test_same_day_offer_needs_a_pickup_window_today():
    tomorrow = PickupWindow(start=datetime(2026, 10, 14, 18, 0), end=datetime(2026, 10, 14, 20, 0))
    decision = run("no_candidate_fits.json", own_pickup_windows=(tomorrow,))
    (outcome,) = decision.fallback
    assert outcome.kind == "unclaimed"
    assert "no pickup left today" in outcome.reason


def test_nothing_needs_to_move():
    failure, candidates = parse_scenario(recorded("city_cooler_fails.json"))
    failure = dataclasses.replace(failure, items=tuple(i for i in failure.items if i.produce_id != "romaine"))
    decision = assess_cooler_failure(failure, candidates)
    assert decision.items_to_move == ()
    assert decision.proposal is None
    assert decision.fallback == ()
    assert decision.reason_cards == ()
