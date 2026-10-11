# Join real agents over A2A (#21)

The real core/policy adapters are now available on the original yi36 review stack
(PRs #42-#47). The core stack includes the merged #20 runner at `bf099b0` and
real calculators. Its HTTP integration test compares a real mixed-batch fixture
over five actual A2A hosts against the same in-process policies, requiring
nonempty identical commitments, pathways and recomputed core checks. Core CI run
38127403436 passed all 32 tests, including actual Postgres persistence, and 601
agent/API skeleton regressions. This is local A2A evidence; native Directory,
container/public HTTPS deployment and unexpected live cooler reapproval remain
unverified acceptance gates for #21.

Use `harvestnet_core.join_adapter:policy` and
`harvestnet_core.join_adapter:harness` from the reviewed core stack. Both the
core and real `harvestnet_agents` package must be available to each organization.

## Plug in teammates' code

Supply two synchronous adapters, without changing their decision logic:

- `real_agents:move(organization_id, input) -> move`: uses the SAME deterministic
  real rules policy and calculators locally and inside each organization container.
  Input has current `draft`, owner calculator `facts`, and `turn`. No individual
  household data goes to agents. Return our documented move shape or adapt once.
- `real_core:run_fixture(fixture, move_provider) -> run`: Lane A's seeded harness
  calls `move_provider(organization_id,input)` on each published turn. It owns
  drafts, stops, owner holds, explicit human approvals and records. Return
  `commitments`, `pathways` and `rule_checks` with boolean keys:
  `no_double_booking`, `pounds_conserved`, `versioned_approvals`, `no_auto_commit`,
  `all_pounds_have_pathway`, `zero_invalid_commitments`. Additional boolean
  checks are supported and must also pass. Never return constant success checks
  in the real harness; test checks here are synthetic stand-ins only.

Bake adapters into the reviewed agent image or mount the source read-only. Set
`AGENT_POLICY` for each organization to the real policy export. Set actual agent
URLs and `AGNTCY_DIRECTORY_ADDRESS`; each native host registers its own card at
startup. Re-register capacity changes and verify candidate facts at the owner.
Use a fresh event namespace for each test. Receipt stores make retries idempotent.

```sh
python -m harvestnet_platform.join --fixture path/to/mixed-batch.json \
  --harness real_core:run_fixture --policy real_agents:move
```

`AGENT_ENDPOINTS` is a JSON map with market/city/rural/eastside/advocate URLs and
`TRANSPORT_TOKEN` authenticates the internal exchange. Native AGNTCY and small
JSON-RPC hosts use the same wire contract. The CLI deliberately rejects the
platform stand-in as a real policy. Missing exports fail visibly. Test both
transports against the same fixture, clock, seed, policy and calculator inputs.
Verify peers' policy metadata/image before running; do not compare an LLM's
independent random calls and call differences transport bugs. Use a recorded
sequence for a nondeterministic policy. No live Claude calls are needed here.

The comparison requires nonempty rule-check definitions, every check passing,
and exact identical commitments/pathways. It never creates holds, approves or
commits. Lane A must run the same rule checks over remote results.

## Validation so far

`harvestnet_platform.lane_b:real_rules` adapts the published typed Lane B rules.
Install the reviewed `agents` package alongside this platform package. The input
is Lane B's `AgentInput` unchanged (`{role, draft, facts, turn}`), with the core's
clock and turn number in `turn`; Lane A's earlier form (`turn_context`) is still
read. Organization IDs are the same on the wire and in Lane B (`market`), so the
old `LANE_B_ORGANIZATION_IDS` alias is gone. No donor facts, allocations, clocks
or decisions are invented or rewritten.

Set `LANE_B_CALCULATORS=reviewed_core_module:factory` to a callable returning the
real calculator implementation. The production adapter refuses missing factories
or Lane B's `StandInCalculators`. Pass those settings into each container and the
local comparison process when baking the final reviewed image. `pass` is now an
allowed nonvoting move; the advocate is restricted to counter/pass, consistent
with Lane B's interface. The extra move remains proposed pending contract day.

All **26 recorded Lane B scenarios** match direct rule outputs over five actual
HTTP hosts, including duplicate retries, accept/counter/reject/hold/ask-human/pass
with Lane B's input unchanged. The test uses `lane_b:recorded_rules`, which is
explicitly marked as using stand-in calculators and rejected by the real-join CLI.
CI runs it against the in-repo `agents/`, so it checks the same commit. This proves
real rules can travel over our transport with recorded calculator inputs; it
does not prove commitments/pathways or core rule checks for #21.

Five actual local HTTP endpoints exchanged a synthetic mixed-batch fixture:
300 lb apples, 200 lb romaine, 400 lb potatoes. Outcomes match the same in-process
test policies; missing human approvals give zero synthetic commitments. A
partial outage must retry the identical message. Missing/failing core rule checks
or differing pathways fail comparison. These results establish the platform seam,
not real-agent behavior, a native Directory deployment, or Level 3 performance.
