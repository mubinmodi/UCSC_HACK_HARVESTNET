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

## Issue #22

Actual HTTP tests for browser requests and the Lane C human capability relay; real agents compared over five A2A hosts and in-process. Recorded voice extraction remains a labeled replay. External provider configuration and a reachable core deployment remain acceptance gates.

## Issue #23 (join, local only)

Cooler failure end to end. `harvestnet_core/cooler_join.py` runs the cooler-failure fixture to its commitment, then fails the city cooler mid-run through Lane C's demo switch. The city's agent reads its own organization systems, gets its holding from `GET /lots/{lot_id}/holding`, rediscovers food banks through Lane C's Directory, and runs Lane B's cooler-failure flow. It records the failed cooler with `PUT /food-banks/{id}/status` and proposes the new version with `POST /lots/{lot_id}/changes`. `harvestnet_core/changes.py` records that version. Each named human decides on it through Lane C's review links and `/approvals`. Only when every named organization approves does the core place the owners' holds, move the commitments, and move the affected pickups. Lane B writes the household texts, and the core adds `to`, `pickup_id` and `release_url`. The reason cards appear under `disruptions` on the food bank dashboard. The new routes and the change record are proposed, pending #1. Test: `python -m unittest core_tests.test_cooler_failure_join -v`, with `PYTHONPATH=agents/src` and `HARVESTNET_PLATFORM_SOURCE=.`. Nothing is deployed. Beeceptor data for the scenario's day: `python -m harvestnet_core.cooler_join --export-systems runtime/cooler-systems.json --export-openapi runtime/cooler-openapi.json`.
