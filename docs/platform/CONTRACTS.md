# Lane C integration contracts

The team's shared contracts are **agreed** (ticket #1, October 11, 2026) and live in
[`docs/contracts/`](../contracts/README.md), with machine-readable examples and the
API skeleton in `api_skeleton/`. Lane C follows them: organization IDs are names
(`market`, not `donor`), times carry an offset (October 13, 2026, `-07:00`), the
transport wraps Lane B's agent input unchanged, approvals post `lot_id` and a
`sha256:` terms hash, and "can't make it" calls `POST /pickups/{pickup_id}/release`.

This page covers Lane C's own internal routes: the organization systems below are
the organizations' *own* systems, so they keep their own field names
(`cold_available_lb`); specialists translate them into the contract's facts
(README decision 4). No mock response is a real household outcome.

## Organization systems (#16)

`GET /systems/{organization}/{resource}` returns `organization_id`, `resource`,
`synthetic: true`, `mode`, `source`, `fixture_version`, `observed_at`, and `data`.
Organizations: `market` (the donor), `city`, `rural`, `eastside`. Resources: market
`inventory` and `truck`; food banks `storage`, `cooler`, `cooler-failed`,
`pickup-hours`, `truck`. The fixture (`fixture_version: synthetic-v2`) is the
complete example and follows the core's normal afternoon (`core_fixtures/normal-afternoon.json`).
Units: pounds, degrees Celsius, ISO 8601 timestamps with an offset. An older export
keyed by `donor` (the core's `cooler_join`) is still read as `market`. Fixture temperature values are synthetic, not safety
thresholds or guidance. Specialist calculators must assess actual condition.

`POST /demo/{bank}/cooler` with `{"failed": true}` selects the synthetic failed
reading and makes cold capacity zero. `false` resets it. Requires bearer
`DEMO_SWITCH_TOKEN`. It affects one bank only. This is demo control, never a
real refrigeration control. Set `COOLER_STATE_PATH` to persist it across restarts.

## Beeceptor setup

1. Run `python -m harvestnet_platform.systems --export-openapi beeceptor.openapi.json`.
2. Import that OpenAPI document into a dedicated Beeceptor mock endpoint; use
   **example responses** (including the explicit `synthetic` label).
3. Set `BEECEPTOR_BASE_URL=https://YOUR-ENDPOINT.free.beeceptor.com`.
4. Run `python -m harvestnet_platform.systems`, then use its authenticated demo
   switch. The adapter reads the matching working/failed Beeceptor mock route;
   it never changes the organization's real system.
5. Verify every route against the examples. An unavailable or incompatible
   response uses its recorded copy and reports `mode: replay` and a fallback reason.

The exported schema intentionally describes external organization systems only,
not HarvestNet's public API. It must not become the authoritative approval store.
Without a connected Beeceptor account the live import remains a setup step;
all recorded endpoints and switch behavior run locally now. The fixture moved to
`synthetic-v2` (the `market` routes and October 13 times), so the live Beeceptor
mock must be re-imported from a fresh export; until then its responses don't match
and every read is the labeled recorded copy.

Agent hosts read their own systems through this service, which applies the demo
switch: set `SYSTEMS_URL=http://systems:8010`. Its labels (`mode`, `source`,
`disruption`) are kept as they are.

Reference: [Beeceptor OpenAPI mocking](https://beeceptor.com/docs/),
[mock rules](https://beeceptor.com/docs/mock-rules/).
