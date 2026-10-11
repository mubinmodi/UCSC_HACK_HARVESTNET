"""The contract's scenario, run end to end with the real rules-based negotiators (#20).

The runner takes any ``Calculators`` implementation. These unit tests pass the stand-ins
explicitly; the harness join (``core_tests/test_join.py``) runs it with Lane A's real
calculators. Every number is synthetic. No test calls the Claude API."""

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from harvestnet_agents.calculators import CalculatorError, HouseholdBalance, StandInCalculators
from harvestnet_agents.llm_negotiators import LLMNegotiator, SpendingCap
from harvestnet_agents.negotiation import Role, StorageSlot, TimeWindow, amendment_from_dict, parse_draft, parse_facts
from harvestnet_agents.rules_negotiators import rules_negotiator
from harvestnet_agents.scenario import load_scenario
from harvestnet_agents.scenario_runner import (
    FIXTURE_CHECKS_IN_HARNESS,
    LANE_A_PENDING,
    EventLog,
    RecordedCalculators,
    llm_negotiators_for,
    run_scenario,
)

CONTRACT_EXAMPLE = Path(__file__).parents[2] / "docs" / "contracts" / "examples" / "scenario-normal-afternoon.json"


def raw():
    return json.loads(CONTRACT_EXAMPLE.read_text())


def events(run, kind):
    return [e for e in run.events if e["kind"] == kind]


@pytest.fixture(scope="module")
def normal():
    return run_scenario(load_scenario(CONTRACT_EXAMPLE), StandInCalculators())


# --- The normal afternoon -----------------------------------------------------------------


def test_the_normal_afternoon_runs_end_to_end_to_a_commitment(normal):
    assert normal.status == "committed", [e for e in normal.events if e["kind"] == "stop"]
    commitment = events(normal, "commitment")
    assert len(commitment) == 1 and commitment[0]["version"] == normal.committed_version
    assert not events(normal, "invalid_move")


def test_every_lane_b_rule_check_passes_on_the_normal_afternoon(normal):
    failed = {name: r.failures for name, r in normal.lane_b_rule_checks.items() if not r.passed}
    assert not failed
    assert set(normal.rule_checks()) >= {
        "no_central_decider",
        "every_move_has_reason",
        "advocate_never_votes",
        "numbers_trace_to_inputs",
        "commits_only_with_every_named_approval",
        "cold_dependent_produce_follows_profiles",
    }
    assert all(normal.rule_checks().values())


def test_the_fixtures_own_rule_checks_are_left_to_lane_as_harness_never_faked(normal):
    assert set(normal.fixture_rule_checks) == set(raw()["rule_checks"])
    assert all(v == FIXTURE_CHECKS_IN_HARNESS for v in normal.fixture_rule_checks.values())
    assert LANE_A_PENDING == FIXTURE_CHECKS_IN_HARNESS
    assert "pending" not in FIXTURE_CHECKS_IN_HARNESS


def test_the_runner_never_picks_the_stand_ins_silently():
    with pytest.raises(TypeError):
        run_scenario(load_scenario(CONTRACT_EXAMPLE))
    with pytest.raises(TypeError):
        run_scenario(load_scenario(CONTRACT_EXAMPLE), None)


def test_the_commitment_needs_every_named_organizations_human_on_that_exact_version(normal):
    commit = events(normal, "commitment")[0]
    version = next(e for e in events(normal, "version") if e["version"] == commit["version"])
    approvals = [e for e in events(normal, "approval") if e["version"] == commit["version"]]
    assert sorted(a["organization_id"] for a in approvals) == sorted(version["named_organizations"])
    assert all(a["decision"] == "approve" and a["terms_hash"] == version["terms_hash"] for a in approvals)
    assert all(a["source"] == "scripted_human" for a in approvals)
    assert commit["seq"] > max(a["seq"] for a in approvals)
    # The last approval (eastside, after 15 minutes) is when it commits, before the 3 pm deadline.
    assert commit["at"] == max(a["at"] for a in approvals)
    assert commit["at"] < raw()["surplus_offers"][0]["deadline"]


def test_no_move_commits_and_every_hold_is_the_movers_own_on_the_current_version(normal):
    for m in events(normal, "move"):
        assert m["commits"] is False
    for h in events(normal, "hold"):
        assert h["owner_id"] == h["organization_id"]
    holds = {h["organization_id"] for h in events(normal, "hold") if h["version"] == normal.committed_version}
    version = next(e for e in events(normal, "version") if e["version"] == normal.committed_version)
    assert holds == set(version["named_organizations"])


def test_the_advocate_argues_but_never_votes(normal):
    kinds = {m["move"]["action"] for m in events(normal, "move") if m["role"] == "advocate"}
    assert kinds <= {"counter", "pass"}
    assert "advocate" not in {a["organization_id"] for a in events(normal, "approval")}


def test_romaine_goes_only_where_a_cold_chain_and_cold_storage_exist(normal):
    terms = normal.committed_draft
    assert terms.pounds("romaine", "rural") == 0 and terms.pounds("romaine", "eastside") == 0
    assert terms.pounds("romaine", "city") > 0
    assert terms.transport("city").mover.value == "food_bank"  # its refrigerated truck


def test_every_pound_is_allocated_or_visibly_unclaimed(normal):
    for item in normal.outcome["items"]:
        allocated = sum(a["pounds"] for a in item["allocations"])
        assert allocated + item["unclaimed_lb"] == item["pounds"]
        if item["unclaimed_lb"]:
            assert item["unclaimed_reason"]


# --- Beyond fair share (user direction, October 11, 2026) ---------------------------------

# The fair-share gaps the run's facts give (synthetic, placeholder table), before and after the policy change.
GAPS = {"city": 31.0, "rural": 32.0, "eastside": 19.0}
UNCLAIMED_BEFORE_LB = 818.0  # 249 lb apples, 169 lb romaine, 400 lb potatoes, when food banks bid only to their gaps


def own_facts(run, organization_id):
    """The food bank's own facts as of the commitment (before the cooler failure changes them)."""
    commit = events(run, "commitment")[0]["seq"]
    raw = [e["facts"] for e in events(run, "facts") if e["organization_id"] == organization_id and e["seq"] < commit][-1]
    return parse_facts(Role.FOOD_BANK, raw)


def test_food_banks_take_the_surplus_beyond_fair_share_so_much_less_is_unclaimed(normal):
    unclaimed = sum(i["unclaimed_lb"] for i in normal.outcome["items"])
    assert unclaimed < UNCLAIMED_BEFORE_LB / 4
    assert unclaimed == 0  # this run: every pound has a food bank


def test_no_food_bank_takes_more_than_it_can_store_or_hand_out_before_it_spoils(normal):
    calc = StandInCalculators()
    draft = normal.committed_draft
    for fb in draft.named_food_banks():
        facts, tr = own_facts(normal, fb), draft.transport(fb)
        ends = []
        for a in draft.allocations_to(fb):
            check = calc.pickup_feasibility(tr.arrives_at, facts.pickup_windows, draft.item(a.produce_id).usable_until)
            assert check.feasible, (fb, a.produce_id)
            profile = calc.profiles.get(a.produce_id)
            days = profile.days_usable_cold if profile.needs_cold else profile.days_usable_room
            assert days is not None and check.collect.end - tr.arrives_at <= timedelta(days=days.min), (fb, a.produce_id)
            ends.append(check.collect.end)
        for at in (tr.arrives_at, max(ends)):  # storage over time: from arrival until pickup ends
            free = calc.storage_at(facts.storage, at)
            cold = sum(a.pounds for a in draft.allocations_to(fb) if calc.profiles.get(a.produce_id).needs_cold)
            dry = draft.planned_lb(fb) - cold
            assert cold <= free.cold_free_lb and dry <= free.dry_free_lb, (fb, at)
        if tr.mover.value == "food_bank":
            assert draft.planned_lb(fb) <= facts.truck.capacity_lb


def test_bids_toward_fair_share_come_before_bids_beyond_it_and_are_marked(normal):
    bids = [m for m in events(normal, "move")
            if m["role"] == "food_bank" and m["move"]["action"] == "counter" and m["move"]["amendment"]["kind"] == "set_pounds"]
    beyond = [m for m in bids if "beyond fair share" in m["move"]["reason"]]
    toward = [m for m in bids if m not in beyond]
    assert beyond and toward
    assert max(m["seq"] for m in toward) < min(m["seq"] for m in beyond)
    versions = {e["version"]: e for e in events(normal, "version")}
    for m in beyond:
        draft = parse_draft(versions[m["version"]]["terms"])
        # A food bank bids beyond fair share only on a version that already plans its own gap ...
        assert draft.planned_lb(m["organization_id"]) >= m["facts"]["demand"]["below_fair_share_lb"]
    # ... and in this run, the first one comes after every food bank's gap is planned.
    first = parse_draft(versions[beyond[0]["version"]]["terms"])
    assert all(first.planned_lb(fb) >= gap for fb, gap in GAPS.items())
    for m in toward:
        after = parse_draft(versions[m["version"]]["terms"]).amend(
            amendment_from_dict(m["move"]["amendment"]), proposer_id=m["organization_id"], reason="")
        assert after.planned_lb(m["organization_id"]) <= m["facts"]["demand"]["below_fair_share_lb"]


def test_pounds_beyond_fair_share_never_count_toward_it(normal):
    # The fair-share figures every organization sees stay what the households' requests give.
    for e in events(normal, "facts"):
        if e["role"] == "food_bank":
            assert e["facts"]["demand"]["below_fair_share_lb"] == GAPS[e["organization_id"]]
        elif e["role"] == "advocate":
            assert {g["food_bank_id"]: g["below_fair_share_lb"] for g in e["facts"]["gaps"]} == GAPS
    accounting = {f["food_bank_id"]: f for f in normal.outcome["fair_share"]}
    assert set(accounting) == set(GAPS)
    for fb, gap in GAPS.items():
        f = accounting[fb]
        assert f["below_fair_share_lb"] == gap and f["remaining_gap_lb"] == 0
        assert f["planned_lb"] == normal.committed_draft.planned_lb(fb)
        assert f["beyond_fair_share_lb"] == f["planned_lb"] - gap > 0


@pytest.mark.parametrize("capacity_lb", [500, 300])
def test_a_donor_vehicle_too_small_for_the_extra_pounds_gets_them_back_never_fair_share(capacity_lb):
    # Food banks can't see the donor's vehicle, so extra bids can overfill it. The donor asks the truck-less
    # food bank to collect; it takes back pounds beyond fair share instead of asking again and again.
    data = raw()
    data["donors"][0]["drop_off"]["capacity_lb"] = capacity_lb
    run = run_scenario(load_scenario(data), StandInCalculators())
    assert run.status == "committed", events(run, "stop")
    assert all(run.rule_checks().values()), {k: v.failures for k, v in run.lane_b_rule_checks.items()}
    take_backs = [m for m in events(run, "move") if m["role"] == "food_bank" and "take back" in m["move"]["reason"]]
    assert take_backs and all("beyond fair share" in m["move"]["reason"] for m in take_backs)
    draft = run.committed_draft
    assert all(draft.planned_lb(fb) >= gap for fb, gap in GAPS.items())  # fair-share pounds are never taken back
    donor_moved = sum(draft.planned_lb(fb) for fb in draft.named_food_banks() if draft.transport(fb).mover.value == "donor")
    assert donor_moved <= capacity_lb
    assert sum(i["unclaimed_lb"] for i in run.outcome["items"]) < UNCLAIMED_BEFORE_LB


def test_the_cooler_failure_after_commitment_proposes_a_move_awaiting_fresh_approval(normal):
    fault = events(normal, "fault")
    assert [f["fault_kind"] for f in fault] == ["cooler_failure"]
    assessment = events(normal, "cooler_failure_assessment")
    assert len(assessment) == 1
    a = assessment[0]
    assert {i["produce_id"] for i in a["items_to_move"]} == {"romaine"}
    assert a["proposal"]["committed"] is False
    assert a["proposal"]["status"] == "awaiting_receiver_decision"
    assert a["proposal"]["receiving_food_bank_id"] in {"rural", "eastside"}
    assert len(a["reason_cards"]) == 2
    # Nothing else commits after the failure.
    assert len(events(normal, "commitment")) == 1


def test_the_event_log_is_plain_json_with_a_clock_and_sequence(normal):
    text = json.dumps(normal.events)
    assert json.loads(text) == normal.events
    assert [e["seq"] for e in normal.events] == list(range(1, len(normal.events) + 1))
    assert all(e["at"] for e in normal.events)
    json.dumps(normal.to_dict())


def test_every_calculator_call_is_logged_with_inputs_outputs_and_a_difference_field(normal):
    calls = events(normal, "calculator_call")
    assert calls and {c["calculator"] for c in calls} >= {"to_pounds", "fair_share_gap", "arrival_time", "pickup_feasibility", "storage_at"}
    for c in calls:
        assert "input" in c and ("output" in c or "error" in c)
        assert c["difference_from_stand_in"] is None  # the stand-ins are the calculators here
    assert normal.calculator_differences == []


def test_each_move_records_the_calculator_calls_it_made(normal):
    seqs = {c["seq"] for c in events(normal, "calculator_call")}
    bids = [m for m in events(normal, "move") if m["move"]["action"] == "counter" and m["role"] == "food_bank"]
    assert bids and all(m["calculator_call_seqs"] and set(m["calculator_call_seqs"]) <= seqs for m in bids)


def test_the_same_inputs_give_the_same_run():
    a = run_scenario(load_scenario(CONTRACT_EXAMPLE), StandInCalculators())
    b = run_scenario(load_scenario(CONTRACT_EXAMPLE), StandInCalculators())
    assert a.events == b.events


# --- Stop rules -----------------------------------------------------------------------------


def test_the_deadline_stops_the_negotiation_unclaimed_and_nothing_commits():
    run = run_scenario(load_scenario(CONTRACT_EXAMPLE), StandInCalculators(), minutes_per_turn=20)
    assert run.status == "unclaimed_deadline"
    assert not events(run, "commitment")
    assert all(i["unclaimed_lb"] == i["pounds"] for i in run.outcome["items"])
    assert all(run.rule_checks().values()), {k: v.failures for k, v in run.lane_b_rule_checks.items()}


def test_approvals_arriving_after_the_deadline_commit_nothing():
    data = raw()
    for h in data["humans"]:
        h["after_minutes"] = 240
    run = run_scenario(load_scenario(data), StandInCalculators())
    assert run.status == "unclaimed_deadline" and not events(run, "commitment")
    assert all(run.rule_checks().values())


def test_a_human_decline_commits_nothing():
    data = raw()
    data["humans"][1]["on_approval_request"] = "decline"  # city
    run = run_scenario(load_scenario(data), StandInCalculators())
    assert run.status == "declined_by_human"
    assert not events(run, "commitment")
    assert all(run.rule_checks().values())


def test_an_organization_with_no_human_script_never_approves_so_nothing_commits():
    data = raw()
    data["humans"] = [h for h in data["humans"] if h["organization_id"] != "rural"]
    run = run_scenario(load_scenario(data), StandInCalculators())
    assert run.status == "no_human_response"
    assert not events(run, "commitment")


def test_a_condition_doubt_stops_for_a_human_check():
    data = raw()
    data["surplus_offers"][0]["items"][1]["condition_doubt"] = "cold chain unknown"
    run = run_scenario(load_scenario(data), StandInCalculators())
    assert run.status == "waiting_for_human"
    stop = events(run, "stop")[-1]
    assert stop["rule"] == "ask_human" and "cold chain unknown" in stop["reason"]
    assert not events(run, "commitment")


def test_a_recalled_lot_is_never_offered():
    data = raw()
    data["surplus_offers"][0]["recall_notice"] = True
    run = run_scenario(load_scenario(data), StandInCalculators())
    assert run.status == "recalled"
    assert not events(run, "version") and not events(run, "move")


def test_three_rounds_without_new_terms_preserve_the_disagreement():
    # A donor whose staff never accept: it passes every turn, so nothing reaches holds.
    class Stubborn:
        def __init__(self, inner):
            self.inner = inner

        def move(self, agent_input):
            m = self.inner.move(agent_input)
            if m.kind.value in ("accept", "request_hold"):
                return replace(m, kind=type(m.kind)("pass"), holds=(), reason="We are not ready to accept version "
                               f"{agent_input.draft.version}.")
            return m

    def factory(role, org, calculators):
        n = rules_negotiator(role, org, calculators)
        return Stubborn(n) if org == "market" else n

    run = run_scenario(load_scenario(CONTRACT_EXAMPLE), StandInCalculators(), negotiator_factory=factory)
    assert run.status == "preserved_disagreement"
    assert events(run, "stop")[-1]["rule"] == "preserved_disagreement"
    assert not events(run, "commitment")


def test_a_move_about_an_old_version_or_not_a_move_at_all_is_logged_and_changes_nothing():
    class Stale:
        """Answers about the version before the current one, then with garbage."""

        def __init__(self, inner):
            self.inner, self.turns = inner, 0

        def move(self, agent_input):
            self.turns += 1
            if self.turns == 1:
                return "accept"
            m = self.inner.move(agent_input)
            return replace(m, version=m.version - 1) if self.turns == 2 else m

    def factory(role, org, calculators):
        n = rules_negotiator(role, org, calculators)
        return Stale(n) if org == "eastside" else n

    run = run_scenario(load_scenario(CONTRACT_EXAMPLE), StandInCalculators(), negotiator_factory=factory)
    invalid = events(run, "invalid_move")
    assert [i["organization_id"] for i in invalid] == ["eastside", "eastside"]
    assert "not a move" in invalid[0]["problem"] and "names version" in invalid[1]["problem"]
    assert run.status == "committed"
    assert all(run.rule_checks().values())


# --- Swapping calculators and negotiators ----------------------------------------------------


@dataclass
class SlowerRoutes(StandInCalculators):
    """A different Calculators implementation: every trip takes 5 minutes longer."""

    label = "test calculators (routes 5 minutes slower)"

    def arrival_time(self, departs_at, travel_minutes):
        return super().arrival_time(departs_at, travel_minutes) + timedelta(minutes=5)


def test_another_calculators_implementation_can_be_injected_and_its_differences_are_logged():
    run = run_scenario(load_scenario(CONTRACT_EXAMPLE), calculators=SlowerRoutes())
    scenario_event = events(run, "scenario")[0]
    assert scenario_event["calculators"] == SlowerRoutes.label
    assert scenario_event["compared_with"] == StandInCalculators.label
    diffs = run.calculator_differences
    assert diffs and {d["calculator"] for d in diffs} == {"arrival_time"}
    d = diffs[0]["difference_from_stand_in"]
    assert d["fields"] == ["arrives_at"]
    assert d["stand_in_output"]["arrives_at"] != d["output"]["arrives_at"]
    # Calls that agree record no difference.
    assert any(c["difference_from_stand_in"] is None for c in events(run, "calculator_call"))
    assert all(run.rule_checks().values()), {k: v.failures for k, v in run.lane_b_rule_checks.items()}


def test_a_calculator_answer_that_differs_changes_the_run_and_the_log_shows_why():
    @dataclass
    class NoColdSpace(StandInCalculators):
        label = "test calculators (no cold space anywhere)"

        def storage_at(self, storage, at):
            free = super().storage_at(storage, at)
            return replace(free, cold_free_lb=0.0)

    run = run_scenario(load_scenario(CONTRACT_EXAMPLE), calculators=NoColdSpace())
    assert {d["calculator"] for d in run.calculator_differences} == {"storage_at"}
    assert run.committed_draft is None or run.committed_draft.pounds("romaine", "city") == 0
    assert all(run.rule_checks().values()), {k: v.failures for k, v in run.lane_b_rule_checks.items()}


class RefusingClient:
    """Stands in for anthropic.Anthropic(): every response is a refusal. Never calls the API."""

    def __init__(self):
        self.calls = 0
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **request):
        self.calls += 1
        usage = SimpleNamespace(input_tokens=10, output_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return SimpleNamespace(model=request["model"], stop_reason="refusal", usage=usage, content=[])


def test_llm_negotiators_can_take_a_role_and_their_fallbacks_are_logged():
    client = RefusingClient()
    cap = SpendingCap(limit_usd=1.0)

    def factory(role, org, calculators):
        if role is Role.ADVOCATE:
            return LLMNegotiator(role, org, cap=cap, client=client, calculators=calculators)
        return rules_negotiator(role, org, calculators)

    run = run_scenario(load_scenario(CONTRACT_EXAMPLE), StandInCalculators(), negotiator_factory=factory)
    advocate_moves = [m for m in events(run, "move") if m["role"] == "advocate"]
    assert advocate_moves and all(m["negotiator"] == "llm" for m in advocate_moves)
    assert all(m["llm"]["source"] == "fallback" for m in advocate_moves)
    assert client.calls == len(advocate_moves)
    assert events(run, "scenario")[0]["negotiators"]["advocate"] == "llm"
    assert run.number_check_failures == sum(m["llm"]["number_check_failures"] for m in advocate_moves)
    # The fallback is the rules-based move, so the run matches the all-rules run.
    assert run.status == "committed"
    assert all(run.rule_checks().values())


def test_llm_negotiators_for_gives_the_llm_only_the_named_roles():
    factory = llm_negotiators_for([Role.FOOD_BANK], cap=SpendingCap(limit_usd=1.0), client=RefusingClient())
    calc = StandInCalculators()
    assert isinstance(factory(Role.FOOD_BANK, "city", calc), LLMNegotiator)
    assert not isinstance(factory(Role.DONOR, "market", calc), LLMNegotiator)
    assert factory(Role.FOOD_BANK, "city", calc).calculators is calc


# --- The recorder logs the calculator contract's JSON ----------------------------------------

CALCULATOR_EXAMPLES = Path(__file__).parents[2] / "docs" / "contracts" / "examples" / "calculators.json"


def window(w):
    return TimeWindow(datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"]))


def contract_args(name, i):
    """A contract example's JSON input as the Python arguments of the ``Calculators`` method."""
    return {
        "fair_share_gap": lambda: ([HouseholdBalance(h["household_size"], h["received_lb"]) for h in i["households"]],),
        "gap_after_plan": lambda: (i["gap_lb"], i["planned_lb"]),
        "storage_at": lambda: ([StorageSlot(window(s["window"]), s["cold_free_lb"], s["dry_free_lb"]) for s in i["storage"]],
                               datetime.fromisoformat(i["at"])),
        "capacity_fit": lambda: (i["free_lb"], i["needed_lb"]),
        "pickup_feasibility": lambda: (datetime.fromisoformat(i["arrives_at"]), [window(w) for w in i["pickup_windows"]],
                                       datetime.fromisoformat(i["usable_until"])),
        "arrival_time": lambda: (datetime.fromisoformat(i["departs_at"]), i["travel_minutes"]),
        "to_pounds": lambda: (i["produce_id"], i["quantity"], i["unit"], i["lb_per_unit"]),
    }[name]()


def test_the_recorder_logs_every_contract_calculator_example_in_the_contracts_shape():
    examples = json.loads(CALCULATOR_EXAMPLES.read_text())["examples"]
    log = EventLog()
    calc = RecordedCalculators(StandInCalculators(), log, lambda: datetime.fromisoformat("2026-10-13T12:00:00-07:00"))
    covered = [e for e in examples if hasattr(calc.primary, e["calculator"])]
    # The stand-ins have no fair_share or household_portions; Lane A's calculators do, and
    # core_tests/test_join.py records those two contract examples through this recorder.
    assert {e["calculator"] for e in examples} - {e["calculator"] for e in covered} == {"fair_share", "household_portions"}
    assert hasattr(calc, "fair_share") and hasattr(calc, "household_portions")
    for ex in covered:
        method = getattr(calc, ex["calculator"])
        if "error" in ex:
            with pytest.raises(CalculatorError):
                method(*contract_args(ex["calculator"], ex["input"]))
        else:
            method(*contract_args(ex["calculator"], ex["input"]))
        logged = log.events[-1]
        assert logged["input"] == ex["input"], ex["name"]
        assert logged.get("output") == ex.get("output") and logged.get("error") == ex.get("error"), ex["name"]


class WithFairShare(StandInCalculators):
    """A non-stand-in with a fair_share calculator the stand-ins don't have."""

    label = "test calculators (with fair_share)"

    def fair_share(self, household_size):
        from harvestnet_agents.fair_share import fair_share
        return fair_share(household_size, self.table)


def test_a_calculator_the_stand_ins_lack_is_logged_as_not_compared_never_as_agreeing():
    log = EventLog()
    clock = lambda: datetime.fromisoformat("2026-10-13T12:00:00-07:00")  # noqa: E731
    calc = RecordedCalculators(WithFairShare(), log, clock, reference=StandInCalculators())
    calc.fair_share(4)
    event = log.events[-1]
    assert event["calculator"] == "fair_share" and event["output"]["pounds"] == 12
    assert event["difference_from_stand_in"] is None
    assert "no fair_share calculator" in event["not_compared"]
    calc.gap_after_plan(10, 4)
    assert "not_compared" not in log.events[-1]


def test_a_known_reason_for_a_difference_is_added_to_its_explanation():
    log = EventLog()
    clock = lambda: datetime.fromisoformat("2026-10-13T12:00:00-07:00")  # noqa: E731
    calc = RecordedCalculators(SlowerRoutes(), log, clock, reference=StandInCalculators(),
                               explanations={"arrival_time": "every route is 5 minutes slower in this test"})
    calc.arrival_time(datetime.fromisoformat("2026-10-13T13:00:00-07:00"), 20)
    d = log.events[-1]["difference_from_stand_in"]
    assert d["fields"] == ["arrives_at"]
    assert d["explanation"].endswith("Why: every route is 5 minutes slower in this test")
