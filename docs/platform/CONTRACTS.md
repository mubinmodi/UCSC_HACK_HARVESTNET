# Lane C integration contracts

These are version `platform-v1` **proposed contracts**, derived from the MVP design.
Ticket #1 has no implementation or agreed machine-readable contract yet. Lane A/B
can supply adapters without changing these platform modules. No mock response is
claimed to be a real household outcome or a team-approved interface.

## Organization systems (#16)

`GET /systems/{organization}/{resource}` returns `organization_id`, `resource`,
`synthetic: true`, `mode`, `source`, `fixture_version`, `observed_at`, and `data`.
Organizations: `donor`, `city`, `rural`, `eastside`. Resources: donor `inventory`
and `truck`; banks `storage`, `cooler`, `cooler-failed`, `pickup-hours`, `truck`.
The fixture is the complete example contract. Units: pounds, degrees Celsius,
UTC ISO-8601 timestamps. Fixture temperature values are synthetic, not safety
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
all recorded endpoints and switch behavior run locally now.

Reference: [Beeceptor OpenAPI mocking](https://beeceptor.com/docs/),
[mock rules](https://beeceptor.com/docs/mock-rules/).
