"""A whole negotiation of the recorded scenario, with a **test-only** turn loop (#11).

Lane A owns the real protocol (turn order, versions, holds, approvals, stop rules; ticket
#8). This loop is a minimal stand-in so the negotiators can be checked together: it
publishes turns in a fixed order, applies counters as new versions (old accepts stop
counting), records which items a food bank countered down (the advocate reads that from
the shared records), and stops when every named organization has requested its holds,
or after three rounds with no new terms. It never commits anything.
"""

import json
from dataclasses import replace
from pathlib import Path

from harvestnet_agents.negotiation import (
    AdvocateFacts,
    AgentInput,
    MoveKind,
    Role,
    SetPounds,
    Turn,
    parse_agent_input,
)
from harvestnet_agents.rules_negotiators import rules_negotiator

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


def negotiate(max_moves=60):
    draft, now, facts = scenario()
    accepted, held, declined, log = set(), set(), set(), []
    rounds_without_change = 0
    turn_number = 0
    while turn_number < max_moves:
        changed = False
        for org, role in ORDER:
            turn_number += 1
            org_facts = facts[org]
            if isinstance(org_facts, AdvocateFacts):
                org_facts = replace(org_facts, declined=tuple(sorted(declined)))
            move = rules_negotiator(role, org).move(AgentInput(draft, org_facts, Turn(org, turn_number, now, tuple(sorted(accepted)))))
            log.append(move)
            assert move.version == draft.version and not move.commits
            if move.kind is MoveKind.COUNTER:
                a = move.amendment
                if isinstance(a, SetPounds) and a.food_bank_id == org and a.pounds < draft.pounds(a.produce_id, org):
                    declined.add((org, a.produce_id))
                draft = draft.amend(a, proposer_id=org, reason=move.reason)
                accepted, held, changed = set(), set(), True
            elif move.kind is MoveKind.ACCEPT:
                accepted.add(org)
            elif move.kind is MoveKind.REQUEST_HOLD:
                held.add(org)
            elif move.kind in (MoveKind.REJECT, MoveKind.ASK_HUMAN):
                return draft, log, "stopped: " + move.kind.value
            if held and held >= set(draft.named_organizations()):
                return draft, log, "held"
        rounds_without_change = 0 if changed else rounds_without_change + 1
        if rounds_without_change >= 3:
            return draft, log, "preserved disagreement"
    return draft, log, "move limit"


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
