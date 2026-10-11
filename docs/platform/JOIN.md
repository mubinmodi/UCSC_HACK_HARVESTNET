# Join real agents over A2A (#21)

The transport/core seam is ready; **the actual join remains blocked on #20 and
the shared contracts**. None of the remote branches currently contains Lane A's
real harness or Lane B's real negotiators. A synthetic seam test is explicitly
not claimed as completion of issue #21.

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

`AGENT_ENDPOINTS` is a JSON map with donor/city/rural/eastside/advocate URLs and
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

Five actual local HTTP endpoints exchanged a synthetic mixed-batch fixture:
300 lb apples, 200 lb romaine, 400 lb potatoes. Outcomes match the same in-process
test policies; missing human approvals give zero synthetic commitments. A
partial outage must retry the identical message. Missing/failing core rule checks
or differing pathways fail comparison. These results establish the platform seam,
not real-agent behavior, a native Directory deployment, or Level 3 performance.
