"""A whole negotiation of the recorded scenario (#11), through the runner's turn loop (#20).

This used to have its own test-only turn loop. That loop is now ``scenario_runner.negotiate``
(ticket #20): it publishes turns in a fixed order, applies counters as new versions (old
accepts stop counting), records which items a food bank countered down (the advocate reads
that from the shared records), and stops when every named organization has requested its
holds, or after three rounds with no new terms. It never commits anything. Lane A still
owns the real protocol (#7, #8).
"""

import json
from pathlib import Path

from harvestnet_agents.negotiation import MoveKind, Role, parse_agent_input
from harvestnet_agents.rules_negotiators import rules_negotiator
from harvestnet_agents.scenario_runner import EventLog
from harvestnet_agents.scenario_runner import negotiate as run_turns

FIXTURES = Path(__file__).parent / "fixtures" / "negotiators"
ORDER = [("market", Role.DONOR), ("city", Role.FOOD_BANK), ("rural", Role.FOOD_BANK), ("eastside", Role.FOOD_BANK), ("advocate", Role.ADVOCATE)]


def facts_from(name):
    return parse_agent_input(json.loads((FIXTURES / f"{name}.json").read_text()))[1]


def scenario():
    start = facts_from("rural_bids_toward_its_gap_on_produce_it_can_receive")
    facts = {
        "market": facts_from("donor_accepts_plan_before_deadline").facts,
        "city": facts_from("city_accepts_what_its_facts_allow").facts,
        "rural": start.facts,
        "eastside": facts_from("eastside_asks_human_on_condition_doubt").facts,
        "advocate": facts_from("advocate_proposes_unclaimed_pounds_to_the_largest_gap").facts,
    }
    return start.draft, start.turn.now, facts


def negotiate():
    draft, now, facts = scenario()
    log = EventLog()
    result = run_turns(
        draft,
        turn_order=[org for org, _ in ORDER],
        roles=dict(ORDER),
        facts_at=lambda org, _now: facts[org],
        negotiators={org: rules_negotiator(role, org) for org, role in ORDER},
        start=now,
        log=log,
    )
    assert not [e for e in log.events if e["kind"] == "invalid_move"]
    return result.draft, result.moves, result.status


def test_the_recorded_scenario_reaches_holds_by_every_named_organization_with_no_commitment():
    draft, log, outcome = negotiate()
    assert outcome == "held", [m.reason for m in log[-6:]]
    assert all(not m.commits for m in log)
    # The advocate argued but never voted.
    assert {m.kind for m in log if m.role is Role.ADVOCATE} <= {MoveKind.COUNTER, MoveKind.PASS}
    # Every pound has a destination or is visibly unclaimed.
    for item in draft.items:
        assert draft.allocated_lb(item.produce_id) + draft.unallocated_lb(item.produce_id) == item.pounds


def test_the_scenario_outcome_follows_the_facts():
    draft, _, _ = negotiate()
    # Romaine needs a cold chain: only the city food bank, with a refrigerated truck and a walk-in, can take it.
    assert draft.pounds("romaine", "rural") == 0 and draft.pounds("romaine", "eastside") == 0
    assert draft.pounds("romaine", "city") > 0
    # The rural food bank, with the largest gap, ends up with the most produce.
    assert max(("city", "rural", "eastside"), key=draft.planned_lb) == "rural"
    # No food bank goes above its households' gap while another is below it.
    gaps = {"city": 200, "rural": 310, "eastside": 90}
    below = [fb for fb, gap in gaps.items() if draft.planned_lb(fb) < gap]
    above = [fb for fb, gap in gaps.items() if draft.planned_lb(fb) > gap]
    assert not (below and above)
