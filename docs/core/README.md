# Lane A takeover: issues #7, #8, #9, #10, #22 and #24

User direction (October 11, 2026): implement the six assigned yi36 issues and commit to each original branch. The review stack uses `yi36/07-scenario-harness-records`, `yi36/08-calculators-matching-stop-rules`, `yi36/09-real-api-logic`, `yi36/10-baselines-evaluation-runner`, `yi36/22-join-live-households-voice`, `yi36/24-join-evaluation-live`. Each branch includes its prerequisites. Shared records, calculator and API primitives are introduced with #7 because the harness must execute actual commitments and household replies. Later commits add the issue-specific acceptance tests and joins. No original teammate commits were overwritten. The base includes merged contracts, agents and #20 at `bf099b0`. Issues remain open until their external acceptance gates are verified.

## Run and integrate

From the repository root, install the `agents` package or put `agents/src` on
`PYTHONPATH`. No model SDK is needed for rules, baselines or replay.

```sh
PYTHONPATH=agents/src python -m unittest discover -s core_tests -v
PYTHONPATH=agents/src python -m harvestnet_core run core_fixtures/normal-afternoon.json
PYTHONPATH=agents/src python -m harvestnet_core evaluate core_fixtures/*.json
PYTHONPATH=agents/src python -m harvestnet_core replay runtime/replays/normal-afternoon-rules_based-0.json
PYTHONPATH=agents/src python -m harvestnet_core.server
```

On PowerShell, use `$env:PYTHONPATH='agents/src'` once, then omit the prefix from
the commands. `evaluate` stores each scenario's results in the records the server
reads (`--database`, default `DATABASE_URL` or `runtime/core.sqlite`), so
`GET /results?scenario_id=...` serves them unchanged. The cooler-failure scenario
reads Lane C's organization systems in process, so run from the repository root. The server binds localhost port 8050. `HOST` (set `0.0.0.0` in a container), `PORT`, `DATABASE_URL`,
`HARVESTNET_FIXTURE`, `HARVESTNET_ALLOWED_ORIGIN` and `HARVESTNET_STAFF_TOKENS`
configure it. Staff tokens are a JSON object with a different secret for each
organization ID. Store them in ignored local configuration and pass them as
Bearer credentials. Never expose them to household pages or put them in Git.
The frontend must attach its own organization's staff credential for staff
operations. Household read-back and create routes require no staff token.

`DATABASE_URL` accepts a SQLite path or PostgreSQL DSN. PostgreSQL requires
`psycopg[binary]==3.2.10`. Both use transactions; Postgres reservations also take
an advisory transaction lock across API processes. SQLite is the labeled local
persistence option. A persistent server seeds missing fixture records only,
and never resets existing household balances on restart.

The default fixture is synthetic, and responses retain that label. A real
deployment must supply reviewed organization facts, a real clock, and a fixture
without scripted households. Changing a label does not turn recorded facts into
live evidence. The original Lambda address serves the example skeleton. The
team subsequently deployed the core at `https://18-217-110-223.sslip.io/api`
and the household, donor-dashboard and results-strip pages on the same host.
Read-only checks on October 11 verified HTTP 200 responses for health, fair share,
food banks, published results and all three pages. API responses remain explicitly
synthetic. These checks do not verify browser interactions, voice calls, SMS,
n8n publication or Directory registration. AWS work remains deferred for this
Codex session; no resources were provisioned here.

## #7: scenario harness and records

`records.py`, `protocol.py`, `engine.py`, `checks.py`, and `stand_ins.py` provide
transactional records, ordered events, replaceable Lane A stand-ins, real Lane B
rules and a shared seeded clock. The small normal fixture produces a commitment,
pickup notice and confirmation. Every named human must explicitly approve the
exact terms hash/version while owner holds remain valid. No missing reply or
deadline can create a commitment. Fixture humans are always labeled scripted.

Audits recompute approval/version evidence, overlapping storage/truck/lot holds,
per-item conservation, pathways, fair-share limits and counted number failures.
Tests tamper with an approval and double-book storage, and assert audit failure.
CI runs a real Postgres service and tests event persistence, rollback and reconnect.
The local machine has no Postgres server. GitHub Actions run 38127403436 verified
the actual Postgres test: all 32 core tests passed with no skips, followed by
601 existing agent and API skeleton tests. Each of the six original branch push
workflows also passed. This verifies test database persistence, not production
deployment or external provider delivery.

## #8: calculators, matching, versions and stop rules

`Calculators` implements all six agreed calculators and the supporting capacity,
gap-after-plan and arrival tools, without inheriting stand-in calculators. Calls
are logged. Household portions water-fill the largest deficits, never exceed the
placeholder fair share, and leave excess unassigned. Missing pack weights and
storage readings cannot invent capacity. NaN, infinity and boolean quantities
are rejected. Pickup eligibility checks actual weekly household windows,
can't-eat exclusions, spoilage deadlines and same-day collection for limited-fridge
households receiving produce whose profile says it needs a fridge (`needs_fridge`,
design section 8; not the transport cold chain). Pickup windows also stay within
the owner's reserved storage interval.

Every counter creates a version and clears previous approvals and holds. Owner
holds reject overlapping overbooking. Three rounds without new terms preserve
disagreement, and the API records deadline unclaimed without auto-commit.
Recalled produce is refused. Condition doubt needs an explicit authenticated
condition check; it never disappears through ordinary approval.

Outgoing policy reasons are checked against inputs and calculator results
(`workflows.checked_move`, shared by the fixture harness and the public API's
scheduler). After a failed number check the same owner is asked once more; only
after the second failure does the deterministic owner move with template wording
replace it (`template_fallback` event). Each failure is counted on the lot and in
the event log. LLM policy provenance includes internal number failures and
fallback causes.

Scripted faults are **not forecast**. No method's agents see a cooler failure
before its time: the plan is negotiated and committed on the working cooler. At
the fault time the harness runs Workflow 4 in process
(`cooler_join.apply_fault`): Lane C's demo switch fails the cooler, the failing
food bank's agent reads its own systems, rediscovers food banks through Lane C's
local Directory, runs Lane B's cooler-failure flow, records the failed cooler in
its status and proposes the new version. Each named organization's scripted human
decides on that exact version, minutes counted from the fault. No reply is no
approval. Without an approved change, cold-dependent pickups at the failed cooler
become `held_for_human` and are never counted as collected. This is the same path
as the #23 join, without HTTP. It does not certify the live AGNTCY Directory or
n8n re-approval.

With the shipped cooler fixture, the scripted eastside human answers 15 minutes
after being asked. That is exactly the planned trip's arrival time, because Lane
B's plan departs at the moment of detection, so the core refuses the answer as
stale and nothing commits. This is reported as is (see #10 below). A variant
where humans answer within the trip time commits the change; the tests cover both.

## #9: real API logic

`api.py` implements every agreed public API operation with the same top-level
response fields. Unknown records return 404; stale terms return 409. Fair share
comes from the real calculator. Preview saves nothing; saving requires complete
answers and explicit consent. Requests expire after seven days, including their
write-only phone and pickup records. Their pickup notices in the event log keep
only the pounds, items and food bank; the request code and the household's pickup
window are removed (design section 12). Names, addresses and income are refused.

`GET /` lists every operation (the agreed contract plus the three additive,
proposed routes), with `contract_version`. A contract test calls all 20 agreed
operations for real and checks each status and field against its example, one
level into nested objects and list items (`core_tests/test_followups.py`).
`get_lot` items carry `split` (food bank, pounds, mover), `unclaimed_lb` once the
lot is settled, and `households_reached`. A missing body field, an unknown
`produce_id` or another bad input returns the contract's 400; only unknown
records return 404.

A surplus offer's `drop_off` applies to that offer only. It is checked and stored
with the lot, survives restarts, and never changes the donor's recorded drop-off
or other lots. An item without `usable_until` gets the **produce profile's**
minimum usable days (cold life for cold-dependent produce, room life otherwise),
counted from the report time and labeled `usable_until_basis: profile_assumption`
with the profile field, days, profile set version and that field's sources. The
label is returned by `create_surplus_offer` and `get_lot`. A `use_soon` item must
state the donor's own `usable_until`: the profiles give no use-soon life, and
none is invented (ADR 0002). A condition check relabels the item `condition_check`.

Offers schedule each organization's real rules, acquire its own holds and stop
awaiting actual human approvals. Accept/decline, counter queueing, version history,
status updates, donor item views, dashboards and pickup confirmation use records.
Household views show only committed pickups. A release is scoped to its pickup
and request code, is safe to retry, and reassigns only within the reserved pickup
window to eligible households below fair share.

The additive authenticated `POST /lots/{lot_id}/condition-checks` takes
`organization_id`, `version`, `produce_id`, `condition_grade`, `usable_until`, and
`reason`. Only donor staff or the receiving bank can clear its condition doubt;
this creates a new version and invalidates old approvals. This operation needs
frontend contract review; it does not change existing route shapes.

Staff auth binds each token to one organization. The legacy Lane C approval
payload is accepted by normalizing `event_id` to `lot_id`, the donor role alias
to the actual donor ID, and the raw SHA-256 digest to the agreed prefixed form.
The decision and exact terms are never changed. The actual platform approval
store/HTTP client is tested against the core with separate owner credentials.

## #10: baselines and evaluation runner

Five synthetic fixtures cover normal afternoon, storage shortage, produce
shortage, cooler failure and condition doubt. Baselines give banks first
opportunity by earliest household request or recorded donor travel time,
respectively. They still use each owner's real review, resource holds and human
approvals. The advocate makes no baseline amendments.

Metrics come from run records: produce wasted with its split (below),
worst-served weekly coverage, households reached, pickup-window match, time to
first commitment, invalid commitments and counted number failures.
**Worst-served coverage** follows design section 16: for each food bank, the
average over the households that chose it of each household's share of fair share
received (capped at 1, zeros included), then the lowest of those averages.
`coverage_by_food_bank` shows each average. **Pickup-window match** is the share
of collected pounds whose recorded confirmation came before the item's usable
time (`null` when nothing was collected). A household that chose several food
banks counts in each. The old value took the single lowest household and was 0.0
in every run; it now differs across scenarios and methods.

For a scenario with a fault, each method's result has `cooler_failure`: how many
faults, `mid_run_workflow_4`, the change statuses and any refusals, pounds and
pickups moved or released, and pounds `held_for_human`. On the shipped cooler
fixture every method reports the refused late answer and held cold pickups,
because the fixture's scripted timing is what it is. Change commitments count
toward `invalid_commitments` like first commitments.

**Produce wasted** (design section 16, decided by the user October 11, 2026):
`produce_split` in `evaluation.py` counts every offered pound once, as
`collected_by_households_lb`, else `committed_to_food_banks_lb`, else
`produce_wasted_lb`. A committed pound counts as committed only when its food
bank's own storage hold (cold if the produce profile needs it) overlaps the food
bank's pickup hours before the item's usable time, checked with the
`pickup_feasibility` calculator. A failed cooler ends cold storage at the
failure. A Workflow 4 fallback kept at the failed cooler counts only as a
`same_day_offer`, using the profile's room-temperature life. Everything else is
wasted: unclaimed pounds, and commitments that would spoil first. A household's
collected pounds come out of its food bank's committed share, so nothing is
counted twice. The old value (everything the scripted households did not collect)
is still reported as `uncollected_by_scenario_households_lb`. None of this is
observed spoilage, and the note beside each result says so. Replays carry
the original moves and must reproduce commitments/pathways/checks without any
Claude calls. Results remain whatever the run computes.

## #20: join, real agents in the harness

`harvestnet_core/join.py`. `run_join(fixture)` runs one contract fixture through Lane A's harness (`run_fixture`) with Lane B's rules-based negotiators and the real calculators, and a `HarnessLog` writes Lane B's event log for that same run. So the fixture's eight checks (from the harness records) and Lane B's six (from the log) are both real results on one run, with nothing pending. Every calculator call is compared with Lane B's stand-ins; a difference carries both answers and the reason from `Calculators.stand_in_differences`. `run_join` also runs Lane B's `run_scenario` with the real calculators as a cross-check, and for its cooler-failure logic (#15). `python -m harvestnet_core.join` prints one line per fixture. The fixtures in `core_fixtures/` are already contract-v0.1 scenarios, so they load unchanged. Test: `core_tests/test_join.py`.

## #22: household, voice, approval and pickup join

Web and recorded English/Spanish transcripts go through the existing Lane B
front desk. An injected extractor must pass its evidence checks; raw transcript
text is not stored. Voice intake returns read-back/consent without saving; a
separate consented voice request gets the same calculated fair share as the web.
Without a configured voice extractor the API returns 503 and directs to text.
`POST /voice-intake` has a per-process sliding-window rate limit (20 calls a
minute by default, `voice_rate_limit` on `API`); over it, 503 `rate_limited`. The
API refuses a bare Lane B `ClaudeExtractor`: it must be wrapped in
`harvestnet_core.voice.CappedExtractor`, which takes a spending cap (zero to $100,
nonzero needs `allow_paid`). The extractor doesn't report token usage, so each
call is reserved and charged at its worst case (every prompt and transcript
character as an input token, full `max_tokens` output, highest listed price).
When the next call's worst case doesn't fit, no call is made: 503
`spending_cap_reached`. The local server attaches no extractor.

Local HTTP tests exercise browser-style request creation and the existing
capability-verified human approval relay. Tests also cover pickup views, wrong
request releases, retries, reassignment and fair-share conservation. Live
ElevenLabs calls, n8n publication, SES email delivery and the actual frontend screens
still require their configuration/deployment. No real pickup email was sent.

## #23: join, cooler failure end to end (local only)

Cooler failure end to end. `harvestnet_core/cooler_join.py` runs the cooler-failure fixture to its commitment, then fails the city cooler mid-run through Lane C's demo switch. The city's agent reads its own organization systems, gets its holding from `GET /lots/{lot_id}/holding`, rediscovers food banks through Lane C's Directory, and runs Lane B's cooler-failure flow. It records the failed cooler with `PUT /food-banks/{id}/status` and proposes the new version with `POST /lots/{lot_id}/changes`. `harvestnet_core/changes.py` records that version. Each named human decides on it through Lane C's review links and `/approvals`. Only when every named organization approves does the core place the owners' holds, move the commitments, and move the affected pickups. Lane B writes the household texts, and the core adds `to`, `pickup_id` and `release_url`. The reason cards appear under `disruptions` on the food bank dashboard. The new routes and the change record are proposed, pending #1. Test: `python -m unittest core_tests.test_cooler_failure_join -v`, with `PYTHONPATH=agents/src` and `HARVESTNET_PLATFORM_SOURCE=.`. Nothing is deployed. Beeceptor data for the scenario's day: `python -m harvestnet_core.cooler_join --export-systems runtime/cooler-systems.json --export-openapi runtime/cooler-openapi.json`.

## #24: real evaluation join

`live_evaluation.py` connects existing Lane B LLM negotiators to the same real
calculators/harness and records source, model calls, number failures, cost and
fallback cause. One cap is shared across repetitions and scenarios when the same
provider is reused. It defaults to zero and rejects limits above $100. A nonzero
cap requires explicit authorization. This session spent no provider credits.

Repeated runs report individual values plus mean and standard deviation.
`publish_evaluation` stores the results response; `/results` returns those method
values unchanged. `python -m harvestnet_core evaluate` calls it for each fixture.
`--llm-cap-usd 0` runs the LLM method with no model calls (`fallback_only`); a
nonzero cap needs `--allow-paid` and is shared by every scenario and repetition
in the command (`--repeats`). Missing LLM configuration gives `not_run`, with null values.
Each LLM run is labeled from its own `policy_provenance` events, not from the
shared cap: it reports `model_calls`, `llm_decisions`, `fallback_decisions` and
`template_fallbacks`. Runs with no LLM decisions (zero cap, or a shared cap
already spent) are `fallback_only` with `measured: false`; a run that hits the
cap midway is `partial`, with the counts visible. A number-check re-ask records
both calls' cost and counts. `llm_cost_usd` is this scenario's own spend;
`llm_cap_spent_usd` is the shared cap's running total. A zero cap never builds
the Anthropic client. `not_run` and `fallback_only` are not presented as a real
LLM evaluation. Paid repeated LLM runs on the deployed system
remain an open acceptance gate.

## Actual transport join

`join_adapter.policy` uses the existing real Lane B policy and real core
calculators. `join_adapter.harness` adapts only the transport's donor alias,
preserving typed draft/facts, clocks, decisions and resource ownership. A test
runs the full mixed batch across five actual A2A HTTP hosts and in-process and
requires identical nonempty commitments, pathways and all core rule checks.

For Lane C, use `AGENT_POLICY=harvestnet_core.join_adapter:policy` and the harness
export `harvestnet_core.join_adapter:harness`. Bake both core and reviewed agents
into the organization images. This local proof does not replace container,
native Directory daemon or public HTTPS deployment acceptance.

## Latest teammate compatibility

Merged main `3e427e6` adds the team's beyond-fair-share bank bidding policy.
The original six branches now include it. The core implements its signed
`adjust_pounds` operation and preserves each owner's negotiator across turns in
the harness, public scheduler, baselines and evaluation provider. A2A policy
sessions isolate owner memory between independent runs. This memory is local
process state; host-restart recovery and native Directory deployment are not
claimed verified. Household portions retain the agreed fair-share cap; a bank
bid beyond its gap does not fabricate consent or allocate above household caps.
