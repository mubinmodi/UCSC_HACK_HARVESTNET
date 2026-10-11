"""Loading the contract's scenario fixture format (#20, docs/contracts/scenario-fixtures.md).

Every number here is synthetic, from the contract's example scenario."""

import copy
import json
from datetime import datetime
from pathlib import Path

import pytest

from harvestnet_agents.calculators import StandInCalculators
from harvestnet_agents.negotiation import AdvocateFacts, DonorFacts, FoodBankFacts, Role
from harvestnet_agents.scenario import (
    ScenarioError,
    draft_to_dict,
    facts_for,
    initial_draft,
    load_scenario,
)

CONTRACT_EXAMPLE = Path(__file__).parents[2] / "docs" / "contracts" / "examples" / "scenario-normal-afternoon.json"


def raw():
    return json.loads(CONTRACT_EXAMPLE.read_text())


def at(text):
    return datetime.fromisoformat(f"2026-10-13T{text}:00-07:00")


@pytest.fixture
def scenario():
    return load_scenario(CONTRACT_EXAMPLE)


def test_the_contract_example_loads_with_its_organizations_turn_order_and_one_lot(scenario):
    assert scenario.scenario_id == "normal-afternoon"
    assert scenario.mode == "synthetic" and scenario.synthetic
    assert scenario.turn_order == ("market", "city", "rural", "eastside", "advocate")
    assert scenario.role_of("market") is Role.DONOR
    assert scenario.role_of("advocate") is Role.ADVOCATE
    assert [o.lot_id for o in scenario.offers] == ["lot-market-1013"]
    assert scenario.humans["eastside"].decision == "approve" and scenario.humans["eastside"].after_minutes == 15
    assert "advocate" not in scenario.humans


def test_a_food_bank_gets_only_its_own_facts_and_its_households_only_as_counts(scenario):
    calc = StandInCalculators()
    rural = facts_for(scenario, "rural", at("12:00"), calc, lot=scenario.offers[0])
    assert isinstance(rural, FoodBankFacts) and rural.food_bank_id == "rural"
    assert rural.truck is None
    assert rural.travel_minutes_from_donor == 40
    assert rural.storage[0].cold_free_lb == 50 and rural.storage[0].dry_free_lb == 700
    # K7P4 (4 people, 0 lb), M2Q9 (2, 3 lb), R3T1 (1, 4 lb), B8W2 (6, 0 lb) chose rural.
    d = rural.demand
    assert (d.households, d.people, d.limited_fridge, d.evening_only) == (4, 13, 2, 2)
    # Placeholder table: 12 + (7 - 3) + 0 + 16 = 32 lb below fair share.
    assert d.below_fair_share_lb == 32
    assert calc.calls[-1].name == "fair_share_gap"


def test_no_facts_name_a_household(scenario):
    calc = StandInCalculators()
    codes = [r.request_code for r in scenario.requests]
    for org in scenario.turn_order:
        text = json.dumps(draft_to_dict(initial_draft(scenario, scenario.offers[0], calc))) + repr(
            facts_for(scenario, org, at("12:00"), calc, lot=scenario.offers[0])
        )
        assert not any(code in text for code in codes), org


def test_the_donor_gets_its_own_route_and_drop_off_facts(scenario):
    market = facts_for(scenario, "market", at("12:00"), StandInCalculators(), lot=scenario.offers[0])
    assert isinstance(market, DonorFacts) and market.donor_id == "market"
    assert market.travel_minutes == {"city": 20, "rural": 40, "eastside": 25}
    assert market.drop_off.food_bank_ids == ("rural", "eastside") and not market.drop_off.refrigerated


def test_the_advocate_sees_the_same_counts_for_every_food_bank(scenario):
    calc = StandInCalculators()
    adv = facts_for(scenario, "advocate", at("12:00"), calc, lot=scenario.offers[0])
    assert isinstance(adv, AdvocateFacts)
    gaps = {g.food_bank_id: g for g in adv.gaps}
    assert set(gaps) == {"city", "rural", "eastside"}
    assert gaps["rural"].low_access and not gaps["city"].low_access
    for fb in gaps:
        own = facts_for(scenario, fb, at("12:00"), calc, lot=scenario.offers[0]).demand
        assert (gaps[fb].households, gaps[fb].below_fair_share_lb) == (own.households, own.below_fair_share_lb)


def test_a_cooler_failure_changes_the_food_banks_facts_only_from_its_time(scenario):
    calc = StandInCalculators()
    before = facts_for(scenario, "city", at("15:00"), calc, lot=scenario.offers[0])
    after = facts_for(scenario, "city", at("15:30"), calc, lot=scenario.offers[0])
    assert calc.storage_at(before.storage, at("16:00")).cold_free_lb == 250
    assert calc.storage_at(after.storage, at("15:00")).cold_free_lb == 250
    assert calc.storage_at(after.storage, at("16:00")).cold_free_lb == 0
    assert calc.storage_at(after.storage, at("16:00")).dry_free_lb == 200


def test_the_first_version_is_the_donors_offer_in_pounds_from_the_unit_calculator(scenario):
    calc = StandInCalculators()
    v1 = initial_draft(scenario, scenario.offers[0], calc)
    assert v1.version == 1 and v1.proposer_id == "market" and v1.based_on_version is None
    assert {i.produce_id: i.pounds for i in v1.items} == {"apples": 300, "romaine": 200, "potatoes": 400}
    assert [c.name for c in calc.calls].count("to_pounds") == 3
    assert v1.allocations == () and v1.drop_off_to == ("rural", "eastside") and not v1.drop_off_refrigerated
    assert v1.deadline == at("15:00")
    assert v1.names["city"] == "City food bank"
    assert v1.reason


def test_a_fixture_with_the_wrong_kind_or_contract_version_is_refused():
    for key, value in (("kind", "systems"), ("contract_version", "contract-v9")):
        bad = raw()
        bad[key] = value
        with pytest.raises(ScenarioError):
            load_scenario(bad)


def test_a_fixture_naming_other_policy_versions_than_the_packaged_ones_is_refused():
    for key in ("fair_share_table_version", "produce_profile_set_version"):
        bad = raw()
        bad["policies"][key] = "other"
        with pytest.raises(ScenarioError, match=key):
            load_scenario(bad)


def test_a_request_without_consent_is_refused():
    bad = raw()
    bad["requests"][0]["consent"] = False
    with pytest.raises(ScenarioError, match="consent"):
        load_scenario(bad)


def test_a_turn_order_must_name_every_organization_once():
    bad = raw()
    bad["turn_order"] = ["market", "city", "city", "advocate"]
    with pytest.raises(ScenarioError, match="turn_order"):
        load_scenario(bad)


def test_loading_does_not_change_the_raw_fixture():
    data = raw()
    copied = copy.deepcopy(data)
    load_scenario(data)
    assert data == copied
