"""The contract's scenario, run end to end with the real rules-based negotiators (#20).

Lane A's harness (#7) and real calculators (#8) don't exist yet, so the runner takes any
``Calculators`` implementation (the stand-ins here) and checks Lane B's rules over its
event log. Every number is synthetic. No test calls the Claude API."""

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from harvestnet_agents.calculators import CalculatorError, HouseholdBalance, StandInCalculators
from harvestnet_agents.llm_negotiators import LLMNegotiator, SpendingCap
from harvestnet_agents.negotiation import Role, StorageSlot, TimeWindow
from harvestnet_agents.rules_negotiators import rules_negotiator
from harvestnet_agents.scenario import load_scenario
from harvestnet_agents.scenario_runner import (
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
    return run_scenario(load_scenario(CONTRACT_EXAMPLE))


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


def test_the_fixtures_own_rule_checks_are_reported_as_pending_lane_a_never_faked(normal):
    assert set(normal.fixture_rule_checks) == set(raw()["rule_checks"])
    assert all(v == LANE_A_PENDING for v in normal.fixture_rule_checks.values())


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
    a = run_scenario(load_scenario(CONTRACT_EXAMPLE))
    b = run_scenario(load_scenario(CONTRACT_EXAMPLE))
    assert a.events == b.events


# --- Stop rules -----------------------------------------------------------------------------


def test_the_deadline_stops_the_negotiation_unclaimed_and_nothing_commits():
    run = run_scenario(load_scenario(CONTRACT_EXAMPLE), minutes_per_turn=20)
    assert run.status == "unclaimed_deadline"
    assert not events(run, "commitment")
    assert all(i["unclaimed_lb"] == i["pounds"] for i in run.outcome["items"])
    assert all(run.rule_checks().values()), {k: v.failures for k, v in run.lane_b_rule_checks.items()}


def test_approvals_arriving_after_the_deadline_commit_nothing():
    data = raw()
    for h in data["humans"]:
        h["after_minutes"] = 240
    run = run_scenario(load_scenario(data))
    assert run.status == "unclaimed_deadline" and not events(run, "commitment")
    assert all(run.rule_checks().values())


def test_a_human_decline_commits_nothing():
    data = raw()
    data["humans"][1]["on_approval_request"] = "decline"  # city
    run = run_scenario(load_scenario(data))
    assert run.status == "declined_by_human"
    assert not events(run, "commitment")
    assert all(run.rule_checks().values())


def test_an_organization_with_no_human_script_never_approves_so_nothing_commits():
    data = raw()
    data["humans"] = [h for h in data["humans"] if h["organization_id"] != "rural"]
    run = run_scenario(load_scenario(data))
    assert run.status == "no_human_response"
    assert not events(run, "commitment")


def test_a_condition_doubt_stops_for_a_human_check():
    data = raw()
    data["surplus_offers"][0]["items"][1]["condition_doubt"] = "cold chain unknown"
    run = run_scenario(load_scenario(data))
    assert run.status == "waiting_for_human"
    stop = events(run, "stop")[-1]
    assert stop["rule"] == "ask_human" and "cold chain unknown" in stop["reason"]
    assert not events(run, "commitment")


def test_a_recalled_lot_is_never_offered():
    data = raw()
    data["surplus_offers"][0]["recall_notice"] = True
    run = run_scenario(load_scenario(data))
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

    run = run_scenario(load_scenario(CONTRACT_EXAMPLE), negotiator_factory=factory)
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

    run = run_scenario(load_scenario(CONTRACT_EXAMPLE), negotiator_factory=factory)
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

    run = run_scenario(load_scenario(CONTRACT_EXAMPLE), negotiator_factory=factory)
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
    covered = [e for e in examples if hasattr(calc, e["calculator"])]
    # fair_share and household_portions aren't in the interface yet: Lane A adds them (#8).
    assert {e["calculator"] for e in examples} - {e["calculator"] for e in covered} == {"fair_share", "household_portions"}
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
