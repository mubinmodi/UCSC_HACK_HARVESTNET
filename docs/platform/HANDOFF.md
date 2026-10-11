# Lane C handoff

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

The shared #1 API contracts/skeleton and #20 real harness have no code in
their remote branches as last checked. Lane B's rules now exist at pinned commit
`f06b14822d4379bc790a2f1d8a4525ac94cb7649`. The Lane C adapter verifies all 25
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
until credits are confirmed. Do not provision chargeable resources.** Secrets
Manager storage and actual HTTPS deployment are not verified. Docker Compose is
validated, but Docker Engine/container runtime is absent. Native App SDK startup
and authenticated A2A exchange pass locally; a real Directory daemon push/search
still needs its runtime. Recorded system capabilities are synthetic snapshots;
owners must recheck current facts/reservations before any commitment.

No Claude calls or provider credits were spent. Lane B's future client must use
the budget wrapper; configuration alone does not intercept an arbitrary client.

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
