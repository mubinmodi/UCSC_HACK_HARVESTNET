# Organization transport (#17)

Run `python -m unittest discover -s tests -v`. The tests start five actual HTTP
servers, broadcast A2A JSON-RPC messages, compare responses with the in-process
fallback, retry messages, and reject unauthorized commitment operations.

`compose.platform.yaml` runs one container each for `market` (the donor), `city`,
`rural`, `eastside`, and `advocate`. Organization IDs are names, not roles
(contract decision 1). Set a random `TRANSPORT_TOKEN` and run
`docker compose -f compose.platform.yaml up --build -d`. This default uses the
small A2A JSON-RPC host. It is labeled `a2a_jsonrpc`, not native AGNTCY.

For the native AGNTCY host, install `requirements-agntcy.txt` on Linux, set
`ORGANIZATION_ID`, `AGENT_PUBLIC_URL`, and `TRANSPORT_TOKEN`, then run
`python -m harvestnet_platform.agntcy_server`. It wraps the same receiver in the
official App SDK factory/A2A server. No SLIM group chat is used.

## Ordered exchange

Envelope: `event_id` (the lot ID, contract decision 7), positive `sequence`, `turn`
(the organization ID), and `input`, which is Lane B's agent input unchanged:
`{role, draft, facts, turn}` with `turn: {organization_id, number, now,
accepted_by}` (contract decision 5). Lane A's earlier form (`turn` as the ID plus
`turn_context`) is still accepted. One caller serializes each event, broadcasts
the envelope to all organizations, and waits for every acknowledgement before
advancing. **Only the organization whose turn it is receives `facts`**: every other
host gets the same envelope without them, and a host refuses another
organization's facts (agent-moves.md: "this organization's own ... and nobody
else's").

Each HTTP turn waits up to `AGENT_TURN_TIMEOUT_SECONDS` (default 60), long enough
for a live Claude turn. Other service calls use `HARVESTNET_HTTP_TIMEOUT_SECONDS`
(default 10). This caller schedules turns;
it has no acceptance, hold, or commitment authority. Sequence order is durable
in each organization's SQLite receipt log. Identical retries return the saved
result; changed retries and sequence gaps fail. After a partial outage, retry the
same envelope. Do not auto-switch to another policy or mode in a running event.

Only the named organization returns a move on its own turn. Moves are proposals
and follow `docs/contracts/agent-moves.md`: accept, a counter with exactly one
amendment (`set_pounds`, `shift_pounds` or `set_transport`, with its fields),
reject, request own hold (with at least one hold), ask own human, or pass. Other
moves carry no amendment and no holds.
They never count as human approvals. The advocate cannot vote. There is no
transport commitment endpoint. The shared transport token authenticates trusted
internal dispatch, not a human or an organization approval. Keep it private.

## Discovery

Set `AGENT_ENDPOINTS` to a JSON map of all five organization URLs.
`python -m harvestnet_platform.directory --cold-lb 100 --pickup-at 2026-10-13T19:00:00-07:00`
uses the labeled local registry when no native address is configured. Reads include
synthetic source, timestamp, cold pounds and pickup hours from systems fixtures.
The registry is not a reservation; a candidate must recheck facts and approve.

With an AGNTCY Directory gRPC daemon, set `AGNTCY_DIRECTORY_ADDRESS=directory:8888`,
install the optional requirements, and run `python -m harvestnet_platform.directory --register`.
All five records use the official OASF A2A module envelope plus HarvestNet
capabilities in annotations. Search reads Directory records, then filters exact
cold capacity and pickup time. Each native host keeps its own record current:
it re-reads its own systems (through `SYSTEMS_URL`, which applies the demo cooler
switch) every `DIRECTORY_REFRESH_SECONDS` (default 30), publishes a new record when
its capabilities change (a failed cooler drops cold space to zero), and deletes
the old one. If a stale record survives, search keeps only each organization's
newest. Local fallback refreshes immediately; native records are still snapshots
and require owner rechecks. A live Directory outage fails visibly rather than claiming local results
came from AGNTCY.

Reference implementation inspected at AGNTCY app-sdk 0.5.5:
[factory and server examples](https://github.com/agntcy/app-sdk),
[Directory SDK](https://docs.agntcy.org/dir/directory-sdk/).
The native App SDK process was also started successfully and exchanged an
authenticated A2A message in a subprocess test. Docker/native Directory execution
still needs Docker Engine and a configured Directory daemon; neither is available
on this development machine. Compose syntax is validated separately.
