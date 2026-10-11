"""Rules-based negotiators (#11).

Each recorded input in tests/fixtures/negotiators/ is a synthetic stand-in for one of
contract day's example input/output pairs (ticket #1 is not done): a draft version, one
organization's specialists' facts, and its turn, plus the expected move.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

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
        assert agent_input.draft.planned_lb(a.food_bank_id) <= drop.capacity_lb


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
