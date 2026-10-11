# Lane A takeover acceptance stack

User authorized commits on all six original yi36 branches; review stack #7 -> #8 -> #9 -> #10 -> #22 -> #24. Requirements are the supplied plan and live GitHub issues. Keep issues open until all acceptance gates are verified. No AWS, paid model runs or real SMS is authorized.

## Issue #7

Transactional records, owner holds, exact-version human approvals, event audits and real-agent fixture execution. Shared calculator and API primitives are prerequisites for executing household confirmations and releases. SQLite is the local fallback; CI uses a dedicated Postgres service. Test: python -m unittest discover -s core_tests -v, with agents/src on PYTHONPATH.

## Issue #8

Real calculator, matching, recall, number-validation and stale-approval acceptance tests. Also injects these calculators into the newly merged teammate scenario runner. Core audits and Lane B checks are separate; no result is synthesized.

## Issue #9

Real public API and HTTP server, consent/privacy/expiry, owner authentication, condition checks, counter processing, commitments and household pickup release. No actual SMS or voice provider calls. The HTTP server binds localhost unless configured.

## Issue #10

First-come-first-served and nearest-food-bank baselines share the real harness and safety checks. Five synthetic fixtures, measured deterministic metrics and replay. Missing live LLM runs are explicitly not_run, not invented.

## Issue #20 (join: real agents in the harness)

`harvestnet_core/join.py`. `run_join(fixture)` runs one contract fixture through Lane A's harness (`run_fixture`) with Lane B's rules-based negotiators and the real calculators, and a `HarnessLog` writes Lane B's event log for that same run. So the fixture's eight checks (from the harness records) and Lane B's six (from the log) are both real results on one run, with nothing pending. Every calculator call is compared with Lane B's stand-ins; a difference carries both answers and the reason from `Calculators.stand_in_differences`. `run_join` also runs Lane B's `run_scenario` with the real calculators as a cross-check, and for its cooler-failure logic (#15). `python -m harvestnet_core.join` prints one line per fixture. The fixtures in `core_fixtures/` are already contract-v0.1 scenarios, so they load unchanged. Test: `core_tests/test_join.py`.

## Issue #22

Actual HTTP tests for browser requests and the Lane C human capability relay; real agents compared over five A2A hosts and in-process. Recorded voice extraction remains a labeled replay. External provider configuration and a reachable core deployment remain acceptance gates.
