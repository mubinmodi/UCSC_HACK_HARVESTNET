# Running and deploying the platform

- **Live deployment:** [`deploy/aws/README.md`](../../deploy/aws/README.md). One small EC2 instance runs the whole stack. That page covers setup, redeploy, rollback, logs, reset and teardown.
- **Local rehearsal, no accounts:** below.
- **Fallbacks and the Claude spending cap:** below.

## Local rehearsal

Python 3.12 or newer. From the repository root:

```sh
python -m harvestnet_platform.demo     # then open the URL saved in runtime/demo-url.txt
```

Keep the terminal running. The page has the cooler switch with capability discovery, five organization turns, review links with Approve and Decline, and text intake with a read-back. Every mode is labeled. It is a **platform rehearsal**, not the whole application: it makes no Claude calls, saves no households and commits no produce. Tests: `uv run --with pytest pytest -q` at the root (optional native SDK tests need `requirements-agntcy.txt`).

## Fallbacks

Each one is labeled on screen. Pick one before a run and do not switch inside a running event.

| If this fails | Use | Note |
|---|---|---|
| Beeceptor | The recorded synthetic fixtures (`mode: replay`, with a reason) | [`CONTRACTS.md`](CONTRACTS.md) |
| ElevenLabs | The text form: a validated draft with read-back, awaiting consent | No food is promised by text intake. |
| n8n | The local review page with the exact version and Approve and Decline | A missing core records a decision but cannot commit it ([`APPROVALS.md`](APPROVALS.md)). |
| AGNTCY | `InProcess` transport, visibly labeled | [`TRANSPORT.md`](TRANSPORT.md) |
| Claude, or its cap reached | Rules-based moves and the recorded replay | Live calls are off until a cap is set. |
| The whole deployment | `docs/demo/replay.html`, opened from a laptop | `docs/demo/REHEARSAL.md` |

## Claude spending cap

`CLAUDE_RUN_CAP_USD` (default 0, meaning no live calls; above $100 is refused) is the one setting that authorizes paid calls. Lane B reads it with `SpendingCap.from_env()` for the LLM negotiators (one shared cap per run) and the voice line's front-desk extractor. The core's voice intake also reads it, and needs `ANTHROPIC_API_KEY` (`harvestnet_core/voice.py`).

Before each call the cap reserves a deliberately high worst case and settles the actual cost. If the reservation does not fit, no call is made and the caller falls back to rules or the text form. The cap is **per process**: a restart starts it from zero again. `python -m harvestnet_core evaluate --llm-cap-usd N --allow-paid` has its own cap, shared across that command.

`CLAUDE_TOTAL_CAP_USD` is read only by `harvestnet_platform.budget.Budget`, a durable SQLite ledger with a run cap and a total cap. No live path uses it yet, so the total cap is a team agreement, not enforced code. To enforce it, reserve through `Budget` as well. Conservative bounds are a prerequisite, and neither mechanism is a provider billing cap.

## Secrets and configuration

`deploy/load_secrets.py --secret-id <arn> --region <region>` reads one Secrets Manager JSON secret into `runtime/deploy.env` (mode 0600, Git-ignored), using the instance role. It accepts only the keys in its `ALLOWED` set and single-line values with no single quote or backslash. The AWS setup script does this on the instance.

- Keep secrets in local ignored files or Secrets Manager, never in Git, chat or logs. Do not paste plain `docker compose config`, `docker inspect` or environment dumps; `config --quiet` validates without printing.
- Rotating a secret means recreating the affected containers.
- Never log approval links, household emails, transcripts or SNAP answers.

## The generic Compose overlay

`compose.deployment.yaml` (with `compose.platform.yaml` and `compose.agntcy.yaml`) is a generic overlay: Caddy, a private Postgres and a required `CORE_API_IMAGE`. CI validates its configuration. The live stack does not use it; it uses `deploy/aws/compose.aws.yaml`, with SQLite and no Postgres. Prefer the AWS files. The generic overlay still carries retired settings (`REPLY_BINDING_KEY`, `POSTGRES_PASSWORD`).
