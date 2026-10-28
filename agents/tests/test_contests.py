"""Food banks contest each other's shares (ADR 0013).

A food bank below fair share, with nothing unclaimed it can receive, contests another food
bank's share; the food bank that loses pounds concedes what is beyond its own gap and may take
back what is within it; the advocate backs whichever side is further below fair share; a
standoff ends as a preserved disagreement. The recorded inputs are the synthetic negotiator
fixtures in tests/fixtures/negotiators/, adjusted per test. Every number is synthetic, and no
test calls the Claude API."""

import copy
import json
from pathlib import Path

import pytest

from harvestnet_agents.calculators import StandInCalculators
from harvestnet_agents.lane_b_rule_checks import run_lane_b_rule_checks
from harvestnet_agents.llm_negotiators import NumberPool, check_move, precompute
from harvestnet_agents.negotiation import (
    AdvocateFacts,
    AgentInput,
    FoodBankGap,
    MoveKind,
    Role,
    SetPounds,
    ShiftPounds,
    Turn,
    food_bank_amendment_problem,
    parse_agent_input,
    parse_facts,
)
from harvestnet_agents.rules_negotiators import RulesAdvocate, RulesFoodBank
from harvestnet_agents.scenario import load_scenario
from harvestnet_agents.scenario_runner import run_scenario

FIXTURES = Path(__file__).parent / "fixtures" / "negotiators"
SCARCE = Path(__file__).parents[2] / "core_fixtures" / "more-households-than-produce.json"


def city_input(below_fair_share_lb=300, dry_free_lb=300, unclaimed_apples_lb=0):
    """City holds 200 lb romaine; rural 250 lb apples and 400 lb potatoes; eastside 50 lb apples.
    Every pound is allocated unless ``unclaimed_apples_lb`` is taken off rural's apples."""
    raw = json.loads((FIXTURES / "city_accepts_what_its_facts_allow.json").read_text())
    raw["facts"]["demand"]["below_fair_share_lb"] = below_fair_share_lb
    raw["facts"]["storage"][0]["dry_free_lb"] = dry_free_lb
    raw["draft"]["allocations"][1]["pounds"] -= unclaimed_apples_lb
    return parse_agent_input(raw)[1]


RURAL_FACTS = {
    "food_bank_id": "rural", "name": "Rural food bank",
    "storage": [{"window": {"start": "2026-10-13T12:00", "end": "2026-10-13T23:59"}, "cold_free_lb": 0, "dry_free_lb": 900}],
    "pickup_windows": [{"start": "2026-10-13T16:00", "end": "2026-10-13T18:00"}],
    "truck": None, "travel_minutes_from_donor": 40,
    "demand": {"households": 50, "people": 150, "below_fair_share_lb": 640},
}


def rural_input(draft, below_fair_share_lb, number):
    facts = parse_facts(Role.FOOD_BANK, {**RURAL_FACTS, "demand": {**RURAL_FACTS["demand"], "below_fair_share_lb": below_fair_share_lb}})
    return AgentInput(draft, facts, Turn("rural", number, draft.deadline.replace(hour=12, minute=30)))


def contested(city_move, agent_input):
    return agent_input.draft.amend(city_move.amendment, proposer_id="city", reason=city_move.reason)


# --- Contest: shape and limits --------------------------------------------------------------


def test_a_food_bank_below_fair_share_with_nothing_unclaimed_contests_one_item_to_itself():
    agent_input = city_input()  # gap 300, 200 planned: 100 lb below, every pound allocated
    move = RulesFoodBank("city").move(agent_input)
    assert move.kind is MoveKind.COUNTER
    # The shortest-lived item it can receive is apples; rural's 250 lb is the largest other line.
    assert move.amendment == ShiftPounds("apples", "rural", "city", 100)
    assert food_bank_amendment_problem("city", move.amendment) is None
    assert "100 lb below their fair share" in move.reason and "Rural food bank has 250 lb of apples" in move.reason
    assert "contest" in move.reason and "within our fair-share gap" in move.reason
    assert RulesFoodBank("city").counter_problems(agent_input, contested(move, agent_input)) == []


def test_a_contest_is_limited_like_a_bid_by_storage_and_never_passes_the_gap():
    assert RulesFoodBank("city").move(city_input(dry_free_lb=60)).amendment == ShiftPounds("apples", "rural", "city", 60)
    assert RulesFoodBank("city").move(city_input(below_fair_share_lb=230)).amendment == ShiftPounds("apples", "rural", "city", 30)


def test_no_contest_at_fair_share_while_produce_is_unclaimed_or_in_a_baseline():
    assert RulesFoodBank("city").move(city_input(below_fair_share_lb=200)).kind is MoveKind.ACCEPT  # gap met
    bid = RulesFoodBank("city").move(city_input(unclaimed_apples_lb=40))
    assert bid.amendment == SetPounds("apples", "city", 40)  # unclaimed pounds come first

    class Baseline(RulesFoodBank):
        contests = False

    assert Baseline("city").move(city_input()).kind is MoveKind.ACCEPT


# --- Defending: concede beyond the gap, take back within it --------------------------------------


def test_the_food_bank_that_loses_pounds_beyond_its_gap_concedes_them():
    before = city_input()
    after = contested(RulesFoodBank("city").move(before), before)
    rural = RulesFoodBank("rural")
    assert rural.move(rural_input(before.draft, 500, 9)).kind is MoveKind.ACCEPT
    answer = rural.move(rural_input(after, 500, 14))  # 550 lb still planned for a 500 lb gap
    assert answer.kind is MoveKind.ACCEPT
    assert "100 lb of our apples moved to City food bank's share" in answer.reason and "we concede them" in answer.reason


def test_the_food_bank_that_loses_pounds_within_its_gap_takes_them_back_up_to_its_gap():
    before = city_input()
    after = contested(RulesFoodBank("city").move(before), before)
    rural = RulesFoodBank("rural")
    rural.move(rural_input(before.draft, 640, 9))
    first = rural.move(rural_input(after, 640, 14))
    assert first == rural.move(rural_input(after, 640, 14))  # asked twice on one version, the same answer
    assert first.kind is MoveKind.COUNTER
    assert first.amendment == ShiftPounds("apples", "city", "rural", 90)  # 90 lb below: never past its gap
    assert "Since our last turn, 100 lb of our apples moved" in first.reason and "We take back 90 lb" in first.reason
    agent_input = rural_input(after, 640, 14)
    assert rural.counter_problems(agent_input, contested(first, agent_input)) == []


# --- The advocate backs the side further below fair share ---------------------------------------


def advocate_input(city_gap, rural_gap, contests=(("city", "rural", "apples"),)):
    before = city_input()
    after = contested(RulesFoodBank("city").move(before), before)  # city 300 lb planned, rural 550 lb
    facts = AdvocateFacts(gaps=(FoodBankGap("city", "City food bank", 60, city_gap), FoodBankGap("rural", "Rural food bank", 50, rural_gap),
                                FoodBankGap("eastside", "Eastside food bank", 20, 50)), contests=tuple(contests))
    return AgentInput(after, facts, Turn("advocate", 15, after.deadline.replace(hour=12, minute=40)))


def test_the_advocate_backs_the_food_bank_further_below_fair_share_in_a_contest():
    agent_input = advocate_input(city_gap=500, rural_gap=600)  # city 200 lb below, rural 50 lb below
    move = RulesAdvocate().move(agent_input)
    assert move.kind is MoveKind.COUNTER and move.amendment == ShiftPounds("apples", "rural", "city", 150)
    assert "we back City food bank" in move.reason and "Rural food bank answers for its own share" in move.reason
    advocate = RulesAdvocate()
    assert advocate.counter_problems(agent_input, agent_input.draft.amend(move.amendment, proposer_id="advocate", reason=move.reason)) == []
    other_way = agent_input.draft.amend(ShiftPounds("apples", "city", "rural", 50), proposer_id="advocate", reason="x")
    assert any("back the food bank further below fair share" in p for p in advocate.counter_problems(agent_input, other_way))


def test_the_advocate_can_back_the_defender_and_passes_on_no_contest_or_a_tie():
    move = RulesAdvocate().move(advocate_input(city_gap=320, rural_gap=640))  # city 20 lb below, rural 90 lb below
    assert move.amendment == ShiftPounds("apples", "city", "rural", 90)
    assert RulesAdvocate().move(advocate_input(city_gap=320, rural_gap=640, contests=())).kind is MoveKind.PASS
    assert RulesAdvocate().move(advocate_input(city_gap=350, rural_gap=600)).kind is MoveKind.PASS  # both 50 lb below


# --- A standoff is kept, not broken -------------------------------------------------------------


@pytest.fixture(scope="module")
def standoff():
    return run_scenario(load_scenario(SCARCE), StandInCalculators())


def test_a_contest_and_take_back_standoff_ends_as_a_preserved_disagreement_with_both_sides(standoff):
    assert standoff.status == "preserved_disagreement" and standoff.committed_draft is None
    stop = next(e for e in standoff.events if e["kind"] == "stop")
    assert stop["rule"] == "counter_cycle"
    claims = [e for e in standoff.events if e["kind"] == "move" and e["role"] == "food_bank"
              and (e["move"].get("amendment") or {}).get("to_food_bank_id") == e["organization_id"]]
    assert any("We contest" in e["move"]["reason"] for e in claims) and any("We take back" in e["move"]["reason"] for e in claims)
    # The dashboards' data: at least two versions in the cycle with their proposers and reasons, and each side's last word.
    assert len(stop["options"]) >= 2 and all(o["reason"] and o["proposer_id"] for o in stop["options"])
    assert {"city", "rural"} <= {r["organization_id"] for r in stop["reasons"]}
    assert all(r.passed for r in standoff.lane_b_rule_checks.values()), standoff.lane_b_rule_checks


def test_the_advocate_sees_the_recorded_contests_and_backs_a_side(standoff):
    advocate = [e for e in standoff.events if e["kind"] == "move" and e["organization_id"] == "advocate"]
    assert any(e["facts"]["contests"] for e in advocate)
    assert any("we back" in e["move"]["reason"] for e in advocate)


# --- The rule check allows exactly one new shape -------------------------------------------------


def contest_move(events):
    return next(e for e in events if e["kind"] == "move" and "We contest" in e["move"]["reason"])


def failing(events):
    return {n for n, r in run_lane_b_rule_checks(events).items() if not r.passed}


def test_the_rule_check_accepts_a_contest_and_refuses_every_other_shape_on_another_share(standoff):
    assert "no_central_decider" not in failing(standoff.events)
    between_others = copy.deepcopy(standoff.events)
    contest_move(between_others)["move"]["amendment"]["to_food_bank_id"] = "eastside"
    assert "no_central_decider" in failing(between_others)
    set_other = copy.deepcopy(standoff.events)
    m = contest_move(set_other)["move"]
    m["amendment"] = {"kind": "set_pounds", "produce_id": m["amendment"]["produce_id"], "food_bank_id": "rural", "pounds": 0.0}
    assert "no_central_decider" in failing(set_other)
    past_gap = copy.deepcopy(standoff.events)
    contest_move(past_gap)["move"]["amendment"]["pounds"] = 31.0
    problems = run_lane_b_rule_checks(past_gap)["no_central_decider"].failures
    assert any("more than its own remaining fair-share gap" in p for p in problems)


# --- The LLM's contests are checked against the rules limits ------------------------------------


def llm_check(agent_input, amendment, reason):
    calc = StandInCalculators()
    pool = NumberPool()
    pool.add(agent_input)
    pool.add(precompute(Role.FOOD_BANK, agent_input, calc))
    rules = RulesFoodBank("city", calc)
    raw = {"kind": "counter", "reason": reason, "amendment": {
        "kind": amendment[0], "produce_id": "apples", "food_bank_id": amendment[1], "from_food_bank_id": amendment[2],
        "to_food_bank_id": amendment[3], "pounds": amendment[4], "mover": None, "departs_at": None, "arrives_at": None}}
    return check_move(raw, Role.FOOD_BANK, agent_input, pool, rules.review, rules.counter_problems)


def test_the_llm_check_accepts_a_valid_contest_and_refuses_invalid_ones():
    why = "Our 60 households are 100 lb below their fair share this week. We contest 100 lb of Rural food bank's apples."
    move, problems = llm_check(city_input(), ("shift_pounds", None, "rural", "city", 100), why)
    assert problems == [] and move.amendment == ShiftPounds("apples", "rural", "city", 100)
    # Past its gap (200 lb would leave it 100 lb beyond fair share).
    _, problems = llm_check(city_input(), ("shift_pounds", None, "rural", "city", 200), "We contest 200 lb of rural's apples.")
    assert any("no further than your households' fair-share gap" in p for p in problems)
    # Between two other food banks, or setting another food bank's pounds.
    _, problems = llm_check(city_input(), ("shift_pounds", None, "rural", "eastside", 50), "Moving 50 lb of apples to eastside.")
    assert any("only to your own share" in p for p in problems)
    _, problems = llm_check(city_input(), ("set_pounds", "rural", None, None, 200), "Rural should have 200 lb of apples.")
    assert problems
    # While unclaimed pounds it can receive remain, it asks for those first.
    _, problems = llm_check(city_input(unclaimed_apples_lb=40), ("shift_pounds", None, "eastside", "city", 50), "We contest 50 lb of apples.")
    assert any("is unclaimed and you can receive it" in p for p in problems)
    # At fair share, no contest at all.
    _, problems = llm_check(city_input(below_fair_share_lb=200), ("shift_pounds", None, "rural", "city", 50), "We contest 50 lb of apples.")
    assert any("already have their fair share" in p for p in problems)


# --- Cooler failure: each food bank answers for itself --------------------------------------------


def test_each_food_bank_answers_a_cold_space_request_from_its_own_facts_only():
    agent_input = city_input()
    answer = RulesFoodBank("city").answer_cold_space_request(agent_input.facts, agent_input.draft, agent_input.turn.now)
    assert (answer.food_bank_id, answer.cold_space_lb) == ("city", 50)  # 250 lb cold free, 200 lb romaine committed
    from harvestnet_agents.rules_negotiators import TurnError
    with pytest.raises(TurnError):
        RulesFoodBank("rural").answer_cold_space_request(agent_input.facts, agent_input.draft, agent_input.turn.now)


def test_in_the_runner_each_candidate_answers_for_itself_and_the_failed_food_bank_chooses():
    run = run_scenario(load_scenario(Path(__file__).parents[2] / "core_fixtures" / "cooler-failure.json"), StandInCalculators())
    assessment = next(e for e in run.events if e["kind"] == "cooler_failure_assessment")
    failed = assessment["food_bank_id"]
    answers = {a["food_bank_id"]: a for a in assessment["answers"]}
    assert failed not in answers and answers and all(a["answered_by"] == fb for fb, a in answers.items())
    calls = [e for e in run.events if e["kind"] == "calculator_call" and e["seq"] in assessment["calculator_call_seqs"]]
    # Each answer's storage reading is made by that food bank's own agent, never by the failed one.
    assert {e["actor"] for e in calls if e["calculator"] == "storage_at"} == set(answers)
    assert {c["food_bank_id"] for c in assessment["reason_cards"]} == set(answers)
    assert assessment["proposal"] is None or assessment["proposal"]["committed"] is False
