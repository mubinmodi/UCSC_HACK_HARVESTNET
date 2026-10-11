# Organization transport (#17)

Run `python -m unittest discover -s tests -v`. The tests start five actual HTTP
servers, broadcast A2A JSON-RPC messages, compare responses with the in-process
fallback, retry messages, and reject unauthorized commitment operations.

`compose.platform.yaml` runs one container each for donor, city, rural, eastside,
and advocate. Set a random `TRANSPORT_TOKEN` and run
`docker compose -f compose.platform.yaml up --build -d`. This default uses the
small A2A JSON-RPC host. It is labeled `a2a_jsonrpc`, not native AGNTCY.

For the native AGNTCY host, install `requirements-agntcy.txt` on Linux, set
`ORGANIZATION_ID`, `AGENT_PUBLIC_URL`, and `TRANSPORT_TOKEN`, then run
`python -m harvestnet_platform.agntcy_server`. It wraps the same receiver in the
official App SDK factory/A2A server. No SLIM group chat is used.

## Ordered exchange

Envelope: `event_id`, positive `sequence`, `turn`, and `input` containing `turn`,
`draft` (`version`, `terms`), and deterministic calculator `facts`. One caller
serializes each event, broadcasts the same envelope to all organizations, and
waits for every acknowledgement before advancing. This caller schedules turns;
it has no acceptance, hold, or commitment authority. Sequence order is durable
in each organization's SQLite receipt log. Identical retries return the saved
result; changed retries and sequence gaps fail. After a partial outage, retry the
same envelope. Do not auto-switch to another policy or mode in a running event.

Only the named organization returns a move on its own turn. Moves are proposals:
accept, one structured counter, reject, request own hold, or ask own human.
They never count as human approvals. The advocate cannot vote. There is no
transport commitment endpoint. The shared transport token authenticates trusted
internal dispatch, not a human or an organization approval. Keep it private.

## Discovery

Set `AGENT_ENDPOINTS` to a JSON map of all five organization URLs.
`python -m harvestnet_platform.directory --cold-lb 100 --pickup-at 2026-10-12T02:00:00Z`
uses the labeled local registry when no native address is configured. Reads include
synthetic source, timestamp, cold pounds and pickup hours from systems fixtures.
The registry is not a reservation; a candidate must recheck facts and approve.

With an AGNTCY Directory gRPC daemon, set `AGNTCY_DIRECTORY_ADDRESS=directory:8888`,
install the optional requirements, and run `python -m harvestnet_platform.directory --register`.
All five records use the official OASF A2A module envelope plus HarvestNet
capabilities in annotations. Search reads Directory records, then filters exact
cold capacity and pickup time. Reregister after a capability change. Local
fallback refreshes immediately; native records are snapshots and require owner
rechecks. A live Directory outage fails visibly rather than claiming local results
came from AGNTCY.

Reference implementation inspected at AGNTCY app-sdk 0.5.5:
[factory and server examples](https://github.com/agntcy/app-sdk),
[Directory SDK](https://docs.agntcy.org/dir/directory-sdk/).
Docker/native Directory execution still needs Docker and a configured Directory
daemon; neither is available on this development machine. Local HTTP is tested.
