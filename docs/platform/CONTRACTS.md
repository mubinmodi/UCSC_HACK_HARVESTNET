# Organization systems

The shared interfaces (scenario fixtures, agent moves, calculators, public API) are in [`docs/contracts/`](../contracts/README.md), and the platform follows them. This page covers the platform's own service: the **organization systems**, which stand in for each organization's real systems (inventory, storage, cooler, pickup hours, trucks).

An organization's system keeps its own field names (`cold_available_lb`). Its specialist translates them into the contract's facts (`cold_free_lb`, contract decision 4), so no field here is a contract field. Every reading is synthetic and labeled so; none is a real household or food safety outcome.

## Routes

`python -m harvestnet_platform.systems` (port 8010; `--host 0.0.0.0` in a container) serves:

- `GET /systems/{organization}/{resource}` returns `organization_id`, `resource`, `synthetic: true`, `mode`, `source`, `fixture_version`, `observed_at` and `data`. Organizations come from `harvestnet_platform/roster.py`. Resources: `market` has `inventory` and `truck`; each food bank (`city`, `rural`, `eastside`) has `storage`, `cooler`, `cooler-failed`, `pickup-hours` and `truck`.
- `POST /demo/{bank}/cooler` with `{"failed": true}` selects the failed reading for that one bank and makes its cold capacity zero. `false` resets it. It needs the `DEMO_SWITCH_TOKEN` bearer. It is demo control and never touches real refrigeration. `COOLER_STATE_PATH` keeps the state across restarts.
- `GET /openapi.json`, or `--export-openapi FILE`, describes the readings for Beeceptor.

The fixture is `harvestnet_platform/fixtures/systems.json`. It follows the core's normal afternoon (`core_fixtures/normal-afternoon.json`): October 13, 2026, `-07:00`. Units are pounds, degrees Celsius and ISO 8601 times with an offset. Temperatures are synthetic and are not safety thresholds; specialists must assess actual condition.

## Who reads it

Agent hosts read their own organization's systems through this service (`SYSTEMS_URL=http://systems:8010`), so the demo switch applies to them. The service's labels (`mode`, `source`, `disruption`) pass through unchanged. Without `SYSTEMS_URL`, a host reads Beeceptor (`BEECEPTOR_BASE_URL`) directly, or the recorded copy.

## Beeceptor

1. `python -m harvestnet_platform.systems --export-openapi beeceptor.openapi.json`
2. Import it into a dedicated Beeceptor mock endpoint and use the **example responses**, which carry the `synthetic` label.
3. Set `BEECEPTOR_BASE_URL=https://YOUR-ENDPOINT.free.beeceptor.com` and start the service.
4. Verify each route against the examples.

The mock must match the fixture exactly: a reading is accepted only if it is labeled synthetic, names the same organization and resource, carries the fixture's `fixture_version`, and has the same fields and field types as the recorded copy. Anything else falls back to the recorded copy with `mode: replay` and a `fallback_reason`. **Re-import the mock from a fresh export whenever the fixture changes**; until then every read is the labeled recorded copy.

The exported schema describes the organizations' external systems only, not HarvestNet's public API, and never becomes an approval store.
