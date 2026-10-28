"""Food banks contest each other's shares, and concede toward need (ADR 0013).

A food bank below fair share, with nothing unclaimed it can receive, contests another food
bank's share and states its claim (its own fair-share gap). The food bank that loses pounds
concedes what is beyond its own gap and takes back only enough to reach its proportional share
of that item, split by the two gaps; the contester accepts the split. The advocate backs the side
below its proportional share. A standoff, kept as a preserved disagreement, now needs a side
that refuses the split. The recorded inputs are the synthetic negotiator fixtures in
tests/fixtures/negotiators/, adjusted per test. Every number is synthetic, and no test calls the
Claude API."""

import copy
import json
from pathlib import Path

import pytest

from harvestnet_agents.calculators import CalculatorError, StandInCalculators, split_in_proportion
from harvestnet_agents.lane_b_rule_checks import run_lane_b_rule_checks
from harvestnet_agents.llm_negotiators import NumberPool, check_move, precompute
from harvestnet_agents.negotiation import (
    AdvocateFacts,
    AgentInput,
    Claim,
    FoodBankGap,
    MoveKind,
    Role,
    SetPounds,
    ShiftPounds,
    Turn,
    amendment_from_dict,
    amendment_to_dict,
    claim_of,
    food_bank_amendment_problem,
    parse_agent_input,
    parse_facts,
)
from harvestnet_agents.rules_negotiators import RulesAdvocate, RulesFoodBank, TurnError, rules_negotiator
from harvestnet_agents.scenario import load_scenario
from harvestnet_agents.scenario_runner import run_scenario

FIXTURES = Path(__file__).parent / "fixtures" / "negotiators"
SCARCE = Path(__file__).parents[2] / "core_fixtures" / "more-households-than-produce.json"


def city_input(below_fair_share_lb=300, dry_free_lb=300, unclaimed_apples_lb=0):
    """City holds 200 lb romaine; rural 250 lb apples; eastside 50 lb apples (the recorded draft,
    without its potatoes, so one item is contested). Every pound is allocated unless
    ``unclaimed_apples_lb`` is taken off rural's apples."""
    raw = json.loads((FIXTURES / "city_accepts_what_its_facts_allow.json").read_text())
    raw["draft"]["items"] = [i for i in raw["draft"]["items"] if i["produce_id"] != "potatoes"]
    raw["draft"]["allocations"] = [a for a in raw["draft"]["allocations"] if a["produce_id"] != "potatoes"]
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


def rural_input(draft, below_fair_share_lb, number, claims=()):
    facts = parse_facts(Role.FOOD_BANK, {**RURAL_FACTS, "demand": {**RURAL_FACTS["demand"], "below_fair_share_lb": below_fair_share_lb}})
    return AgentInput(draft, facts, Turn("rural", number, draft.deadline.replace(hour=12, minute=30)), claims=tuple(claims))


def apply(move, agent_input):
    return agent_input.draft.amend(move.amendment, proposer_id=move.organization_id, reason=move.reason)


def claims_of(*moves_and_drafts):
    """The claims the rules runner would record for these (move, the version it created)."""
    return tuple(c for m, d in moves_and_drafts if (c := claim_of(m.organization_id, m.role, m.amendment, d.version)) is not None)


def first_round(rural_gap=640):
    """City contests rural's apples; returns city, rural, the drafts and the claims so far."""
    city, rural = RulesFoodBank("city"), RulesFoodBank("rural")
    before = city_input()
    rural.move(rural_input(before.draft, rural_gap, 9))  # rural's turn on the version before the contest
    contest = city.move(before)
    after = apply(contest, before)
    return city, rural, before, contest, after, claims_of((contest, after))


# --- The proportional split calculator ----------------------------------------------------------


def test_the_proportional_split_is_in_whole_pounds_and_capped_at_each_gap():
    split = split_in_proportion({"city": 100, "rural": 150}, {"city": 300, "rural": 640})
    # 250 lb at 300 : 640 is 79.79 and 170.21 lb: 79 and 170, and the last pound to the larger remainder.
    assert split.shares_lb == {"city": 80.0, "rural": 170.0} and split.short_lb == {"city": 0.0, "rural": 20.0}
    plenty = split_in_proportion({"a": 90, "b": 10}, {"a": 30, "b": 40})
    assert plenty.shares_lb == {"a": 30.0, "b": 40.0} and plenty.unassigned_lb == 30.0
    assert split_in_proportion({"a": 1, "b": 0}, {"a": 31, "b": 32}).shares_lb == {"a": 0.0, "b": 1.0}  # 0.49 : 0.51 lb
    with pytest.raises(CalculatorError):
        split_in_proportion({"a": 1}, {"b": 1})
    # The core's calculators give the same split (core_tests/test_contests.py).


# --- A contest states its claim; shape and limits ------------------------------------------------


def test_a_food_bank_below_fair_share_with_nothing_unclaimed_contests_and_states_its_claim():
    agent_input = city_input()  # gap 300, 200 planned: 100 lb below, every pound allocated
    move = RulesFoodBank("city").move(agent_input)
    assert move.kind is MoveKind.COUNTER
    # The shortest-lived item it can receive is apples; rural's 250 lb is the largest other line.
    assert move.amendment == ShiftPounds("apples", "rural", "city", 100, claimant_gap_lb=300)
    assert amendment_to_dict(move.amendment)["claimant_gap_lb"] == 300
    assert amendment_from_dict(amendment_to_dict(move.amendment)) == move.amendment
    assert food_bank_amendment_problem("city", move.amendment) is None
    assert "100 lb below their fair share" in move.reason and "Rural food bank has 250 lb of apples" in move.reason
    assert RulesFoodBank("city").counter_problems(agent_input, apply(move, agent_input), amendment=move.amendment) == []


def test_a_contest_is_limited_like_a_bid_by_storage_and_never_passes_the_gap():
    assert RulesFoodBank("city").move(city_input(dry_free_lb=60)).amendment.pounds == 60
    assert RulesFoodBank("city").move(city_input(below_fair_share_lb=230)).amendment.pounds == 30


def test_no_contest_at_fair_share_while_produce_is_unclaimed_or_in_a_baseline():
    assert RulesFoodBank("city").move(city_input(below_fair_share_lb=200)).kind is MoveKind.ACCEPT  # gap met
    assert RulesFoodBank("city").move(city_input(unclaimed_apples_lb=40)).amendment == SetPounds("apples", "city", 40)

    class Baseline(RulesFoodBank):
        contests = False

    assert Baseline("city").move(city_input()).kind is MoveKind.ACCEPT


# --- The defender concedes toward need ----------------------------------------------------------


def test_the_food_bank_that_loses_pounds_beyond_its_gap_concedes_them():
    city, rural, before, contest, after, claims = first_round(rural_gap=120)
    answer = rural.move(rural_input(after, 120, 14, claims))  # 150 lb still planned for a 120 lb gap
    assert answer.kind is MoveKind.ACCEPT
    assert "100 lb of our apples moved to City food bank's share" in answer.reason and "we concede them" in answer.reason


def test_the_defender_takes_back_only_enough_to_reach_its_proportional_share():
    city, rural, before, contest, after, claims = first_round()
    answer = rural.move(rural_input(after, 640, 14, claims))
    assert answer == rural.move(rural_input(after, 640, 14, claims))  # asked twice on one version, the same answer
    # 250 lb of apples between them, split 300 : 640 -> city 80 lb, rural 170 lb; rural holds 150 lb.
    assert answer.amendment == ShiftPounds("apples", "city", "rural", 20, claimant_gap_lb=640)
    assert "states its households are 300 lb below fair share" in answer.reason and "640 lb below" in answer.reason
    assert "our share of the 250 lb of apples we both hold is 170 lb and City food bank's is 80 lb" in answer.reason
    agent_input = rural_input(after, 640, 14, claims)
    assert rural.counter_problems(agent_input, apply(answer, agent_input), amendment=answer.amendment) == []


def test_the_contester_accepts_the_split_and_moves_on_to_a_food_bank_that_has_not_answered():
    city, rural, before, contest, after, claims = first_round()
    answer = rural.move(rural_input(after, 640, 14, claims))
    settled = apply(answer, rural_input(after, 640, 14, claims))
    claims = claims + claims_of((answer, settled))
    city_turn = AgentInput(settled, before.facts, Turn("city", 18, before.turn.now), claims=claims)
    move = city.move(city_turn)
    # City holds its 80 lb proportional share of the apples it shares with rural, so it leaves rural's line alone,
    # and contests eastside, which has stated no gap yet, for its remaining 20 lb.
    assert move.amendment == ShiftPounds("apples", "eastside", "city", 20, claimant_gap_lb=300)


def test_a_contester_whose_pounds_were_taken_past_the_split_contests_once_more_down_to_its_share():
    class Insisting(RulesFoodBank):
        def _short_of_share(self, split, facts, held):  # refuses the split: claims its whole gap
            return facts.demand.below_fair_share_lb

    city, _, before, contest, after, claims = first_round()
    rural = Insisting("rural")
    rural.move(rural_input(before.draft, 640, 9))
    grab = rural.move(rural_input(after, 640, 14, claims))
    assert grab.amendment.pounds == 100  # takes back everything it lost, not its proportional 20 lb
    taken = apply(grab, rural_input(after, 640, 14, claims))
    claims = claims + claims_of((grab, taken))
    again = city.move(AgentInput(taken, before.facts, Turn("city", 18, before.turn.now), claims=claims))
    assert again.amendment == ShiftPounds("apples", "rural", "city", 80, claimant_gap_lb=300)  # back to its 80 lb share, no more
    assert "to our proportional share" in again.reason


# --- The advocate backs the side below its proportional share --------------------------------------


def advocate_input(draft, contests=(("city", "rural", "apples"),)):
    facts = AdvocateFacts(gaps=(FoodBankGap("city", "City food bank", 60, 300), FoodBankGap("rural", "Rural food bank", 50, 640),
                                FoodBankGap("eastside", "Eastside food bank", 20, 50)), contests=tuple(contests))
    return AgentInput(draft, facts, Turn("advocate", 15, draft.deadline.replace(hour=12, minute=40)))


def test_the_advocate_restores_the_proportional_split_for_the_side_below_its_share():
    *_, after, _ = first_round()  # city 100 lb apples, rural 150 lb: rural is below its 170.2 lb share
    agent_input = advocate_input(after)
    move = RulesAdvocate().move(agent_input)
    assert move.kind is MoveKind.COUNTER and move.amendment == ShiftPounds("apples", "city", "rural", 20)
    assert "restores the proportional split" in move.reason and "City food bank answers for its own share" in move.reason
    advocate = RulesAdvocate()
    assert advocate.counter_problems(agent_input, apply(move, agent_input)) == []
    too_far = after.amend(ShiftPounds("apples", "city", "rural", 50), proposer_id="advocate", reason="x")
    wrong_way = after.amend(ShiftPounds("apples", "rural", "city", 20), proposer_id="advocate", reason="x")
    for amended in (too_far, wrong_way):
        assert any("restore the proportional split" in p for p in advocate.counter_problems(agent_input, amended))


def test_the_advocate_passes_on_an_item_already_split_in_proportion_or_with_no_contest():
    *_, after, _ = first_round()
    split = after.amend(ShiftPounds("apples", "city", "rural", 20), proposer_id="rural", reason="x")
    assert RulesAdvocate().move(advocate_input(split)).kind is MoveKind.PASS
    assert RulesAdvocate().move(advocate_input(after, contests=())).kind is MoveKind.PASS


# --- With the rules everywhere, a scarce lot converges instead of deadlocking ------------------------


@pytest.fixture(scope="module")
def scarce():
    return run_scenario(load_scenario(SCARCE), StandInCalculators())


def test_with_more_households_than_produce_contests_converge_to_a_proportional_split(scarce):
    claims = [e for e in scarce.events if e["kind"] == "move" and e["role"] == "food_bank"
              and (e["move"].get("amendment") or {}).get("to_food_bank_id") == e["organization_id"]]
    assert any("We contest" in e["move"]["reason"] for e in claims) and any("We take back" in e["move"]["reason"] for e in claims)
    assert all(e["move"]["amendment"]["claimant_gap_lb"] == e["facts"]["demand"]["below_fair_share_lb"] for e in claims)
    assert not any(e["kind"] == "stop" and e["rule"] == "counter_cycle" for e in scarce.events)
    # Every food bank and the donor hold the same final version, and their humans commit it: no standoff.
    assert scarce.status == "committed"
    assert all(r.passed for r in scarce.lane_b_rule_checks.values()), scarce.lane_b_rule_checks
    # The committed potatoes are split in proportion to the three gaps (31, 32 and 19 lb), in whole pounds.
    potatoes = {a.food_bank_id: a.pounds for a in scarce.committed_draft.allocations if a.produce_id == "potatoes"}
    assert potatoes == split_in_proportion(potatoes, {"city": 31, "rural": 32, "eastside": 19}).shares_lb


def test_the_advocate_sees_the_recorded_contests_and_backs_the_side_below_its_share(scarce):
    advocate = [e for e in scarce.events if e["kind"] == "move" and e["organization_id"] == "advocate"]
    assert any(e["facts"]["contests"] for e in advocate)
    assert any("restores the proportional split" in e["move"]["reason"] for e in advocate)


# --- A standoff still needs a side that refuses the split --------------------------------------------


class InsistingFoodBank(RulesFoodBank):
    """A negotiator (say, an LLM or a staff counter) that refuses the proportional split and
    always claims its whole gap."""

    def _short_of_share(self, split, facts, held):
        return facts.demand.below_fair_share_lb


@pytest.fixture(scope="module")
def standoff():
    def factory(role, org, calc):
        return InsistingFoodBank(org, calc) if org == "rural" else rules_negotiator(role, org, calc)

    return run_scenario(load_scenario(SCARCE), StandInCalculators(), negotiator_factory=factory)


def test_a_side_that_refuses_the_split_ends_in_a_preserved_disagreement_with_both_sides(standoff):
    assert standoff.status == "preserved_disagreement" and standoff.committed_draft is None
    stop = next(e for e in standoff.events if e["kind"] == "stop")
    assert stop["rule"] == "counter_cycle"
    assert len(stop["options"]) >= 2 and all(o["reason"] and o["proposer_id"] for o in stop["options"])
    # Rural keeps claiming more than its share; the food bank it takes from answers with the split each time.
    countering = {r["organization_id"] for r in stop["reasons"] if r["action"] == "counter"}
    assert "rural" in countering and len(countering) >= 2
    assert any("to our proportional share" in r["reason"] for r in stop["reasons"] if r["organization_id"] in countering - {"rural"})


# --- The rule check allows exactly one new shape -------------------------------------------------


def contest_move(events):
    return next(e for e in events if e["kind"] == "move" and "We contest" in e["move"]["reason"])


def failing(events):
    return {n for n, r in run_lane_b_rule_checks(events).items() if not r.passed}


def test_the_rule_check_accepts_a_stated_contest_and_refuses_every_other_shape_on_another_share(scarce):
    assert "no_central_decider" not in failing(scarce.events)
    between_others = copy.deepcopy(scarce.events)
    contest_move(between_others)["move"]["amendment"]["to_food_bank_id"] = "eastside"
    assert "no_central_decider" in failing(between_others)
    set_other = copy.deepcopy(scarce.events)
    m = contest_move(set_other)["move"]
    m["amendment"] = {"kind": "set_pounds", "produce_id": m["amendment"]["produce_id"], "food_bank_id": "rural", "pounds": 0.0}
    assert "no_central_decider" in failing(set_other)
    past_gap = copy.deepcopy(scarce.events)
    contest_move(past_gap)["move"]["amendment"]["pounds"] = 31.0
    assert any("more than its own remaining fair-share gap" in p for p in run_lane_b_rule_checks(past_gap)["no_central_decider"].failures)
    wrong_claim = copy.deepcopy(scarce.events)
    contest_move(wrong_claim)["move"]["amendment"]["claimant_gap_lb"] = 99.0
    assert any("states a 99 lb gap" in p for p in run_lane_b_rule_checks(wrong_claim)["no_central_decider"].failures)


# --- The LLM's contests are checked against the rules limits ------------------------------------


def llm_check(agent_input, kind, food_bank=None, source=None, to=None, pounds=None, claim=None, org="city", split=None):
    calc = StandInCalculators()
    pool = NumberPool()
    pool.add(agent_input)
    pool.add(precompute(Role.FOOD_BANK, agent_input, calc))
    if split is not None:  # the model's proportional_split tool call, as the negotiator records its result
        pool.add(calc.proportional_split(*split), ("proportional_split",))
    rules = RulesFoodBank(org, calc)
    raw = {"kind": "counter", "reason": "Our households' gap is in the facts; we ask within it.", "amendment": {
        "kind": kind, "produce_id": "apples", "food_bank_id": food_bank, "from_food_bank_id": source, "to_food_bank_id": to,
        "pounds": pounds, "mover": None, "departs_at": None, "arrives_at": None, "claimant_gap_lb": claim}}
    return check_move(raw, Role.FOOD_BANK, agent_input, pool, rules.review, rules.counter_problems)


def test_the_llm_check_accepts_a_valid_contest_and_refuses_invalid_ones():
    move, problems = llm_check(city_input(), "shift_pounds", source="rural", to="city", pounds=100, claim=300)
    assert problems == [] and move.amendment == ShiftPounds("apples", "rural", "city", 100, claimant_gap_lb=300)
    cases = [
        (dict(source="rural", to="city", pounds=100, claim=None), "a contest states its claim"),
        (dict(source="rural", to="city", pounds=100, claim=250), "a contest states its claim"),
        (dict(source="rural", to="city", pounds=200, claim=300), "no further than your households' fair-share gap"),
        (dict(source="rural", to="eastside", pounds=50, claim=300), "only to your own share"),
    ]
    for kwargs, words in cases:
        _, problems = llm_check(city_input(), "shift_pounds", **kwargs)
        assert any(words in p for p in problems), (kwargs, problems)
    _, problems = llm_check(city_input(), "set_pounds", food_bank="rural", pounds=200)
    assert problems
    _, problems = llm_check(city_input(unclaimed_apples_lb=40), "shift_pounds", source="eastside", to="city", pounds=50, claim=300)
    assert any("is unclaimed and you can receive it" in p for p in problems)
    _, problems = llm_check(city_input(below_fair_share_lb=200), "shift_pounds", source="rural", to="city", pounds=50, claim=200)
    assert any("already have their fair share" in p for p in problems)


def test_the_llm_check_refuses_claims_above_the_proportional_share_once_a_gap_was_stated():
    *_, after, claims = first_round()
    # Rural takes back more than its proportional 20 lb.
    _, problems = llm_check(rural_input(after, 640, 14, claims), "shift_pounds", source="city", to="rural", pounds=50, claim=640, org="rural")
    assert any("shift at most 20 lb (concede toward need)" in p for p in problems)
    move, problems = llm_check(rural_input(after, 640, 14, claims), "shift_pounds", source="city", to="rural", pounds=20, claim=640,
                               org="rural", split=({"city": 100, "rural": 150}, {"city": 300, "rural": 640}))
    assert problems == [], problems
    # City, once rural stated its gap and holds its share, can't contest rural's apples again.
    settled = after.amend(ShiftPounds("apples", "city", "rural", 20, claimant_gap_lb=640), proposer_id="rural", reason="x")
    stated = claims + (Claim("rural", "city", "apples", 640, settled.version),)
    city_turn = AgentInput(settled, city_input().facts, city_input().turn, claims=stated)
    _, problems = llm_check(city_turn, "shift_pounds", source="rural", to="city", pounds=10, claim=300)
    assert any("shift at most 0 lb (concede toward need)" in p for p in problems)


# --- Cooler failure: each food bank answers for itself --------------------------------------------


def test_each_food_bank_answers_a_cold_space_request_from_its_own_facts_only():
    agent_input = city_input()
    answer = RulesFoodBank("city").answer_cold_space_request(agent_input.facts, agent_input.draft, agent_input.turn.now)
    assert (answer.food_bank_id, answer.cold_space_lb) == ("city", 50)  # 250 lb cold free, 200 lb romaine committed
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
