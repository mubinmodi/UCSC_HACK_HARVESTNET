# Organization hosts, transport and discovery

Each organization with an agent (`market`, `city`, `rural`, `eastside`, `advocate`; list in `harvestnet_platform/roster.py`) runs its own host. A host receives published turns, runs its negotiator's policy on them, and returns one proposal. It has no way to accept, hold or commit for anyone: there is no commit endpoint, and the shared `TRANSPORT_TOKEN` only authenticates trusted internal dispatch. It is not a human or an organization approval, so keep it private.

## What runs

- **Default host:** `python -m harvestnet_platform.transport --organization <id>` is a small A2A JSON-RPC host, labeled `a2a_jsonrpc`. `compose.platform.yaml` runs one container per organization. The donor's container keeps the service name `donor` (`http://donor:8020`) and hosts `market`.
- **Native AGNTCY host:** `python -m harvestnet_platform.agntcy_server` wraps the same receiver in the official App SDK (`requirements-agntcy.txt`, Linux). `compose.agntcy.yaml` runs it. It needs `ORGANIZATION_ID`, `AGENT_PUBLIC_URL` and `TRANSPORT_TOKEN`. No SLIM group chat is used.
- **Policy:** `AGENT_POLICY=module:function` selects the policy a host runs. Without it a host answers with a labeled synthetic stand-in (`ask_human`, or `pass` for the advocate), which is only for transport tests.
- **On AWS** the hosts are the JSON-RPC ones with the Directory SDK, running the core's real policy (`AGENT_POLICY=harvestnet_core.join_adapter:policy`). The three food bank hosts also run their own cooler watcher (`COOLER_WATCH=1`, `harvestnet_core/cooler_watch.py`). See [`deploy/aws/README.md`](../../deploy/aws/README.md).

**How it fits.** The deployed core negotiates its live offers in process, with the same real policy and calculators the hosts run. The A2A hosts are the transport seam: `harvestnet_platform.join` runs one fixture in process and over the five hosts and requires identical outcomes ([`JOIN.md`](JOIN.md)). They also publish the Directory records that food banks search when a cooler fails. Do not assume a live lot's turns travel over A2A.

## Ordered exchange

The envelope is `event_id` (the lot ID, contract decision 7), a positive `sequence`, `turn` (the organization ID) and `input`, which is Lane B's agent input unchanged: `{role, draft, facts, turn}` with `turn: {organization_id, number, now, accepted_by}` ([agent moves](../contracts/agent-moves.md)). The core's harness sends `turn` as the organization ID and the turn object in `turn_context`; the transport accepts both forms.

- One caller serializes each event, broadcasts the envelope to every organization, and waits for every acknowledgement before advancing.
- **Only the organization whose turn it is receives `facts`.** Every other host gets the envelope without them, and a host refuses another organization's facts.
- Only the acting organization returns a move. Moves are proposals as in `docs/contracts/agent-moves.md`: accept, counter (exactly one amendment), reject, request its own hold, ask its own human, or pass. The advocate may only counter or pass. None counts as a human approval.
- Sequence order is durable in each host's SQLite receipt log (`RECEIPTS_DB`). An identical retry returns the saved result; a changed retry or a sequence gap fails. After a partial outage, retry the same envelope. Never switch policy or mode inside a running event.
- A turn waits up to `AGENT_TURN_TIMEOUT_SECONDS` (default 60, long enough for a live Claude turn). Other service calls use `HARVESTNET_HTTP_TIMEOUT_SECONDS` (default 10). Plain HTTP outside localhost needs `ALLOW_INTERNAL_HTTP=1`, which the Compose stacks set for the Docker network.

## Discovery

The Directory answers "who has cold space and pickup hours for this lot", as a snapshot. It is not a reservation: the candidate rechecks its current facts and holds before anything commits.

- **Records.** Each host registers its own OASF record at startup. It re-reads its own systems every `DIRECTORY_REFRESH_SECONDS` (default 30); a changed capability publishes a new record and removes the old one. Search keeps the newest record per organization and filters cold capacity and pickup time.
- **AWS.** `deploy/aws/compose.directory.yaml` adds a private AGNTCY Directory daemon at `directory:8888` (the official `dirctl daemon`, which includes the search indexer; the standalone apiserver needs a separate reconciler, per the [AGNTCY local deployment guide](https://docs.agntcy.org/dir/dir-deployment-local/)). `deploy/aws/check_directory.sh` is the post-deploy check.
- **Elsewhere.** Set `AGNTCY_DIRECTORY_ADDRESS` and install the SDK from `requirements-agntcy.txt`.
- **The CLI.** `python -m harvestnet_platform.directory --list`, `--brief --cold-lb 100 --pickup-at 2026-10-13T19:00:00-07:00`, or `--register` (seeds all five synthetic records by hand; needs `AGNTCY_DIRECTORY_ADDRESS` and `AGENT_ENDPOINTS`, a JSON map of organization to URL).
- **Fallback.** With no Directory address the CLI uses the local registry and says so (`local_directory_fallback`). If a configured Directory is unreachable and `AGENT_ENDPOINTS` is set, it prints the labeled fallback and exits 2. A fallback result is never presented as an AGNTCY result.

References: [AGNTCY app-sdk](https://github.com/agntcy/app-sdk), [Directory SDK](https://docs.agntcy.org/dir/directory-sdk/).
