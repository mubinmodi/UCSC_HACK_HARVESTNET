"""Produce profiles (ticket #12): demo items, every field sourced or labeled an assumption, versioned."""

import copy
import json
from importlib import resources

import pytest

from harvestnet_agents.profiles import (
    PROFILE_FIELDS,
    ProfileDataError,
    UnitConversionError,
    load_profiles,
    to_pounds,
)

DEMO_ITEMS = ("apples", "romaine", "potatoes", "tomatoes")


def packaged_data():
    return json.loads(resources.files("harvestnet_agents").joinpath("data", "produce_profiles.json").read_text())


def test_demo_items_have_profiles():
    profiles = load_profiles()
    for item in DEMO_ITEMS:
        assert item in profiles


def test_profile_set_is_versioned():
    profiles = load_profiles()
    assert profiles.version
    assert profiles.get("romaine").profile_set_version == profiles.version


def test_every_field_has_a_source_or_an_assumption():
    profiles = load_profiles()
    for item in DEMO_ITEMS:
        profile = profiles.get(item)
        for field in PROFILE_FIELDS:
            provenance = profile.provenance[field]
            assert bool(provenance.sources) != bool(provenance.assumption), (item, field)
            for source_id in provenance.sources:
                assert source_id in profiles.sources


def test_every_cited_source_has_a_url_and_access_date():
    for source in load_profiles().sources.values():
        assert source.url.startswith("https://")
        assert source.accessed
        assert source.title


def test_fridge_needs_match_the_cited_sources():
    profiles = load_profiles()
    assert profiles.get("romaine").needs_fridge is True
    assert profiles.get("apples").needs_fridge is False
    assert profiles.get("potatoes").needs_fridge is False
    assert profiles.get("tomatoes").needs_fridge is False


def test_needs_cold_reads_profile_fields():
    profiles = load_profiles()
    assert profiles.get("romaine").needs_cold is True
    assert profiles.get("apples").needs_cold is False
    assert profiles.get("potatoes").needs_cold is False
    assert profiles.get("tomatoes").needs_cold is False


def test_days_usable_from_cited_sources():
    profiles = load_profiles()
    romaine = profiles.get("romaine")
    assert (romaine.days_usable_cold.min, romaine.days_usable_cold.max) == (7, 14)
    assert (romaine.days_usable_room.min, romaine.days_usable_room.max) == (1, 2)
    apples = profiles.get("apples")
    assert (apples.days_usable_cold.min, apples.days_usable_cold.max) == (28, 42)
    assert (apples.days_usable_room.min, apples.days_usable_room.max) == (21, 21)
    # Tomatoes: refrigeration not recommended, so no cold life is given.
    assert profiles.get("tomatoes").days_usable_cold is None


def test_tomatoes_are_chilling_sensitive():
    tomatoes = load_profiles().get("tomatoes")
    assert tomatoes.transport.chilling_injury_below_c == 10
    assert tomatoes.transport.cold_required is False


def test_condition_grades_and_units():
    romaine = load_profiles().get("romaine")
    assert romaine.condition_grades == ("good", "use_soon", "not_for_people")
    assert set(romaine.units) == {"lb", "case"}
    assert set(load_profiles().get("potatoes").units) == {"lb", "sack"}


def test_to_pounds_converts_pounds_and_needs_a_stated_pack_weight():
    romaine = load_profiles().get("romaine")
    assert to_pounds(romaine, 200, "lb") == 200
    # Case weights vary by pack, so the profile holds none; the donor states it.
    with pytest.raises(UnitConversionError):
        to_pounds(romaine, 5, "case")
    assert to_pounds(romaine, 5, "case", lb_per_unit=40) == 200
    with pytest.raises(UnitConversionError):
        to_pounds(romaine, 5, "sack", lb_per_unit=50)
    with pytest.raises(UnitConversionError):
        to_pounds(romaine, -1, "lb")


def test_unknown_item_is_reported_not_assumed():
    profiles = load_profiles()
    assert "kale" not in profiles
    with pytest.raises(KeyError):
        profiles.get("kale")


def test_field_without_source_or_assumption_is_rejected():
    data = packaged_data()
    romaine = next(p for p in data["profiles"] if p["id"] == "romaine")
    romaine["needs_fridge"].pop("sources")
    with pytest.raises(ProfileDataError):
        load_profiles(data)


def test_field_with_unknown_source_is_rejected():
    data = packaged_data()
    romaine = next(p for p in data["profiles"] if p["id"] == "romaine")
    romaine["needs_fridge"]["sources"] = ["made-up-source"]
    with pytest.raises(ProfileDataError):
        load_profiles(data)


def test_field_with_both_source_and_assumption_is_rejected():
    data = packaged_data()
    romaine = next(p for p in data["profiles"] if p["id"] == "romaine")
    romaine["needs_fridge"]["assumption"] = "also assumed"
    with pytest.raises(ProfileDataError):
        load_profiles(data)


def test_missing_version_is_rejected():
    data = copy.deepcopy(packaged_data())
    data.pop("version")
    with pytest.raises(ProfileDataError):
        load_profiles(data)


def test_one_storage_resource_and_one_must_move_rule_come_from_the_profile():
    profiles = load_profiles()
    for profile in profiles:
        assert profile.storage_resource == ("storage_cold" if profile.needs_cold else "storage_dry")
        assert profile.moves_when_cooler_fails is profile.needs_cold
        assert profiles.must_move(profile.id) is profile.needs_cold
        assert profiles.can_stay(profile.id) is (not profile.needs_cold)
    assert profiles.get("romaine").storage_resource == "storage_cold"
    assert profiles.get("apples").storage_resource == "storage_dry"
    # An item with no profile neither must move nor may stay: a human decides.
    assert not profiles.must_move("mystery") and not profiles.can_stay("mystery")
