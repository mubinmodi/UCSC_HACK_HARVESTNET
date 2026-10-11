# Lane C handoff

## Current state (October 11, contract follow-ups)

The Lane C code is merged into `main` and follows the agreed contracts in
`docs/contracts/` (ticket #1) and the API skeleton in `api_skeleton/`:

- Organization IDs are `market`, `city`, `rural`, `eastside`, `advocate`. The
  systems fixture is `synthetic-v2`, dated October 13, 2026 at `-07:00`, and
  follows the core's normal afternoon.
- The transport wraps Lane B's agent input unchanged, sends `facts` only to the
  organization whose turn it is, checks moves against `agent-moves.md`, and waits
  up to `AGENT_TURN_TIMEOUT_SECONDS` (default 60) per turn.
- The approval bridge posts `record_approval` (`lot_id`, `sha256:` hash) with each
  organization's own core token (`CORE_API_TOKENS`), passes core rejections
  through, issues ISO 8601 `expires_at`, has a configurable link lifetime, and can
  reissue a lost link. SMS replies map from the sending phone to its pickup: YES
  confirms, CAN'T MAKE IT calls the release operation.
- Native hosts republish their Directory record when their capabilities change.
- One setting, `CLAUDE_RUN_CAP_USD` (default 0), caps the LLM negotiators and the
  voice extractor.

An AWS Compose overlay now prepares a private AGNTCY `dirctl daemon` with SQLite,
the local OCI store, and the search indexer in one container. Each of the five
organization hosts publishes its own record through the pinned Directory SDK.
`deploy/aws/check_directory.sh` lists registrations and searches cold capacity
and pickup time from inside the city host; it reports whether both answers came
from AGNTCY or from the labeled local fallback. Unit tests and merged Compose
configuration pass. A local container smoke test registered and found one city
host through the real daemon using synthetic data. This is a candidate AWS
deployment: all five hosts, cooler-change republish, and resource use on the
instance have not been verified. See `docs/platform/TRANSPORT.md` and
`deploy/aws/README.md`.

Still open, because they need deployment or accounts: re-importing the
`synthetic-v2` Beeceptor mock, live AGNTCY Directory verification, published n8n
workflows with credentials and a real SMS provider (including Twilio signature
checking in front of the reply webhook), and Secrets Manager plus HTTPS hosting.

The sections below are the earlier history.

## Earlier history

All five calebdbur branches have implementation work. They form a **review stack**:
16 -> 17 -> 18 -> 19 -> 21. Each branch contains the earlier branches' platform
foundation; each pull request uses the previous branch as its base. Review and
merge in that order (or merge the final aggregate only after team review).
Nothing was merged to main, and no issue was closed on partial evidence.

## What works locally

- #16: donor inventory/truck and three food banks' storage/cooler/hours/trucks,
  isolated restart-safe cooler switch, synthetic labels, Beeceptor OpenAPI export,
  recorded fallback on outage or incompatible responses.
- #17: one organization host per donor/bank/advocate, A2A JSON-RPC and native
  AGNTCY App SDK hosting, ordered durable receipts and retries, own proposal moves
  only, capability records/search adapter and labeled in-process/local registry.
- #18: exact-terms review page, independent human decision capabilities, stale
  approval rejection, no-answer/no-approval, four inactive n8n imports, committed
  pickup text formatting, verified SNAP tip filtering and authenticated release
  adapter. Approval relay carries an explicit human receipt without changing it.
- #19: one-command local rehearsal with every fallback labeled; shared durable
  Claude budget guard defaults to zero, Secrets Manager loader, private Postgres
  and five organization services, HTTPS proxy, redeploy/rollback runbook and CI.
- #21: adapter for the real core/policies, fail-closed outcome/rule comparisons,
  partial-outage retries and a synthetic mixed-batch network/in-process seam test.

## Remaining acceptance gates

Expanded verification on October 11: all **36 local tests** pass, including
native App SDK startup and authenticated exchange. Twelve added resilience checks
cover malformed HTTP data, pending-turn recovery after invalid receipts, receipt
and approval persistence after restart, simultaneous reservations across twelve
budget connections, core outage/retry with the same human receipt, every mock
system resource, isolated failure for each food bank, and inactive authenticated
n8n workflow graphs. Testing found and fixed nested transport shape crashes,
premature join-sequence advancement, incomplete pickup text validation, and
nonfinite Directory capacity queries. The combined Compose configuration and
regeneration of all four n8n imports pass. Workflow graph checks do not certify an
actual n8n import/SMS execution, and Compose validation does not run containers.

The agreed contracts (ticket #1) and the API skeleton are on `main`, and the
platform now follows them (see "Current state" above). The #20 real harness is
merged. Lane B's rules are in the in-repo `agents/`. The Lane C adapter verifies all 25
recorded rule scenarios over HTTP with exact direct-policy output equality and
duplicate retries. It supports nonvoting `pass` and explicit donor ID aliasing.
The production adapter requires Lane A's real calculators; its recorded-calculator
test adapter is rejected by the real-join CLI. See `JOIN.md`. Proposed interfaces need review with
Lane A/B. Real-agent fixture equality and actual core rule checks for #21 cannot
be certified until those adapters exist. Do not replace them with constant checks.
With the pinned Lane B package and native SDK available, all **39 tests** pass
locally. CI has a separate pinned-source compatibility job for the new adapter.

Beeceptor is configured at `https://harvestnet.proxy.beeceptor.com` with the
OpenAPI contract and fixed synthetic examples. All 17 system routes were tested
against the live service; city failure returned a failed cooler reading and zero
cold capacity while rural stayed working. The local ignored `.env` has this URL.

The four application workflows were imported and saved as unpublished drafts in
`https://harvestnet.app.n8n.cloud`. A fifth manual-only Beeceptor connection check
ran successfully from n8n Cloud. Application workflows still need their Header
Auth credentials, public platform/core URLs and SMS provider credentials before
publication. No real SMS delivery was attempted. No verified Market Match market
is shipped; test markets are explicitly synthetic.

Cloud workflow IDs (not credentials): review requests `7Qkc7a0X3TuYhwYd`, pickup
texts `Ez4Sir1ssOKZfjuo`, replies `ESzgVkSoQOjzQeU3`, human receipt relay
`c2jM64ZyOnRp49tA`, manual connection check `X9bHymRDirw1LDq8`.

The user has an AWS account, but no AWS host, authenticated session, secret ARN,
domain or core API image is configured. **User hosting budget is $0: prepare only
until credits are confirmed. Do not provision chargeable resources.** The user
subsequently deferred AWS work entirely on October 11: skip AWS sign-in, credit
checks and provisioning until the user resumes that scope. Continue non-AWS
integration work; n8n application workflows still require a reachable API before
they can be fully activated. Secrets
Manager storage and actual HTTPS deployment are not verified. Docker Compose is
validated, but Docker Engine/container runtime is absent. Native App SDK startup
and authenticated A2A exchange pass locally; a real Directory daemon push/search
still needs its runtime. Recorded system capabilities are synthetic snapshots;
owners must recheck current facts/reservations before any commitment.

No Claude calls or provider credits were spent. Lane B's LLM negotiators and
front-desk extractor now read their cap from `CLAUDE_RUN_CAP_USD` (default 0).

## Resume work

1. Fetch latest remote branches and inspect #1/#20 for actual adapter exports.
2. Use the module interfaces in `JOIN.md`; integrate without rewriting teammate
   policies or core rules. Test the same deterministic fixture in both transports.
3. Rerun all tests and Compose validation. Optional SDK tests can be enabled by
   installing `requirements-agntcy.txt`; Windows `pip --target` installs require
   `site.addsitedir` to process pywin32 .pth hooks (normal virtualenv install does
   that automatically).
4. Configure sponsor/AWS accounts only when their credentials/host are available.
   Keep secrets in local ignored configuration or Secrets Manager, never Git.
5. Update the appropriate branch/PR. Keep incomplete acceptance checkboxes open.

The local rehearsal is at `python -m harvestnet_platform.demo`; its URL has an
ephemeral session fragment in ignored `runtime/demo-url.txt`. The review page
does not allocate, commit, or create real household records. It can demonstrate
the integration controls while the full team application is being joined.

## Review submission (October 11)

The user requested submission of the existing PRs for team review. PRs #26-#30
are ready for review, with dependencies and incomplete acceptance gates retained;
none were merged or issues closed. All 39 tests were rerun successfully. The
user-provided n8n API key authenticated successfully and listed all five inactive
workflows. The key is stored only in ignored local configuration. Live SMS,
Directory daemon registration and AWS deployment remain unverified. The real
core comparison has since passed in the takeover stack described below. Review
readiness is not full issue acceptance.

## Six original takeover branches (October 11)

The user authorized taking over yi36's six issues and explicitly requested
commits and pushes on each original branch. Those branches now form a review
stack #7 -> #8 -> #9 -> #10 -> #22 -> #24, with PRs #42 through #47. No teammate
commits were overwritten or force-pushed. The aggregate PR #40 is superseded.
Read `docs/core/README.md` on the final branch for requirements and open gates.
The original five Caleb branches/PRs #26-#30 remain separate and unmerged.

The core stack incorporates newly merged #20 (`bf099b0`). Its actual HTTP tests
exercise the existing Lane C human capability relay and compare real-agent
commitments/pathways/core audits over five A2A hosts against in-process execution.
Run 38127403436 passed all 32 core tests with actual Postgres, no skips, and 601
existing agent/API skeleton tests. This does not certify native Directory or
public deployment. Paid repeated LLM runs, live voice/SMS, unexpected cooler
rediscovery/reapproval and the actual teammate frontend screens remain open.
The new household frontend currently uses synthetic credits/locations and a
placeholder adapter; do not silently treat those as the agreed pounds contract.

The existing overnight heartbeat now checks all eleven issues every ten minutes
and responds to actionable teammate changes. AWS remains deferred; spending is
zero and no real SMS/messages are authorized. Usage limits cannot be bypassed.
