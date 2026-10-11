# Lane A takeover: issues #7, #8, #9, #10, #22 and #24

User direction (October 11, 2026): implement the six assigned yi36 issues and commit to each original branch. The review stack uses `yi36/07-scenario-harness-records`, `yi36/08-calculators-matching-stop-rules`, `yi36/09-real-api-logic`, `yi36/10-baselines-evaluation-runner`, `yi36/22-join-live-households-voice`, `yi36/24-join-evaluation-live`. Each branch includes its prerequisites. Shared records, calculator and API primitives are introduced with #7 because the harness must execute actual commitments and household replies. Later commits add the issue-specific acceptance tests and joins. No original teammate commits were overwritten. The base includes merged contracts, agents and #20 at `bf099b0`. Issues remain open until their external acceptance gates are verified.

## Run and integrate

From the repository root, install the `agents` package or put `agents/src` on
`PYTHONPATH`. No model SDK is needed for rules, baselines or replay.

```sh
PYTHONPATH=agents/src python -m unittest discover -s core_tests -v
PYTHONPATH=agents/src python -m harvestnet_core run core_fixtures/normal-afternoon.json
PYTHONPATH=agents/src python -m harvestnet_core evaluate core_fixtures/normal-afternoon.json
PYTHONPATH=agents/src python -m harvestnet_core replay runtime/replays/normal-afternoon-rules_based-0.json
PYTHONPATH=agents/src python -m harvestnet_core.server
```

On PowerShell, use `$env:PYTHONPATH='agents/src'` once, then omit the prefix from
the commands. The server binds localhost port 8050. `PORT`, `DATABASE_URL`,
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
live evidence. The existing AWS address serves the example skeleton, not this
new core. AWS remains deferred by the user; no resources were provisioned here.

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
households receiving cold-dependent produce. Pickup windows also stay within
the owner's reserved storage interval.

Every counter creates a version and clears previous approvals and holds. Owner
holds reject overlapping overbooking. Three rounds without new terms preserve
disagreement, and the API records deadline unclaimed without auto-commit.
Recalled produce is refused. Condition doubt needs an explicit authenticated
condition check; it never disappears through ordinary approval.

Outgoing policy reasons are checked against inputs and calculator results. The
fixture harness retries once after a number failure, then uses a deterministic
owner fallback with template wording. Each failure is counted. The public rules
scheduler checks its deterministic output too. LLM policy provenance includes
internal number failures and fallback causes.

The cooler-failure evaluation fixture gives **every method the same known
scripted fault forecast** and conservatively excludes unsafe cold reservations.
It logs the timed fault. It does not certify unexpected post-commit disruption,
live Directory rediscovery or n8n re-approval; those remain #23/#21 deployment
acceptance work. The normal fixture removes the cooler fault; the dedicated
cooler fixture keeps it. The agreed contract example is left unchanged.

## #9: real API logic

`api.py` implements every agreed public API operation with the same top-level
response fields. Unknown records return 404; stale terms return 409. Fair share
comes from the real calculator. Preview saves nothing; saving requires complete
answers and explicit consent. Requests expire after seven days, including their
write-only phone and pickup records. Names, addresses and income are refused.

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

Metrics come from run records: produce not collected by the scripted end,
worst-served weekly coverage, households reached, pickup-window match, time to
first commitment, invalid commitments and counted number failures. The
`produce_wasted_lb` field currently means **not collected by scenario end**, not
observed spoilage. This definition is stated beside each result. Replays carry
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
No uncapped Claude extractor is instantiated automatically.

Local HTTP tests exercise browser-style request creation and the existing
capability-verified human approval relay. Tests also cover pickup views, wrong
request releases, retries, reassignment and fair-share conservation. Live
ElevenLabs calls, n8n publication, SMS delivery and the actual frontend screens
still require their configuration/deployment. No real SMS was sent.

## #24: real evaluation join

`live_evaluation.py` connects existing Lane B LLM negotiators to the same real
calculators/harness and records source, model calls, number failures, cost and
fallback cause. One cap is shared across repetitions and scenarios when the same
provider is reused. It defaults to zero and rejects limits above $100. A nonzero
cap requires explicit authorization. This session spent no provider credits.

Repeated runs report individual values plus mean and standard deviation.
`publish_evaluation` stores the results response; `/results` returns those method
values unchanged. Missing LLM configuration gives `not_run`, with null values.
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
