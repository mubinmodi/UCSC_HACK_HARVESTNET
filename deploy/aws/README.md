# HarvestNet on AWS

One small EC2 instance runs the whole stack with Docker Compose. `setup.sh` creates or updates it, `teardown.sh` removes it. Both are safe to re-run and both take `--dry-run` (read-only AWS calls, and every change printed instead of run). `--help` lists their settings.

| Script | Does |
|---|---|
| `setup.sh` | Creates the resources below and deploys a git ref. Re-run it to redeploy. |
| `teardown.sh` | Deletes everything `setup.sh` created. |
| `reset_data.sh` | Wipes the live demo data and starts a fresh synthetic scenario. |
| `logs.sh [service] [lines]` | Service status, then recent container logs. |
| `check_directory.sh [cold_lb] [pickup_at]` | Checks the live AGNTCY Directory. |
| `set-keys.sh` | Pastes provider keys into `deploy/aws/.env` without echoing them. |

All settings are listed in `env.template`; `lib.sh` holds the shared names and helpers.

## What you need

- The AWS CLI v2, signed in with `aws login --profile incubator`. Sign-ins expire; if a script reports missing or expired credentials, run it again.
- `jq`, `git`, `curl`, `openssl` (macOS has all but `jq`: `brew install jq`). `npm`, only if the ref you deploy has apps under `frontend/`.
- No Docker, SSH key, domain or GitHub token: the instance builds the image itself.

## Run it

```sh
cp deploy/aws/env.template deploy/aws/.env     # Git-ignored; fill it in. set-keys.sh pastes keys safely.
set -a; . deploy/aws/.env; set +a
deploy/aws/setup.sh --dry-run                  # see the plan
deploy/aws/setup.sh
```

`ALERT_EMAIL` is required (it receives the budget alerts), and the ref you deploy must contain `deploy/aws/`. The first run takes about 15 to 25 minutes, mostly Docker installing on the instance. It ends by printing the URLs, the cost estimate and the teardown command, and writes them (no secrets) to `deploy/aws/outputs.json`, which Git ignores. That file is the record of the last deploy from this machine.

Defaults, in `setup.sh`: `PROFILE` incubator, `REGION` us-east-2, `GIT_REF` main, `INSTANCE_TYPE` t4g.micro, `VOLUME_GB` 10, `CPU_CREDITS` standard, `HARVESTNET_DOMAIN` `<ip-with-dashes>.sslip.io`, `CLAUDE_RUN_CAP_USD` 0, `CLAUDE_TOTAL_CAP_USD` equal to the run cap. `BUDGET_USD` defaults to 15 in `setup.sh` but `env.template` sets 45 (the account also runs another stack); a loaded `.env` wins. Provider settings go into the secret only when set.

**Values in `.env`.** The secret holder (`deploy/load_secrets.py`) accepts only single-line strings with no single quote or backslash. When you write a JSON value, wrap it in single quotes so the shell keeps its double quotes, for example `APPROVER_EMAILS_JSON='{"city":"you@example.org"}'`. Unquoted, the shell strips the double quotes and the approvals service crashes while `/api/health` still looks green; `setup.sh` also checks `/platform/health` for this reason.

**Email.** Pickup email needs `N8N_PICKUP_WEBHOOK_URL`, `N8N_RELEASE_WEBHOOK_URL`, `N8N_WEBHOOK_TOKEN` and `SES_TEST_RECIPIENTS`. The core refuses to start with some but not all of them. Human review email also needs `N8N_APPROVAL_WEBHOOK_URL` and `APPROVER_EMAILS_JSON` (organization ID to Staff approver address). Details and the n8n setup: [`docs/platform/APPROVALS.md`](../../docs/platform/APPROVALS.md).

- **SES sandbox.** While the us-east-2 SES account is sandboxed, the From identity and every recipient must be verified. Adding an address to `.env` verifies nothing and sends nothing. Keep `SES_TEST_RECIPIENTS` to verified demo addresses.
- **SMTP credentials** are created in n8n Cloud. The deployment never creates or copies them. Set `SES_SENDER_EMAIL` to the same address as n8n Cloud's `HARVESTNET_EMAIL_FROM` variable; the deployment only stores it for reference.
- **n8n Cloud webhooks** come from the published workflows, not from this repo. The workflows in `integrations/n8n/` are inactive drafts until imported, connected to credentials and published.

## What it creates

Everything is tagged `project=harvestnet`, in us-east-2 unless noted.

| Resource | Name | Why |
|---|---|---|
| AWS Budgets budget (global) | `harvestnet-monthly` | Emails `ALERT_EMAIL` at 50%, 80% and 100% of `BUDGET_USD` a month. Created first. |
| S3 bucket, private | `harvestnet-deploy-<account>-<region>` | Release bundles (a `git archive` of the ref plus the built frontends). Bundles expire after 14 days. |
| Elastic IP | `harvestnet-eip` | A fixed address, so the HTTPS name stays the same. |
| Secrets Manager secret | `harvestnet/platform` | A staff token for each organization, the transport, events and demo-switch tokens (random, made once), the domain and URLs, the Claude caps, and any provider settings you set. |
| IAM role and instance profile | `harvestnet-ec2-role`, `harvestnet-ec2-profile` | `AmazonSSMManagedInstanceCore`, plus read access to that one secret and to `releases/*` in the bucket. |
| Security group | `harvestnet-web` | Inbound 80 and 443 only. No SSH: reach the machine through SSM. |
| EC2 instance | `harvestnet-app` | t4g.micro (Graviton, 1 GB memory plus 1 GB swap), Ubuntu 24.04, 10 GB encrypted gp3, standard CPU credits, IMDSv2 only. |

It creates no NAT gateway, load balancer, RDS database, CloudFront distribution, container registry or CloudWatch log group. The `harvestnet-api-skeleton` Lambda and its role are left alone. The budget covers the whole account (linked accounts cannot use cost-allocation tags), so other spending counts toward it.

## What runs on the instance

All Python services share one image (`Dockerfile`), built once on the instance. Compose files: `compose.platform.yaml` (repo root), `compose.aws.yaml`, `compose.directory.yaml`.

- **The five organization hosts** (`donor` hosting `market`, `city`, `rural`, `eastside`, `advocate`) run the core's real policy (`harvestnet_core.join_adapter:policy`) and register with the Directory.
- **Cooler watchers.** The three food bank hosts also run their own watcher (`COOLER_WATCH=1`, `harvestnet_core/cooler_watch.py`). It polls that food bank's own cooler every `COOLER_WATCH_INTERVAL_SECONDS` (10). When the reading fails, it proposes the new version to the core and asks the approval service for the review emails. It never approves or commits. Each host gets the core's staff-token map and `API_EVENTS_TOKEN` and uses only its own organization's token. Operator commands: `docs/demo/REHEARSAL.md`.
- **`systems`** serves the organization systems and the demo cooler switch. **`approvals`** issues review links and prepares emails. **`core`** is `python -m harvestnet_core.server` on SQLite. See `docs/platform/` for each.
- **`directory`** is the private AGNTCY Directory: the official `dirctl` v1.7.1 daemon (gRPC server and search indexer) with SQLite and a local OCI store on one volume. Only the organization hosts reach `directory:8888`; no port is published. Each host registers its own record and refreshes changed capabilities every 30 seconds. If the Directory is down, hosts keep serving moves and the CLI labels its local fallback. A record is a capability snapshot, so owners recheck before committing. It needs outbound access to the public OASF schema service to accept records. Background: [`docs/platform/TRANSPORT.md`](../../docs/platform/TRANSPORT.md).
- **`gateway`** (Caddy) gets a free certificate for `<elastic-ip-with-dashes>.sslip.io`, a public name that resolves to the IP inside it. For your own domain, point its A record at the Elastic IP and set `HARVESTNET_DOMAIN`.
- **Data** is SQLite in Docker volumes on the instance, lost on teardown. There is no Postgres: RDS would cost more than everything else here.

URLs: core API `https://<host>/api/` (health at `/api/health`), review pages `/human/...`, platform adapters `/platform/...` (health at `/platform/health`), each frontend at `/<app>/` (list at `/apps.txt`), except `frontend/landing`, which is built with base `/` and served at the site root `/` (Caddy tries every other route first). The frontends are built with `VITE_API_BASE_URL=https://<host>/api` and served by Caddy on the same origin. Caddy also proxies exactly `POST /systems/demo/<city|rural|eastside>/cooler` to the systems service, which needs the `DEMO_SWITCH_TOKEN` bearer (401 otherwise); no other systems route is public.

**How a deploy works.** Your laptop runs `git archive` on the ref, builds the frontends, and uploads the bundle to the private bucket. SSM Run Command starts `remote_deploy.sh` on the instance, which downloads the bundle with the instance role, loads the secret into a 0600 file, builds the image and runs `docker compose up`. No GitHub token or AWS key lives on the machine. `user-data.sh` only installs Docker and sets up swap and log limits at first boot (its log: `/var/log/harvestnet-bootstrap.log`).

**Claude spending.** `CLAUDE_RUN_CAP_USD` and `CLAUDE_TOTAL_CAP_USD` go into the secret and the containers; the run cap defaults to 0 (no paid calls), the total cap to the run cap, and above $100 is refused. Both are enforced in code: the run cap in memory per process, and the total cap against the persistent spend ledger, `/app/budget/claude-spend.json` (`CLAUDE_SPEND_LEDGER`, set for the core in `compose.aws.yaml`) on the `budget-data` volume. The ledger survives restarts, deploys and `reset_data.sh`, which keeps `budget-data`; `teardown.sh` deletes it with the instance, so after a fresh `setup.sh` seed it again. Every paid caller goes through it: voice intake, the LLM negotiators and `evaluate --llm-cap-usd`. Seed or inspect it on the instance (SSM Session Manager, as root) with `cd /opt/harvestnet/current && export HARVESTNET_RELEASE=$(cat /opt/harvestnet/current-release) && docker compose -p harvestnet --env-file /opt/harvestnet/deploy.env -f compose.platform.yaml -f deploy/aws/compose.aws.yaml -f deploy/aws/compose.directory.yaml exec -T core python -m harvestnet_agents.spend_ledger add 9.92 --note "Oct 11 runs, upper bound"` (or `show` in place of `add ...`). Costs are token-usage estimates, not a provider billing cap ([`docs/platform/DEPLOYMENT.md`](../../docs/platform/DEPLOYMENT.md)). Voice intake (`POST /api/voice-intake`) turns on only with `ANTHROPIC_API_KEY` set and a run cap above 0; otherwise it answers 503 and households use the text form. Example: `ANTHROPIC_API_KEY=... CLAUDE_RUN_CAP_USD=2 CLAUDE_TOTAL_CAP_USD=5 deploy/aws/setup.sh`. `ELEVENLABS_API_KEY` is stored in the secret but no container reads it; `integrations/elevenlabs/sync_agent.py` takes it from your environment.

## Monthly cost estimate

An **estimate**, not a bill: on-demand us-east-2 prices from the AWS Price List API (checked 2026-10-11), 730 hours, default settings.

| Item | Price used | Per month |
|---|---|---|
| EC2 t4g.micro | $0.0084/hour | $6.13 |
| Public IPv4 (the Elastic IP) | $0.005/hour | $3.65 |
| EBS gp3, 10 GB | $0.08/GB-month | $0.80 |
| Secrets Manager, 1 secret | $0.40/secret-month, plus $0.05 per 10,000 calls | $0.40 |
| S3 bundles (a few MB) | | about $0.01 |
| Data transfer out | first 100 GB/month to the internet is free | $0 for a demo |
| SSM, AWS Budgets alerts | free | $0 |
| CPU credits | standard mode never bills extra | $0 |
| **Total** | | **about $11/month (about $0.37/day)** |

`INSTANCE_TYPE=t4g.small` (2 GB, $0.0168/hour) brings it to about $17. `CPU_CREDITS=unlimited` boots faster, but sustained CPU above baseline costs $0.04 per vCPU-hour. Claude and any other provider usage is separate.

## Redeploy, roll back, change settings

```sh
GIT_REF=<branch, tag or SHA> ALERT_EMAIL=you@example.org deploy/aws/setup.sh
```

A branch name means the pushed branch on `origin` (the script runs `git fetch origin` first; `NO_FETCH=1` skips it). The script finds the existing resources and sends the instance a new bundle. Containers are recreated and data volumes are kept. To roll back, deploy the earlier SHA. To set a new provider key or setting, set it in the environment and re-run. To change the instance size, stop the instance, change its type and start it again (the script prints the command). Do not run `docker compose down -v` on the instance: the volumes hold approvals and core data.

## Logs and checks

```sh
deploy/aws/logs.sh              # status of every service, then the last 50 lines of each
deploy/aws/logs.sh core 200     # one service
deploy/aws/check_directory.sh   # registrations, a cold-space search, memory use
```

These use SSM Run Command, so they need no plugin. `check_directory.sh` changes nothing; it exits 0 only when both its registration list and its capability search came from the AGNTCY Directory, and otherwise prints the labeled fallback and fails. `check_directory.sh 250 2026-10-13T17:30:00-07:00` changes the cold-space threshold and pickup time. A pass verifies the daemon's current answer, not that cooler changes or approvals work end to end. For a shell, install the Session Manager plugin and run `aws ssm start-session --profile incubator --region us-east-2 --target <instance-id>`. Container logs stay on the machine, capped at 30 MB per container.

To read one organization's staff token into your own terminal (never into Git, chat or a household page):

```sh
aws secretsmanager get-secret-value --profile incubator --region us-east-2 --secret-id harvestnet/platform \
  --query SecretString --output text | jq -r '.HARVESTNET_STAFF_TOKENS | fromjson | .city'
```

## Reset the demo data

`deploy/aws/reset_data.sh` (`--dry-run` to preview, `--yes` to skip the prompt) deletes the core records, review links, cooler state and each organization host's data, restarts the services on a fresh synthetic scenario, and re-publishes the free rules-based evaluation (the LLM method shows not run). It keeps the Claude ledger volume, the Directory, the HTTPS certificates and every AWS resource. Re-run a paid evaluation afterwards if you want LLM results (`docs/core/README.md`, Evaluation).

## Tear it down

```sh
deploy/aws/teardown.sh --dry-run   # see what would be deleted
deploy/aws/teardown.sh             # asks you to type "delete harvestnet"
```

It deletes the instance with its disk and data, the Elastic IP, the security group, the IAM role and profile, the bucket and its bundles, the secret, the budget, and the SES SMTP IAM user `harvestnet-ses-smtp` (created by hand for n8n email). With `SES_SENDER_EMAIL` set, it also deletes that SES sender identity. The secret stays recoverable for 7 days, and re-running `setup.sh` restores it. Flags: `--yes` skips the prompt, `--purge-secret` deletes the secret at once, `--keep-budget` keeps the alert, `--include-skeleton` also deletes the `harvestnet-api-skeleton` Lambda, its URL, logs and role. It never touches other stacks in the account (for example `clinical-trials-viz`).

## Known limits

- `sslip.io` certificates depend on a free public DNS service and on Let's Encrypt rate limits. If Caddy cannot get a certificate, use a real domain.
- A t4g.micro has 1 GB of memory. Eight small Python services use about 35 MB each when idle (measured locally), and the Directory daemon has a 256 MB ceiling. Actual full-stack memory use on the instance is reported by `check_directory.sh`. If it runs short, use `INSTANCE_TYPE=t4g.small`.
