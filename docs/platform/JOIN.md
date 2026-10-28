# Joining the real agents to the transport

The join proves that the real negotiators and the real core give the same outcome whether their moves travel in process or over the five organization hosts ([`TRANSPORT.md`](TRANSPORT.md)). It is a comparison. It never creates holds, approves or commits anything.

```sh
python -m harvestnet_platform.join --fixture core_fixtures/normal-afternoon.json \
  --harness harvestnet_core.join_adapter:harness --policy harvestnet_core.join_adapter:policy
```

Run it with `agents/src` on `PYTHONPATH` and the five hosts up (`python -m harvestnet_platform.join --help` lists the flags). `AGENT_ENDPOINTS` is a JSON map of the five organization URLs. The join signs every turn as the turn publisher, `core`, with `TRANSPORT_SIGNING_KEY` (the `TRANSPORT_SIGNING_KEY_CORE` value from `python -m harvestnet_platform.transport_auth`), and each host checks it ([`TRANSPORT.md`](TRANSPORT.md), per-sender signatures).

## The two adapters

- **Policy**: `module:function(organization_id, input) -> move`. It must be the same deterministic real rules and real calculators locally and inside each host. `input` is Lane B's agent input (`{role, draft, facts, turn}`); no individual household data reaches an agent. The core's export is `harvestnet_core.join_adapter:policy`.
- **Harness**: `module:function(fixture, move_provider) -> run`. Lane A's seeded harness calls `move_provider(organization_id, input)` on every published turn and owns drafts, stops, holds, human approvals and records. The core's export is `harvestnet_core.join_adapter:harness`.

The run must return `commitments`, `pathways` and `rule_checks`, with these boolean checks: `no_double_booking`, `pounds_conserved`, `versioned_approvals`, `no_auto_commit`, `all_pounds_have_pathway`, `zero_invalid_commitments`. Extra boolean checks must pass too. A real harness computes its checks from records; a constant success flag is not a check.

## What the comparison requires

The harness runs twice on the same fixture, clock, seed, policy and calculator inputs: in process, and with every turn sent through `A2ATransport`. It passes only if rule checks are present and all true, and commitments and pathways are exactly identical and non-empty. Anything else raises.

- Bake the policy into the host images, or mount the source read-only, and set `AGENT_POLICY` for each host. Use a fresh event namespace for each run. Receipt stores make retries idempotent, and a partial outage retries the identical envelope.
- The CLI refuses the platform's stand-in and any policy that uses stand-in calculators. A missing export fails visibly.
- Verify the peers' policy image before a run. Do not compare an LLM's independent random calls and call the differences transport bugs; use a recorded sequence for a nondeterministic policy. This join needs no Claude call.

## Lane B's rules on the platform

`harvestnet_platform.lane_b` adapts Lane B's typed rules without changing them:

- `real_rules` needs `LANE_B_CALCULATORS=module:factory`, a callable that returns the real calculators. It refuses a missing factory and Lane B's `StandInCalculators`. Set it in each container and in the comparison process.
- `recorded_rules` uses the stand-in calculators, is marked `uses_stand_in_calculators`, and exists only to prove that Lane B's recorded scenarios travel over HTTP with identical output. The real-join CLI rejects it.
- Organization IDs are the same on the wire and in Lane B (`market`). `pass` is a valid nonvoting move (contract decision 6), and the advocate may only counter or pass.

## What the tests establish

`tests/test_join.py`, `tests/test_lane_b.py` and `core_tests/test_http_integration.py` cover: every recorded Lane B scenario matches its direct rule output over five actual HTTP hosts, including duplicate retries; a synthetic mixed batch (300 lb apples, 200 lb romaine, 400 lb potatoes; `tests/test_join.py`) and the core's real mixed batch (`core_tests/test_http_integration.py`) give identical, non-empty commitments, pathways and checks in process and over five A2A hosts; and missing human approvals give zero commitments. They establish the platform seam. They do not show Level 3 agent behavior, a live Directory, or public HTTPS deployment.
