"""The persistent Claude spend ledger and the total cap it backs. No test calls the Claude API."""

import json
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from harvestnet_agents.front_desk import ClaudeExtractor, ExtractionError, Transcript
from harvestnet_agents.llm_negotiators import (
    CostEntry,
    SpendingCap,
    SpendingCapReached,
    total_cap_usd_from_env,
)
from harvestnet_agents.spend_ledger import LedgerError, SpendLedger, TotalCapReached

from test_llm_negotiators import run_llm

FIXTURES = Path(__file__).parent / "fixtures"


def entry(cost, model="claude-sonnet-5-5"):
    return CostEntry("org", "donor", model, 0, 0, 0, 0, cost, cost)


def env_for(tmp_path, run=None, total=None):
    env = {"CLAUDE_SPEND_LEDGER": str(tmp_path / "spend.json")}
    if run is not None:
        env["CLAUDE_RUN_CAP_USD"] = str(run)
    if total is not None:
        env["CLAUDE_TOTAL_CAP_USD"] = str(total)
    return env


# --- the ledger file --------------------------------------------------------------------------


def test_ledger_survives_a_new_process_and_the_cli_seeds_it(tmp_path):
    path = tmp_path / "spend.json"
    command = [sys.executable, "-m", "harvestnet_agents.spend_ledger", "--ledger", str(path)]
    added = subprocess.run(command + ["add", "9.92", "--note", "Oct 11 runs, upper bound"], capture_output=True, text=True, check=True)
    assert "9.9200" in added.stdout
    shown = subprocess.run(command + ["show"], capture_output=True, text=True, check=True)  # another process
    assert "total $9.9200" in shown.stdout and "Oct 11 runs, upper bound" in shown.stdout
    ledger = SpendLedger(path)  # and this one
    assert ledger.total_usd() == 9.92
    (only,) = ledger.entries()
    assert only["caller"] == "manual" and only["note"] == "Oct 11 runs, upper bound"


def test_cli_refuses_a_bad_amount_and_a_corrupt_file(tmp_path):
    path = tmp_path / "spend.json"
    command = [sys.executable, "-m", "harvestnet_agents.spend_ledger", "--ledger", str(path)]
    assert subprocess.run(command + ["add", "nan"], capture_output=True, text=True).returncode == 1
    assert not path.exists()
    path.write_text("{not json")
    assert subprocess.run(command + ["add", "1"], capture_output=True, text=True).returncode == 1
    assert path.read_text() == "{not json"  # never overwritten


def test_entries_hold_only_time_caller_model_cost_and_a_manual_note(tmp_path):
    cap = SpendingCap.from_env(env_for(tmp_path, run=5), caller="voice_line")
    cap.reserve(0.5)
    cap.settle(0.5, CostEntry("household-organization-id", "front_desk", "claude-sonnet-5-5", 10, 5, 0, 0, 0.5, 0.01))
    (written,) = SpendLedger(tmp_path / "spend.json").entries()
    assert set(written) == {"time", "caller", "model", "cost_usd"}
    assert (written["caller"], written["model"], written["cost_usd"]) == ("voice_line", "claude-sonnet-5-5", 0.01)
    datetime.fromisoformat(written["time"])


def test_concurrent_writers_lose_no_entries(tmp_path):
    path = tmp_path / "spend.json"

    def write(count):
        ledger = SpendLedger(path)  # each writer has its own handle, like a separate caller
        for _ in range(count):
            ledger.add(0.01)

    threads = [threading.Thread(target=write, args=(15,)) for _ in range(8)]
    code = "from harvestnet_agents.spend_ledger import SpendLedger; l = SpendLedger({!r}); [l.add(0.01) for _ in range(15)]".format(str(path))
    processes = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [p.wait() for p in processes] == [0] * 4
    assert len(SpendLedger(path).entries()) == (8 + 4) * 15
    assert SpendLedger(path).total_usd() == pytest.approx(1.8)


def test_concurrent_reservations_never_overspend_the_total(tmp_path):
    path = tmp_path / "spend.json"
    granted, refused = [], []

    def reserve():
        try:
            granted.append(SpendLedger(path).reserve("negotiator", 0.2, 1.0))
        except TotalCapReached:
            refused.append(1)

    threads = [threading.Thread(target=reserve) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert (len(granted), len(refused)) == (5, 7)
    assert SpendLedger(path).total_usd() == pytest.approx(1.0)


def test_unsettled_reservations_count_then_are_charged_when_stale(tmp_path):
    now = [datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)]
    ledger = SpendLedger(tmp_path / "spend.json", clock=lambda: now[0])
    ledger.reserve("negotiator", 0.4, 1.0)  # a process that died mid-call
    assert ledger.total_usd() == 0.4
    with pytest.raises(TotalCapReached):
        ledger.reserve("negotiator", 0.7, 1.0)
    now[0] += timedelta(hours=2)
    with pytest.raises(TotalCapReached):
        ledger.reserve("negotiator", 0.7, 1.0)  # stale: now charged as spent, still 0.4
    (charged,) = ledger.entries()
    assert charged["cost_usd"] == 0.4 and "never settled" in charged["note"]
    assert ledger.total_usd() == 0.4


def test_an_unreadable_or_unwritable_ledger_fails_closed(tmp_path):
    bad = tmp_path / "spend.json"
    bad.write_text(json.dumps({"entries": [{"cost_usd": "free"}]}))
    cap = SpendingCap.from_env(env_for(tmp_path, run=5))
    with pytest.raises(SpendingCapReached, match="unreadable"):
        cap.reserve(0.01)
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("")
    cap = SpendingCap.from_env({"CLAUDE_SPEND_LEDGER": str(blocked / "spend.json"), "CLAUDE_RUN_CAP_USD": "5"})
    with pytest.raises(SpendingCapReached):
        cap.reserve(0.01)
    assert cap.reserved_usd == 0


# --- the caps ---------------------------------------------------------------------------------


def test_total_cap_defaults_to_the_run_cap_and_zero_means_no_paid_calls(tmp_path):
    assert total_cap_usd_from_env({"CLAUDE_RUN_CAP_USD": "2"}) == 2  # unset
    assert total_cap_usd_from_env({"CLAUDE_RUN_CAP_USD": "2", "CLAUDE_TOTAL_CAP_USD": "  "}) == 2  # blank
    assert total_cap_usd_from_env({"CLAUDE_RUN_CAP_USD": "2", "CLAUDE_TOTAL_CAP_USD": "50"}) == 50
    for bad in ("nan", "inf", "-1", "lots"):
        with pytest.raises(ValueError):
            total_cap_usd_from_env({"CLAUDE_TOTAL_CAP_USD": bad})

    unset = SpendingCap.from_env(env_for(tmp_path, run=2))
    assert unset.total_limit_usd == 2
    unset.reserve(1.5)
    with pytest.raises(SpendingCapReached):
        unset.reserve(1.0)  # the run cap, as before

    # a run cap above an unset total can't be spent twice: the second run sees the first's spend
    second = SpendingCap.from_env(env_for(tmp_path, run=2))
    unset.settle(1.5, entry(1.5))
    with pytest.raises(SpendingCapReached, match="ledger shows"):
        second.reserve(1.0)

    zero = SpendingCap.from_env(env_for(tmp_path, run=5, total=0))
    with pytest.raises(SpendingCapReached):
        zero.reserve(0.0001)
    nothing = SpendingCap.from_env(env_for(tmp_path / "other", total=5))  # run cap unset = 0
    with pytest.raises(SpendingCapReached):
        nothing.reserve(0.0001)
    assert not (tmp_path / "other").exists()  # a refused call touches no file


def test_total_cap_blocks_a_call_that_fits_the_run_cap_but_not_the_remaining_total(tmp_path):
    env = env_for(tmp_path, run=5, total=50)
    SpendLedger.from_env(env).add(49.95, note="earlier runs")  # $0.05 left of the $50 total
    cap = SpendingCap.from_env(env)
    with pytest.raises(SpendingCapReached, match="total cap"):
        cap.reserve(0.10)  # well inside the $5 run cap
    assert cap.reserved_usd == 0
    cap.reserve(0.04)  # still fits
    assert SpendLedger.from_env(env).total_usd() == pytest.approx(49.99)


def test_settling_adds_the_actual_cost_not_the_reservation_and_release_gives_it_back(tmp_path):
    env = env_for(tmp_path, run=5, total=10)
    cap = SpendingCap.from_env(env)
    cap.reserve(2.0)
    cap.settle(2.0, entry(0.25))
    ledger = SpendLedger.from_env(env)
    assert ledger.total_usd() == 0.25 and cap.spent_usd == 0.25 and cap.reserved_usd == 0
    cap.reserve(3.0)
    assert ledger.total_usd() == pytest.approx(3.25)
    cap.release(3.0)  # the call was never made
    assert ledger.total_usd() == 0.25 and cap.reserved_usd == 0


def test_two_caps_in_one_or_two_processes_share_one_total(tmp_path):
    env = env_for(tmp_path, run=5, total=1)
    first, second = SpendingCap.from_env(env), SpendingCap.from_env(env)
    first.reserve(0.6)
    with pytest.raises(SpendingCapReached):
        second.reserve(0.6)  # in flight counts
    first.settle(0.6, entry(0.6))
    with pytest.raises(SpendingCapReached):
        second.reserve(0.6)  # and so does what was spent
    second.reserve(0.4)


def test_a_cap_built_directly_has_no_ledger_and_keeps_the_run_cap_only(tmp_path):
    cap = SpendingCap(1.0)
    cap.reserve(0.5)
    cap.settle(0.5, entry(0.5))
    with pytest.raises(SpendingCapReached):
        cap.reserve(0.6)
    assert cap.ledger is None and not any(tmp_path.iterdir())


# --- the callers ------------------------------------------------------------------------------


def costed_client(text='{"household_size": 4}'):
    usage = SimpleNamespace(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    response = SimpleNamespace(
        model="claude-sonnet-5-5", stop_reason="end_turn", usage=usage,
        content=[SimpleNamespace(type="text", text=text)],
    )
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return response

    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create))), calls


def test_front_desk_extractor_is_held_to_the_total_cap_and_records_actual_cost(tmp_path, monkeypatch):
    for name, value in env_for(tmp_path, run=5, total=50).items():
        monkeypatch.setenv(name, value)
    transcript = Transcript.from_dict(json.loads((FIXTURES / "front_desk" / "en_complete.json").read_text())["transcript"])
    client, calls = costed_client()
    ClaudeExtractor(client=client)(transcript)
    (written,) = SpendLedger.from_env().entries()
    assert written["caller"] == "front_desk"
    assert written["cost_usd"] == pytest.approx((1000 * 2.0 + 200 * 10.0) / 1_000_000)

    SpendLedger.from_env().add(49.99)
    with pytest.raises(ExtractionError, match="total cap"):
        ClaudeExtractor(client=client)(transcript)
    assert len(calls) == 1  # the second call was never made


def test_llm_negotiator_falls_back_without_a_call_when_the_total_is_spent(tmp_path):
    env = env_for(tmp_path, run=5, total=50)
    SpendLedger.from_env(env).add(50.0, note="earlier runs")
    _, _, _, decision, client, cap = run_llm("city_bids_only_what_cold_storage_allows", cap=SpendingCap.from_env(env, caller="negotiator"))
    assert client.requests == []
    assert decision.source == "fallback" and "total cap" in decision.fallback_reason
    assert SpendLedger.from_env(env).total_usd() == 50.0
