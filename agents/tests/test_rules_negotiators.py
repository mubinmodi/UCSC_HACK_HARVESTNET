"""Rules-based negotiators (#11).

Each recorded input in tests/fixtures/negotiators/ is a synthetic stand-in for one of
contract day's example input/output pairs (ticket #1 is not done): a draft version, one
organization's specialists' facts, and its turn, plus the expected move.
"""

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from harvestnet_agents.llm_negotiators import NumberPool, check_move
from harvestnet_agents.negotiation import (
    ADVOCATE_MOVES,
    AdvocateCannotVote,
    Move,
    MoveKind,
    Role,
    amendment_from_dict,
    parse_agent_input,
)
from harvestnet_agents.rules_negotiators import (
    RulesAdvocate,
    RulesDonor,
    RulesFoodBank,
    TurnError,
    rules_negotiator,
)

FIXTURES = Path(__file__).parent / "fixtures" / "negotiators"
NAMES = sorted(p.stem for p in FIXTURES.glob("*.json"))


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def run(name):
    raw = load(name)
    role, agent_input = parse_agent_input(raw)
    negotiator = rules_negotiator(role, agent_input.turn.organization_id)
    return raw, agent_input, negotiator.move(agent_input)


def by_prefix(prefix):
    return [n for n in NAMES if n.startswith(prefix)]


def test_fixtures_cover_every_role():
    assert by_prefix("donor_") and by_prefix("advocate_")
    assert by_prefix("city_") and by_prefix("rural_") and by_prefix("eastside_")


@pytest.mark.parametrize("name", NAMES)
def test_recorded_input_gives_the_expected_move(name):
    raw, agent_input, move = run(name)
    expected = raw["expected"]
    assert move.kind == MoveKind(expected["kind"]), move.reason
    if "amendment" in expected:
        assert move.amendment == amendment_from_dict(expected["amendment"])
    else:
        assert move.amendment is None
    if "holds" in expected:
        assert [(h.resource, h.pounds) for h in move.holds] == [(h["resource"], h["pounds"]) for h in expected["holds"]]
    for words in expected.get("reason_includes", []):
        assert words in move.reason, f"{words!r} missing from: {move.reason}"


@pytest.mark.parametrize("name", NAMES)
def test_every_move_has_a_reason_names_the_current_version_and_commits_nothing(name):
    _, agent_input, move = run(name)
    assert move.reason.strip()
    assert move.version == agent_input.draft.version
    assert move.organization_id == agent_input.turn.organization_id
    assert move.commits is False


@pytest.mark.parametrize("name", NAMES)
def test_a_counter_always_applies_cleanly_as_one_new_version(name):
    _, agent_input, move = run(name)
    if move.kind is MoveKind.COUNTER:
        next_version = agent_input.draft.amend(move.amendment, proposer_id=move.organization_id, reason=move.reason)
        assert next_version.version == agent_input.draft.version + 1


# --- Donor ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", by_prefix("donor_"))
def test_the_donor_only_accepts_plans_that_leave_before_its_deadline(name):
    _, agent_input, move = run(name)
    if move.kind is MoveKind.ACCEPT:
        assert all(tr.departs_at <= agent_input.draft.deadline for tr in agent_input.draft.transports)


@pytest.mark.parametrize("name", by_prefix("donor_"))
def test_the_donor_never_offers_a_drop_off_beyond_its_ability(name):
    _, agent_input, move = run(name)
    a = move.amendment
    if move.kind is MoveKind.COUNTER and getattr(a, "kind", None) == "set_transport" and a.mover == "donor":
        drop = agent_input.facts.drop_off
        assert drop is not None and a.food_bank_id in drop.food_bank_ids
        assert drop.window.contains(a.departs_at) and a.departs_at <= agent_input.draft.deadline
        assert drop.window.contains(a.arrives_at)  # the whole trip fits the vehicle's window
        assert agent_input.draft.planned_lb(a.food_bank_id) <= drop.capacity_lb


def test_a_drop_off_leaving_in_the_window_but_arriving_after_it_is_retimed():
    # The van is free 1 to 2 pm. Leaving at 2 pm, the 40-minute trip to rural ends at 2:40 pm,
    # after the van's window, so the donor offers to leave at 1 pm instead (#20: the harness
    # checks the whole trip against the window, as it does for a food bank's truck).
    raw = load("donor_retimes_a_drop_off_into_its_window")
    raw["draft"]["transports"][0].update(departs_at="2026-10-13T14:00", arrives_at="2026-10-13T14:40")
    role, agent_input = parse_agent_input(raw)
    move = rules_negotiator(role, agent_input.turn.organization_id).move(agent_input)
    assert move.kind is MoveKind.COUNTER, move.reason
    assert move.amendment == amendment_from_dict(raw["expected"]["amendment"])
    assert "2:40 pm" in move.reason and "2 pm" in move.reason


# --- Advocate ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_the_advocate_never_accepts_rejects_or_vetoes(name):
    raw, agent_input, move = run(name)
    if raw["role"] == "advocate":
        assert move.kind in ADVOCATE_MOVES


def test_the_advocate_cannot_be_made_to_vote_even_by_a_buggy_policy():
    with pytest.raises(AdvocateCannotVote):
        Move("advocate", Role.ADVOCATE, 3, MoveKind.ACCEPT, reason="looks fair")
    with pytest.raises(AdvocateCannotVote):
        Move("advocate", Role.ADVOCATE, 3, MoveKind.REJECT, reason="veto")


def test_the_advocate_has_no_accept_or_reject_methods():
    advocate = RulesAdvocate()
    for name in ("accept", "reject", "veto", "request_hold"):
        assert not hasattr(advocate, name)


# --- Turn checks ------------------------------------------------------------------------


def test_a_negotiator_only_moves_on_its_own_turn():
    _, agent_input = parse_agent_input(load("city_accepts_what_its_facts_allow"))
    with pytest.raises(TurnError):
        RulesFoodBank("rural").move(agent_input)


def test_a_negotiator_only_reads_its_own_facts():
    raw = load("city_accepts_what_its_facts_allow")
    raw["turn"]["organization_id"] = "rural"
    _, agent_input = parse_agent_input(raw)
    with pytest.raises(TurnError):
        RulesFoodBank("rural").move(agent_input)


def test_rules_negotiator_builds_the_right_policy_for_each_role():
    assert isinstance(rules_negotiator(Role.DONOR, "market"), RulesDonor)
    assert isinstance(rules_negotiator(Role.FOOD_BANK, "city"), RulesFoodBank)
    assert isinstance(rules_negotiator(Role.ADVOCATE, "advocate"), RulesAdvocate)


def test_moves_are_deterministic():
    first = [run(n)[2] for n in NAMES]
    second = [run(n)[2] for n in NAMES]
    assert first == second


def test_fixture_times_are_synthetic_and_on_the_scenario_day():
    for n in NAMES:
        raw = load(n)
        assert "Synthetic" in raw["_note"]
        assert datetime.fromisoformat(raw["turn"]["now"]).date().isoformat() == "2026-10-13"


# --- Beyond fair share (user direction, October 11, 2026) ---------------------------------

BEYOND = "eastside_bids_beyond_fair_share_once_its_households_have_it"
FAR_PICKUP = [{"start": "2026-11-05T17:00", "end": "2026-11-05T20:00"}]
LONG_STORAGE = [{"window": {"start": "2026-10-13T12:00", "end": "2026-11-06T00:00"}, "cold_free_lb": 150, "dry_free_lb": 200}]


def eastside_raw(below_fair_share_lb=None, storage=None, pickup_windows=None, usable_until=None):
    """The beyond-fair-share fixture's input, with some facts or items changed."""
    raw = load(BEYOND)
    if below_fair_share_lb is not None:
        raw["facts"]["demand"]["below_fair_share_lb"] = below_fair_share_lb
    if storage is not None:
        raw["facts"]["storage"] = storage
    if pickup_windows is not None:
        raw["facts"]["pickup_windows"] = pickup_windows
    for item in raw["draft"]["items"]:
        item["usable_until"] = (usable_until or {}).get(item["produce_id"], item["usable_until"])
    return raw


def next_turn(agent_input, move):
    draft = agent_input.draft.amend(move.amendment, proposer_id=move.organization_id, reason=move.reason)
    return replace(agent_input, draft=draft, turn=replace(agent_input.turn, number=agent_input.turn.number + 1))


def set_pounds(produce_id, food_bank_id, pounds):
    return amendment_from_dict({"kind": "set_pounds", "produce_id": produce_id, "food_bank_id": food_bank_id, "pounds": pounds})


def test_a_food_bank_bids_toward_its_gap_first_and_beyond_fair_share_only_after():
    eastside = RulesFoodBank("eastside")
    _, first_input = parse_agent_input(eastside_raw(below_fair_share_lb=50))
    first = eastside.move(first_input)
    # Toward fair share: it stops at the 50 lb gap, though 200 lb of dry space is free.
    assert first.amendment == set_pounds("apples", "eastside", 50)
    assert "beyond fair share" not in first.reason and "50 lb below their fair share" in first.reason
    after_first = next_turn(first_input, first)
    transport = eastside.move(after_first)  # it settles who moves its share before bidding again
    assert transport.amendment.kind == "set_transport"
    second = eastside.move(next_turn(after_first, transport))
    # Its gap is planned, so the next bid goes beyond fair share, up to its dry space.
    assert second.kind is MoveKind.COUNTER and "beyond fair share" in second.reason
    assert second.amendment == set_pounds("apples", "eastside", 200)
    assert "50 lb fair-share gap is already planned" in second.reason


def test_a_bid_beyond_fair_share_never_exceeds_storage_while_the_produce_waits_for_pickup():
    # Dry space shrinks to 60 lb at 7 pm, before pickup ends at 8 pm, so 60 lb is all it can hold until then.
    storage = [
        {"window": {"start": "2026-10-13T12:00", "end": "2026-10-13T19:00"}, "cold_free_lb": 150, "dry_free_lb": 200},
        {"window": {"start": "2026-10-13T19:00", "end": "2026-10-13T23:59"}, "cold_free_lb": 150, "dry_free_lb": 60},
    ]
    _, agent_input = parse_agent_input(eastside_raw(storage=storage))
    move = RulesFoodBank("eastside").move(agent_input)
    assert move.amendment == set_pounds("apples", "eastside", 60) and "beyond fair share" in move.reason


def test_no_bid_beyond_fair_share_for_produce_its_profile_says_spoils_before_households_collect():
    # Pickup is weeks away. The donor's dates say apples and potatoes both last, but the produce profiles
    # keep apples 21 days at room temperature (dry storage here) and potatoes 30. No crop names in the rule.
    _, agent_input = parse_agent_input(eastside_raw(
        pickup_windows=FAR_PICKUP, storage=LONG_STORAGE, usable_until={"apples": "2026-11-20T00:00", "potatoes": "2026-11-20T00:00"}))
    move = RulesFoodBank("eastside").move(agent_input)
    assert move.amendment == set_pounds("potatoes", "eastside", 200), move.reason
    assert "beyond fair share" in move.reason


def test_a_share_its_profile_says_spoils_before_pickup_is_removed_and_the_llm_cannot_accept_it():
    raw = eastside_raw(pickup_windows=FAR_PICKUP, storage=LONG_STORAGE, usable_until={"apples": "2026-11-20T00:00"})
    raw["draft"]["allocations"] = [{"produce_id": "apples", "food_bank_id": "eastside", "pounds": 100}]
    raw["draft"]["transports"] = [{"food_bank_id": "eastside", "mover": "donor", "departs_at": "2026-10-13T15:00",
                                   "arrives_at": "2026-10-13T15:25"}]
    _, agent_input = parse_agent_input(raw)
    eastside = RulesFoodBank("eastside")
    assert [p.code for p in eastside.review(agent_input)] == ["spoils_in_storage"]
    assert eastside.move(agent_input).amendment == set_pounds("apples", "eastside", 0)
    # The LLM negotiator's accept gate is the same review, so an LLM can't accept this share either.
    accept = {"kind": "accept", "reason": "Version 1 fits our facts.", "amendment": None, "holds": None}
    move, problems = check_move(accept, Role.FOOD_BANK, agent_input, NumberPool(), eastside.review)
    assert move is None and any("can't accept" in p for p in problems)


def test_an_llm_counter_past_the_gap_must_say_beyond_fair_share():
    raw = load(BEYOND)
    _, agent_input = parse_agent_input(raw)
    pool = NumberPool()
    pool.add(raw["facts"])
    pool.add(raw["draft"])
    amendment = {"kind": "set_pounds", "produce_id": "apples", "food_bank_id": "eastside", "pounds": 200, "from_food_bank_id": None,
                 "to_food_bank_id": None, "mover": None, "departs_at": None, "arrives_at": None}
    unlabeled = {"kind": "counter", "reason": "We have 200 lb of dry space, so we ask for 200 lb of apples.", "amendment": amendment,
                 "holds": None}
    move, problems = check_move(unlabeled, Role.FOOD_BANK, agent_input, pool, RulesFoodBank("eastside").review)
    assert move is None and any("beyond fair share" in p for p in problems)
    labeled = {**unlabeled, "reason": "We have 200 lb of dry space, so we ask for 200 lb of apples beyond fair share."}
    move, problems = check_move(labeled, Role.FOOD_BANK, agent_input, pool, RulesFoodBank("eastside").review)
    assert move is not None, problems


def test_the_contracts_move_examples_still_come_from_the_negotiators_unchanged():
    examples = Path(__file__).parents[2] / "docs" / "contracts" / "examples" / "agent-moves.json"
    for pair in json.loads(examples.read_text())["pairs"]:
        role, agent_input = parse_agent_input(pair["input"])
        assert rules_negotiator(role, agent_input.turn.organization_id).move(agent_input).to_dict() == pair["output"], pair["name"]
