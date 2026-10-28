# Running and deploying the platform

- **Live deployment:** [`deploy/aws/README.md`](../../deploy/aws/README.md). One small EC2 instance runs the whole stack. That page covers setup, redeploy, rollback, logs, reset and teardown.
- **Local rehearsal, no accounts:** below.
- **Fallbacks and the Claude spending cap:** below.

## Local rehearsal

Python 3.12 or newer. From the repository root:

```sh
python -m harvestnet_platform.demo     # then open the URL saved in runtime/demo-url.txt
```

Keep the terminal running. The page has the cooler switch with capability discovery, five organization turns, review links with Approve and Decline, and text intake with a read-back. Every mode is labeled. It is a **platform rehearsal**, not the whole application: it makes no Claude calls, saves no households and commits no produce.

## Tests

`uv run --with pytest pytest -q` at the root runs every platform test, including the Lane B compatibility tests (`tests/test_lane_b.py`), which use the in-repo `agents/src` and its recorded negotiator fixtures. Three tests need optional SDKs and **skip loudly** (`-rs` prints why) unless they are installed; CI installs them in its own jobs:

| Test | Needs | Run it locally (downloads the pinned packages from PyPI once) |
|---|---|---|
| `tests/test_sdk_compatibility.py` (2 tests) | `a2a-sdk`, `agntcy-dir` | `uv run --with pytest --with a2a-sdk==0.3.20 --with agntcy-dir==1.0.0 pytest -q tests/test_sdk_compatibility.py` |
| `tests/test_native_agntcy.py` (2 tests: the native host's signature check, and its signed reply to the core's move request) | `agntcy-app-sdk` (Linux in CI; also installs on macOS) | `uv run --with pytest --with-requirements requirements-agntcy.txt pytest -q tests/test_native_agntcy.py` |

`tests/test_aws_deploy.py` also skips its shellcheck test when `shellcheck` is not installed, and the compose-config tests when Docker is not.

## Fallbacks

Each one is labeled on screen. Pick one before a run and do not switch inside a running event.

| If this fails | Use | Note |
|---|---|---|
| Beeceptor | The recorded synthetic fixtures (`mode: replay`, with a reason) | [`CONTRACTS.md`](CONTRACTS.md) |
| ElevenLabs | The text form: a validated draft with read-back, awaiting consent | No food is promised by text intake. |
| n8n | The local review page with the exact version and Approve and Decline | A missing core records a decision but cannot commit it ([`APPROVALS.md`](APPROVALS.md)). |
| AGNTCY | A host that cannot answer: that turn's move is made in process, recorded as `in_process_fallback` with the reason. The whole stack: `HARVESTNET_MOVE_TRANSPORT=in_process`, labeled in the core log | [`TRANSPORT.md`](TRANSPORT.md) |
| Claude, or its cap reached | Rules-based moves and the recorded replay | Live calls are off until a cap is set. |
| The whole deployment | `docs/demo/replay.html`, opened from a laptop | `docs/demo/REHEARSAL.md` |

## Claude spending cap

Two settings authorize paid calls, and both are enforced in code by `SpendingCap` (`agents/src/harvestnet_agents/llm_negotiators.py`):

- `CLAUDE_RUN_CAP_USD` (default 0, meaning no live calls; above $100 is refused) is the **run cap**, in memory per process.
- `CLAUDE_TOTAL_CAP_USD` is the **total cap** on cumulative actual spend across runs, restarts and callers. Unset, it defaults to the run cap; 0 means no paid calls.

The total is kept in the **spend ledger**, a JSON file at `CLAUDE_SPEND_LEDGER` (`harvestnet_agents/spend_ledger.py`; default `runtime/claude-spend.json`, `/app/budget/claude-spend.json` on AWS, on the `budget-data` volume). Entries hold only a time, a caller label, a model and a cost, never prompts or personal data. Writes take a file lock and replace the file atomically, so concurrent processes lose no entries.

Every live caller goes through `SpendingCap.from_env()`: the LLM negotiators, the voice line's front-desk extractor (the core's voice intake also needs `ANTHROPIC_API_KEY`, `harvestnet_core/voice.py`), and `python -m harvestnet_core evaluate --llm-cap-usd N --allow-paid` (where `N` stays the per-run cap). Before each call the cap reserves a deliberately high worst case against **both** caps and, after the call, records the actual cost in the ledger. If the reservation does not fit either cap, or the ledger cannot be read or written, no call is made and the caller falls back to rules or the text form.

Spending that happened before the ledger existed is recorded by hand: `python -m harvestnet_agents.spend_ledger add 9.92 --note "Oct 11 runs, upper bound"` (`show` prints the entries and total). The ledger survives `deploy/aws/reset_data.sh` but not `teardown.sh`, which deletes the instance's disk; re-seed it after a fresh `setup.sh`. The costs are estimates from token usage and a price table, and neither cap is a provider billing cap.

## Secrets and configuration

`deploy/load_secrets.py --secret-id <arn> --region <region>` reads one Secrets Manager JSON secret into `runtime/deploy.env` (mode 0600, Git-ignored), using the instance role. It accepts only the keys in its `ALLOWED` set and single-line values with no single quote or backslash. The AWS setup script does this on the instance.

- Keep secrets in local ignored files or Secrets Manager, never in Git, chat or logs. Do not paste plain `docker compose config`, `docker inspect` or environment dumps; `config --quiet` validates without printing.
- Rotating a secret means recreating the affected containers.
- Never log approval links, household emails, transcripts or SNAP answers.

- Each holder gets only its own credential: an organization host its own staff token and transport keys, the approval bridge a decision-only credential, the core the full staff-token map it checks ([`deploy/aws/README.md`](../../deploy/aws/README.md), "Credentials, one per holder").
- For local Compose runs, `python -m harvestnet_platform.transport_auth --output runtime/transport.env` writes new per-sender transport keys and each host's derived values to a new 0600 file; load it before `docker compose -f compose.platform.yaml ... up`.

## Compose files

The live stack is `compose.platform.yaml` (the five organization hosts) with `deploy/aws/compose.aws.yaml` and `deploy/aws/compose.directory.yaml`, on SQLite with no Postgres. The core requests every live move from the hosts over signed A2A (`HARVESTNET_MOVE_TRANSPORT=a2a`). `HARVESTNET_ORG_HOST=harvestnet_platform.agntcy_server` runs the native AGNTCY SDK host in the same containers, with the same arguments; `compose.agntcy.yaml` does the same for a local stack. The older generic overlay (`compose.deployment.yaml`, with Postgres, a separate core image, retired SMS settings and its own `deploy/Caddyfile`) was removed: nothing ran it, and the AWS files replace it.
