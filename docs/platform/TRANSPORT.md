# Organization transport (#17)

Run `python -m unittest discover -s tests -v`. The tests start five actual HTTP
servers, broadcast A2A JSON-RPC messages, compare responses with the in-process
fallback, retry messages, and reject unauthorized commitment operations.

`compose.platform.yaml` runs one container each for `market` (the donor), `city`,
`rural`, `eastside`, and `advocate`. Organization IDs are names, not roles
(contract decision 1). The donor's container keeps the service name `donor`
(`http://donor:8020`) so deployment overlays still match; it hosts `market`. Set a random `TRANSPORT_TOKEN` and run
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

On AWS, `deploy/aws/compose.directory.yaml` adds a private AGNTCY Directory
daemon at `directory:8888`. The five A2A JSON-RPC hosts install the Directory SDK;
each host registers its own OASF A2A record at startup and re-reads its own systems
(through `SYSTEMS_URL`, including the demo cooler switch) every
`DIRECTORY_REFRESH_SECONDS` (default 30). Changed capabilities publish a new
record and remove the old one. Search keeps the newest record per Organization and
filters cold capacity and pickup time. These are snapshots, so the owner still
rechecks current facts and reservations before any commitment.

For a manually configured Directory, set `AGNTCY_DIRECTORY_ADDRESS` and install
the Directory SDK from `requirements-agntcy.txt`. `python -m
harvestnet_platform.directory --register` remains a manual way to seed all five
synthetic records; the AWS hosts do not need it. Use `--list` to see registrations
or `--brief --cold-lb 100 --pickup-at 2026-10-13T19:00:00-07:00` to query matches.
If the gRPC Directory is unreachable and `AGENT_ENDPOINTS` is available, the CLI
prints a labeled `local_directory_fallback` and exits 2. It never presents those
local results as AGNTCY records.

Reference implementation inspected at AGNTCY app-sdk 0.5.5:
[factory and server examples](https://github.com/agntcy/app-sdk),
[Directory SDK](https://docs.agntcy.org/dir/directory-sdk/).
The native App SDK process was also started successfully and exchanged an
authenticated A2A message in a subprocess test. The AWS overlay uses the official
`dirctl daemon`, which includes the gRPC server and search indexer; the standalone
apiserver needs a separate reconciler ([AGNTCY local deployment](https://docs.agntcy.org/dir/dir-deployment-local/)).
Compose syntax and mock SDK behavior are tested. Live Directory push/search on the
AWS instance is still unverified because this session has no Docker daemon or AWS
deployment access. `deploy/aws/check_directory.sh` is the post-deploy check.
