# The HarvestNet core

The core is the deterministic middle of HarvestNet: the records, the calculators, the rules that stop a negotiation, the public API, and the evaluation. It never decides for an organization. It checks every move, keeps every record, and commits a Surplus lot only when each named organization's Staff approver has approved the same exact version while the owners' holds are still valid (ADR 0001, 0004). Every number comes from a calculator or a record (ADR 0002). All shipped data is synthetic, and responses say so (`mode`, `synthetic`).

API shapes live in [`docs/contracts/`](../contracts/README.md), terms in [`CONTEXT.md`](../../CONTEXT.md), decisions in [`docs/adr/`](../adr/), the design in [`docs/MVP_DESIGN.md`](../MVP_DESIGN.md). This page says how the code works and what is easy to get wrong.

## Run it

Run everything from the repository root. The core imports `harvestnet_agents` (Lane B) and `harvestnet_platform` (Lane C), so first `cd agents && uv sync`, then use `agents/.venv/bin/python` with `PYTHONPATH=agents/src`. Rules, baselines and replay need no model SDK. The tests that run Lane C's code in process always run: `core_tests/platform_source.py` puts `HARVESTNET_PLATFORM_SOURCE` on the import path, or the repository root when it is unset. `demo_replay` reads the variable too. The Postgres test runs only when `HARVESTNET_TEST_DATABASE_URL` names a dedicated test database.

```sh
export PYTHONPATH=agents/src HARVESTNET_PLATFORM_SOURCE=.
PY=agents/.venv/bin/python
$PY -m unittest discover -s core_tests          # one test: -m unittest core_tests.test_stop_rules
$PY -m harvestnet_core run core_fixtures/normal-afternoon.json
$PY -m harvestnet_core evaluate core_fixtures/*.json
$PY -m harvestnet_core replay runtime/replays/normal-afternoon-rules_based-0.json
$PY -m harvestnet_core.server                    # localhost:8050
$PY -m harvestnet_core.join                      # every fixture through both rule-check sets
$PY -m harvestnet_core.cooler_join --export-systems runtime/cooler-systems.json --export-openapi runtime/cooler-openapi.json
$PY -m harvestnet_core.demo_replay --check       # is the offline demo recording current?
```

`python -m harvestnet_core --help` lists the flags. What each command is for:

- **`run`** runs fixtures through the harness and prints the result.
- **`evaluate`** runs every method on each fixture and stores the result in the records the server reads (`--database`, default `DATABASE_URL` or `runtime/core.sqlite`), so `GET /results?scenario_id=...` serves it unchanged. It also saves each run's replay under `--output` (default `runtime/replays`).
- **`replay`** re-runs a saved run from its recorded moves. It must reproduce commitments, pathways and checks with no model call, or it raises.
- **`join`** (`join.py`) runs each fixture two ways with the real calculators: Lane A's harness and Lane B's own runner. A `HarnessLog` writes Lane B's event log for the harness run, so the fixture's checks and Lane B's six checks both read one run. Every calculator call is also compared with Lane B's stand-ins.
- **`cooler_join`** exports the cooler-failure scenario's day as organization-systems data and an OpenAPI file for Beeceptor.
- **`demo_replay`** records the demo scenario into `docs/demo/replay/recording.json` and `docs/demo/replay.html` for the offline backup (`docs/demo/REHEARSAL.md`). Run it again, without `--check`, after any change that alters the recording; a core test fails when the files are stale.

### Server settings

| Variable | Meaning |
|---|---|
| `HOST` (127.0.0.1), `PORT` (8050) | Bind address. A container sets `HOST=0.0.0.0`. |
| `DATABASE_URL` | SQLite path (default `runtime/core.sqlite`) or a PostgreSQL DSN (needs `psycopg[binary]==3.2.10`). |
| `HARVESTNET_FIXTURE` | Scenario the server seeds from. Seeding adds missing records only; a restart never resets household balances. |
| `HARVESTNET_STAFF_TOKENS` | JSON map of organization ID to its own secret. Each token authenticates that one organization. Keep it out of Git and out of household pages. Only the core holds the whole map; each deployed food bank host gets only its own entry. |
| `HARVESTNET_APPROVALS_TOKEN` | Optional. The approval bridge's own credential (at least 16 characters, different from every staff token). Accepted only on `POST /approvals`, with a `receipt_id`, for a named organization, and still subject to every version, terms-hash and deadline check; refused for every other operation. Proposed (platform isolation). |
| `TRANSPORT_SIGNING_KEY` | Optional. The turn publisher's (`core`) own transport key, for signing turns sent to the organization hosts (`docs/platform/TRANSPORT.md`). Unused until the core publishes turns over A2A. |
| `HARVESTNET_ALLOWED_ORIGIN` | CORS origin (default `http://127.0.0.1:8040`). |
| `ANTHROPIC_API_KEY`, `CLAUDE_RUN_CAP_USD`, `CLAUDE_TOTAL_CAP_USD`, `CLAUDE_SPEND_LEDGER` | Voice intake is on only when the key is set and both caps are above zero (the total defaults to the run cap). Otherwise `voice_intake` answers 503 and households use the text form. The run cap is per process; the total cap is checked against the spend ledger file (default `runtime/claude-spend.json`; `/app/budget/claude-spend.json` on AWS), so a restart does not reset it. |
| `HARVESTNET_HOUSEHOLD_URL`, `N8N_PICKUP_WEBHOOK_URL`, `N8N_RELEASE_WEBHOOK_URL`, `N8N_WEBHOOK_TOKEN`, `SES_TEST_RECIPIENTS` | Household email. Setting either webhook requires all of these, or the server refuses to start. `GET /health` answers 503 if the email worker thread has died. |

SQLite is the labeled single-host option. PostgreSQL takes an advisory transaction lock for each reservation, so several API processes stay consistent. Staff routes read the token from `Authorization: Bearer ...`; bodies are JSON objects up to 256 KiB.

## What each module owns

| Module | Owns |
|---|---|
| `records.py` | Transactional JSON records and the append-only event log. Events never contain an email address. |
| `protocol.py` | The rules for holds, versions, approvals and commitment. |
| `engine.py` | The scripted harness (`run_fixture`): a seeded clock, owner-by-owner turns, scripted humans, pickups and household replies. |
| `workflows.py` | Negotiation for live offers (`negotiate_pending`) without scripted humans, and the outgoing-message number check. |
| `checks.py` | Audit checks recomputed from stored evidence (approvals, holds, conservation, fair share over the household's whole week), never a constant. Booking uses each owner's real capacity (`Engine.audit_capacities`). |
| `calculators.py` | The agreed calculators plus capacity, gap-after-plan and arrival helpers (`docs/contracts/calculators.md`). |
| `api.py` | The public API. `OPERATIONS` is the route table (`GET /` lists it) and each operation has an `op_<name>` handler. |
| `server.py` | The JSON HTTP server around `API`. |
| `changes.py` | A changed version of a committed lot after a disruption, with its own approvals. |
| `cooler_join.py`, `cooler_watch.py` | Workflow 4 end to end: `apply_fault` in the harness, `handle_cooler_reading` and the deployed per-food-bank watcher over HTTP. |
| `evaluation.py`, `live_evaluation.py` | Methods, metrics, replay, and the capped LLM provider. |
| `voice.py` | `CappedExtractor`: a hard spending cap (run cap plus the total cap in the spend ledger) around Lane B's Claude extractor. |
| `notices.py`, `contact.py`, `email_delivery.py` | Household pickup emails: the facts, address checking and the release link, and the outbox that delivers to n8n. |
| `join.py`, `join_adapter.py` | Lane A and Lane B joined in one process; the policy and harness the platform's A2A hosts run (`AGENT_POLICY=harvestnet_core.join_adapter:policy`). |
| `demo_replay.py` | The recorded demo. |

## The lot lifecycle

A Surplus lot moves through **negotiating, awaiting approvals, committed**, with two other endings: **unclaimed** and **preserved disagreement**.

- **Versions.** Every counter creates a new version and clears all approvals and holds. Approvals and holds name one version and one terms hash (`sha256:<hex>`); a stale one is refused (409).
- **Turns.** Each organization's own negotiator moves in published turn order (`turn_order` in the fixture). A move must come from the organization whose turn it is, name the current version, and carry a reason. The advocate may only counter or pass. Each owner's negotiator persists across turns, in the harness, the public scheduler, the baselines and the evaluation provider.
- **Holds.** Only a resource's owner places a hold on it. Overlapping holds are checked against capacity at every boundary, so two non-concurrent holds do not block each other, and a double booking is refused. A hold that is already over is a refused move (`hold_refused`), not a crash.
- **Awaiting approvals.** A lot reaches it when it has allocations and every named organization holds its resources, and no human has declined this version.
- **Commitment.** When every named organization has approved the exact version, and every hold is still valid, the core validates the plan against its own records and commits. No missing reply and no deadline commits anything. Fixture humans are scripted and labeled so.
- **A hold that expires** before the last approval returns the lot to negotiation: stale holds go, approvals clear, and the owners' next turns run (`hold_expired`).
- **A decline** returns the lot to negotiation the same way (`returned_to_negotiation`). The declined version stays declined, so those exact terms are never sent for approval again, and any later decision on that version is refused (409), as on a change.
- **Counter shapes by owner** (ADR 0001, 0013). `Protocol.check_owner_amendment` runs on every counter, in the harness, the public scheduler and `POST /lots/{id}/counters`: a food bank changes only its own share, except a **contest** (or take-back), a `shift_pounds` of one item from one other food bank to itself. Setting another food bank's pounds or transport, or shifting between two other food banks, is refused. Every turn's input carries the claims stated so far (`claims_in`: each contest or take-back with its `claimant_gap_lb`), so the other food bank can split the item in proportion to the two gaps and concede toward need. The advocate's facts carry each contested pair (`contests_in`).
- **Stop rules.** A round counts toward the stop only if nobody changed the terms in it. After `rounds_without_new_terms_before_disagreement` such rounds (3 in the shipped fixtures), the lot becomes a **preserved disagreement** with a reason. A counter that brings back terms already seen at the same point in the turn order is a **cycle**, and ends the same way (`cycle_key`). With concede toward need (ADR 0013), a contest ends in a cycle only when a side refuses the proportional split. The dashboards of the involved organizations show the competing plans and each organization's last reason (`disagreement_view`). Nothing commits.
- **Deadline.** A lot still negotiating or awaiting approvals at its deadline becomes **unclaimed** with a reason. A preserved disagreement is a result, so it survives the deadline.
- **Staleness is checked when the API is called.** Every change (any non-`GET`) first runs `purge`: deadlines, hold expiry, and the seven-day request expiry. A `GET` runs it only when something is due (an open lot's deadline, a hold end on a lot awaiting approvals, a request expiry) or a minute has passed since the last purge, for records another API process added.
- **Local time.** Weekdays, pickup hours and "same day" are read on the fixture's `timezone` clock (`Engine.local`), whatever offset an instant carries, so the API's UTC clock and the fixtures' local times give the same pickups.
- **Refusals before negotiation.** A recalled lot is never offered. Condition doubt waits for an explicit authenticated condition check (`POST /lots/{lot_id}/condition-checks`, by the donor or the receiving food bank). That creates a new version and invalidates old approvals; ordinary approval never clears the doubt.
- **Counters from people** (`submit_counter`) queue until that organization's next published turn. Approvals are refused while a counter is queued.
- **Usable time.** An item with no `usable_until` gets the Produce profile's minimum usable days (cold life if the profile needs cold, room life otherwise), counted from the report time and labeled `usable_until_basis: profile_assumption` with the profile field, days, version and sources. A `use_soon` item must carry the donor's own `usable_until`; the profiles give no use-soon life and none is invented (ADR 0002).
- **Drop-off.** A surplus offer's `drop_off` applies to that offer only. The donor's recorded drop-off and other lots are unchanged.

### The outgoing-message number check

`workflows.checked_move` compares every number in a move's reason with the move's inputs and the calculator results. After a failed check the same owner is asked once more. After a second failure the deterministic owner move replaces it with template wording (`template_fallback`). Every failure is counted on the lot and in the event log.

### Per-item status

`get_lot` gives each item its own `status`, derived from the records and not copied from the lot: `offered`, `negotiating`, `held` (the owners of its pounds have placed holds), `committed`, `moving`, `at_food_bank` (its transports or a committed change's trip, against the clock), `collected` (every live pickup of it was collected), `disagreement`, and `unclaimed` (with `unclaimed_reason` when pounds are left over). Items also carry `split` (food bank, pounds, mover) and `households_reached`.

### After commitment

- **Pickups.** `distribute` checks for existing pickups and writes new ones in one transaction, and pickup IDs (`pk-<lot>-<n>`) count within the lot, so two processes never split a lot twice. Each committed pound is split among eligible households by the portion calculator, which fills the largest fair-share deficits first and never exceeds fair share. Eligibility checks the household's weekly windows, can't-eat items, spoilage deadlines, the food bank's pickup hours, and same-day collection for limited-fridge households receiving produce whose profile says `needs_fridge` (a household fridge, not the transport cold chain). Pickup windows stay inside the owner's reserved storage interval. Household views show only committed pickups.
- **Release.** `release_pickup` is scoped to its pickup and request code, is safe to retry, and reassigns only inside the reserved window to eligible households below fair share.
- **Cooler failure (Workflow 4).** No method's agents see a scripted fault before its time: the plan is negotiated and committed on the working cooler. When the cooler fails, the failing food bank's own agent reads its systems, rediscovers food banks through the Directory, runs Lane B's cooler-failure flow, records the failed cooler in its status, and proposes a new version (`POST /lots/{lot_id}/changes`). `changes.py` records it and treats it as its own versioned record on top of the commitment. Each named organization's Staff approver decides on that exact version; a decline is final for it, and the declined record is kept, because version numbers are never reused (`holding`'s `current_version` counts declined changes too). Only when all approve does the core place the owners' holds, move the commitments and move the affected pickups. Without an approved change, cold-dependent pickups at the failed cooler become `held_for_human` and are never counted as collected. The reason cards appear under `disruptions` on the food bank dashboard. In the deployed stack each food bank's host runs its own watcher (`cooler_watch.py`); it proposes and asks for review emails, and never approves.

## Evaluation

`evaluate` runs four methods on one fixture with the same rules, trucks, storage and Staff approver scripts: **first come, first served**, **nearest food bank**, **rules based**, and **llm**. Both baselines still go through each owner's real review, holds and approvals, and the advocate makes no baseline amendments.

- **First come, first served** (design section 16): the food bank whose households asked first claims whole items. A claimant takes the whole item, limited only by the hard rules (storage over time, its truck, pickup hours before the item spoils). Pounds it cannot take are never passed to another food bank; they stay unclaimed and count as wasted.
- **Nearest food bank**: food banks bid in order of recorded travel time from the donor, using the rules negotiators' own bids.
- **Contests stay out of the baselines.** Both baselines keep the mechanism they were defined with: their food banks never contest another's share (`NoContestFoodBank`, `FirstComeFoodBank`, `contests = False`). Only **rules based** (and **llm**) contest, per ADR 0013. With more households than produce, rules-based food banks below fair share contest and concede toward need, so the scarce produce commits split in proportion to their fair-share gaps (`proportional_split`, whole pounds).
- **Pathway split** (ADR 0011, decided October 11, 2026): `produce_split` counts every offered pound once, as `collected_by_households_lb`, else `committed_to_food_banks_lb`, else `produce_wasted_lb`. A committed pound counts as committed only when its food bank's own storage hold (cold if the profile needs it) overlaps the food bank's pickup hours before the usable time, checked with `pickup_feasibility`. A failed cooler ends cold storage at the failure. A Workflow 4 fallback kept at the failed cooler counts only as a `same_day_offer` with the profile's room life. A household's collected pounds come out of its food bank's committed share. None of this is observed spoilage, and the result's `note` says so. `uncollected_by_scenario_households_lb` is the older number: everything the scripted households did not collect.
- **Worst-served coverage** (design section 16): for each food bank, the average over the households that chose it of each household's share of fair share received (capped at 1, zeros included). The metric is the lowest of those averages, and `coverage_by_food_bank` shows each one. A household that chose several food banks counts in each.
- **Pickup-window match**: the share of collected pounds whose confirmation came before the item's usable time (`null` when nothing was collected).
- **Baselines on several lots.** Nearest food bank orders by the travel time from each lot's own donor, and who has finished bidding is tracked per lot.
- Also reported: households reached, time to first commitment, `invalid_commitments` (each first or change commitment that fails its own lot's invalid-commitment or booking check; `lot_rule_checks` in the run holds each lot's checks), counted number-check failures, and for a scenario with a fault a `cooler_failure` block (faults, change statuses and refusals, pounds and pickups moved or released, pounds held for a human).
- **LLM labels.** Without a provider the method is `not_run` with null values. `--llm-cap-usd 0` runs it with no model calls: every decision is a rules fallback, so it is `fallback_only` with `measured: false`. A nonzero cap needs `--allow-paid` and is shared by every scenario and repetition in the command (`--repeats`); it is refused above $100. `--llm-cap-usd` is the per-run cap. The total cap, `CLAUDE_TOTAL_CAP_USD` (default: the same cap; 0 means no paid calls), also applies, checked against the persistent spend ledger at `CLAUDE_SPEND_LEDGER` that every paid caller shares, so repeated commands and a core restart cannot reset it. A call that fits the run cap but not the remaining total is not made and counts as a rules fallback. Seed the ledger with spend from before it existed: `python -m harvestnet_agents.spend_ledger add 9.92 --note "Oct 11 runs, upper bound"`. Each run is labeled from its own `policy_provenance` events, not from the shared cap: `completed` (every decision from the model), `partial` (a mix of model, rules fallbacks and templates, with the counts visible), or `fallback_only`. A number-check re-ask records both calls' cost. `llm_cost_usd` is this scenario's own spend and `llm_cap_spent_usd` the shared cap's running total. A zero cap never builds the Anthropic client. `not_run` and `fallback_only` are not an LLM evaluation, and the frontends show them as such. Repeated runs report each value plus mean and standard deviation.
- **A shipped-fixture gotcha.** In `core_fixtures/cooler-failure.json` the eastside human answers 15 minutes after being asked, exactly the planned trip's arrival time, so the core refuses the answer as stale and nothing commits. Every method reports the refusal and the held cold pickups. A variant where humans answer within the trip time commits the change (both are tested), and the demo recording uses the 10-minute variant, labeled as such.

## Privacy

- A household request carries no name, address or income (those fields are refused). Email is optional, write-only, used only for pickup emails, never returned by the API or written to the event log.
- A request expires after seven days. Expiry deletes the request, its email, and its uncollected pickups. A collected pickup is kept only as a count: its request code is replaced by a fresh random `expired-...` reference and its window removed, so households reached and collected pounds do not shrink. Pickup notices in the event log keep only the pounds, items and food bank; the request code and the household's window are removed (design section 12).
- Household notices are built by `notices.py` (`pickup_ready`, `pickup_changed`, `pickup_released`). Delivery goes through an **outbox** in `email_delivery.py`: the event and its outbox entry commit together without an address or request code, and each entry is claimed before the network call. A restart or timeout therefore never sends a second copy. An ambiguous result is `uncertain`, and an operator inspects and reissues it. A changed or released pickup supersedes an unsent older notice, and only addresses in `SES_TEST_RECIPIENTS` are sent to.
- The release link carries the pickup and code in the URL fragment, so web server logs never see them. Opening the link changes nothing; only the household's tap on "Can't make it" releases the pickup.
- Voice intake returns a read-back and a consent question without saving. A separate consented request saves, with the same fair share as the web. Raw transcripts are not stored. `voice_intake` has a per-process rate limit (20 calls a minute, `voice_rate_limit` on `API`) and answers 503 `rate_limited` over it. The API refuses a bare Claude extractor: it must be a `CappedExtractor`, which reserves each call's worst case (every prompt and transcript character as an input token, the full output, the highest listed price) and makes no call, answering 503 `spending_cap_reached`, when the next call does not fit. The run cap is per process; the total cap is checked against the persistent spend ledger, so a restart does not reset it.

## Proposed routes, not yet in the contract

`GET /` lists every operation with `contract_version` and marks each `agreed` or `proposed`. These three are additive, authenticated, and change no existing route's shape. They need contract review (#1) and are not in `docs/contracts/public-api.md`:

- `POST /lots/{lot_id}/condition-checks`: `organization_id`, `version`, `produce_id`, `condition_grade`, `usable_until`, `reason`.
- `GET /lots/{lot_id}/holding?food_bank_id=...`: what the food bank holds, for the cooler-failure flow.
- `POST /lots/{lot_id}/changes`: a food bank's proposed changed version.

The change record and the `disruptions` field on the food bank dashboard are proposed with them.

## Gotchas

- `POST /approvals` takes only the agreed payload: `lot_id`, the organization's own ID (the donor is `market`, not a role), and a `sha256:`-prefixed hash. The core does not translate older forms; they are refused (400). Only the platform's `ApprovalStore.decide` also accepts a bare hex hash, because a human's page or n8n sends it.
- Staff tokens bind to one organization. An organization cannot approve, counter or confirm for another.
- Unknown records return 404, stale terms return 409, and bad input (a missing body or query field, or a value the rules refuse) returns the contract's 400. Any other exception is a server bug: it is logged and answered 500 with a generic message.
- `GET /approvals` and the dashboard's `needs_your_approval` share one rule (`API.awaiting_decision`): the lot awaits approvals, names the organization, has no decision from it on this version, and its deadline is ahead. `requested_at` is when the version's last owner hold landed.
- `core_tests/stand_ins.py` is a replaceable move provider for harness tests. It is test support, not product code.
- A real deployment needs reviewed organization facts, a real clock and a fixture without scripted households. Relabeling a recorded fact does not make it live evidence.

## History

The core was built ticket by ticket (#7 to #10, #20, #22 to #24). The record of that work is in the GitHub issues and pull requests of `mubinmodi/UCSC_HACK_HARVESTNET`; this page describes only what the code does now.
