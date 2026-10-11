# HarvestNet on AWS

One small EC2 machine runs the whole stack with Docker Compose. `setup.sh` creates it, `teardown.sh` removes it. Both are safe to re-run, and both have `--dry-run`. This is the "redeploy steps any teammate can follow" part of ticket #19.

## What you need

- The AWS CLI v2, signed in: `aws login --profile incubator`. Sign-ins expire. If a script says your credentials are missing or expired, run that command again.
- `jq`, `git`, `curl`, `openssl` (already on macOS, except `jq`: `brew install jq`).
- `npm`, only if the git ref you deploy has apps under `frontend/`.
- You don't need Docker, SSH keys, a domain or a GitHub token. The machine builds the image itself.

## Run it

All settings and optional provider keys are listed in `deploy/aws/env.template`. To paste API keys without them showing on screen, run `deploy/aws/set-keys.sh` in a terminal. Copy it to `deploy/aws/.env` (gitignored), fill it in, then load it with `set -a; . deploy/aws/.env; set +a` before the commands below.

```sh
ALERT_EMAIL=you@example.org deploy/aws/setup.sh --dry-run   # see the plan first
ALERT_EMAIL=you@example.org deploy/aws/setup.sh
```

`ALERT_EMAIL` is required: it gets the budget alerts. The git ref you deploy must contain `deploy/aws/`.

The first run takes about 15 to 25 minutes, mostly the machine installing Docker. At the end it prints the URLs, the monthly cost estimate and the teardown command, and writes them to `deploy/aws/outputs.json` (no secrets; ignored by Git).

Optional settings (defaults in brackets): `PROFILE` [incubator], `REGION` [us-east-2], `GIT_REF` [main], `BUDGET_USD` [15], `INSTANCE_TYPE` [t4g.micro], `VOLUME_GB` [10], `CPU_CREDITS` [standard], `HARVESTNET_DOMAIN` [`<ip>.sslip.io`], `CLAUDE_RUN_CAP_USD` [0], `CLAUDE_TOTAL_CAP_USD` [same as the run cap]. Provider settings are stored in the secret only when set. For pickup email, set `N8N_PICKUP_WEBHOOK_URL`, `N8N_RELEASE_WEBHOOK_URL`, `N8N_WEBHOOK_TOKEN`, and `SES_TEST_RECIPIENTS`. For human review email, also set `N8N_APPROVAL_WEBHOOK_URL` and `APPROVER_EMAILS_JSON` (organization ID to authorized staff address). `SES_SENDER_EMAIL` is stored for configuration reference; set the same address as n8n Cloud's `HARVESTNET_EMAIL_FROM` variable. Run `deploy/aws/setup.sh --help` for the list.

SES SMTP credentials must be created in n8n Cloud; the deployment does not create or copy them. The From identity and all recipients need verification while the us-east-2 SES account is in its sandbox. Adding addresses to `.env` alone does not verify them or send mail. The workflows in `integrations/n8n/` are inactive drafts until imported, connected to credentials, and published. Keep `SES_TEST_RECIPIENTS` limited to verified demo addresses.

## What it creates

Everything is tagged `project=harvestnet`, in us-east-2 unless noted.

| Resource | Name | Why |
|---|---|---|
| AWS Budgets budget (global) | `harvestnet-monthly` | Emails `ALERT_EMAIL` at 50%, 80% and 100% of $15/month. It is created first. |
| S3 bucket, private | `harvestnet-deploy-<account>-<region>` | Holds release bundles (a `git archive` of the ref plus the built frontends). Old bundles expire after 14 days. |
| Elastic IP | `harvestnet-eip` | A fixed address, so the HTTPS name stays the same. |
| Secrets Manager secret | `harvestnet/platform` | Staff tokens for each organization, the transport, events and demo-switch tokens (random, made once), the domain and URLs, the Claude caps, and any provider keys you set. |
| IAM role and instance profile | `harvestnet-ec2-role`, `harvestnet-ec2-profile` | `AmazonSSMManagedInstanceCore`, plus read access to that one secret and to `releases/*` in the bucket. Nothing else. |
| Security group | `harvestnet-web` | Inbound 80 and 443 only. No SSH: you reach the machine through SSM. |
| EC2 instance | `harvestnet-app` | t4g.micro (Graviton, 1 GB memory plus 1 GB swap), Ubuntu 24.04, 10 GB encrypted gp3, standard CPU credits, IMDSv2 only. |

It does not create a NAT gateway, load balancer, RDS database, CloudFront distribution, container registry or CloudWatch log group. The `harvestnet-api-skeleton` Lambda and its role are left alone.

## How it runs

- **Containers:** the five organization hosts from `compose.platform.yaml` (real policy adapter), plus `systems`, `approvals`, the core API (`python -m harvestnet_core.server`), Caddy, and a private AGNTCY Directory. All Python services use one image, `deploy/aws/Dockerfile`. See `deploy/aws/compose.aws.yaml` and `deploy/aws/compose.directory.yaml`.
- **Directory:** the pinned official `dirctl` v1.7.1 image runs the gRPC server and search indexer with SQLite and a local OCI store on one persistent Docker volume. Only the organization hosts can reach `directory:8888`; no Directory port is published. Each host registers its own OASF record and refreshes changed capabilities every 30 seconds. Its Directory SDK is pinned in `requirements-agntcy.txt`. If the Directory is unavailable, host moves continue and the diagnostic CLI labels its local registry fallback. A Directory record is a capability snapshot; owners recheck resources before commitments. This shares the existing EC2 instance, with no additional AWS resource or separate service charge. The [AGNTCY local deployment guide](https://docs.agntcy.org/dir/dir-deployment-local/) explains why the full daemon includes a reconciler and the standalone apiserver does not.
- **Data:** the core uses SQLite on the instance's disk (`DATABASE_URL`), which the core supports. There is no Postgres: RDS would cost more than the rest of the setup together, and the core reads no Postgres settings in Lane C's `compose.deployment.yaml`. Data lives in Docker volumes and is lost on teardown.
- **HTTPS:** Caddy gets a free certificate for `<elastic-ip-with-dashes>.sslip.io`, a public name that resolves to the IP inside it. To use your own domain, point its A record at the Elastic IP and set `HARVESTNET_DOMAIN`.
- **URLs:** core API `https://<host>/api/` (health at `/api/health`), review pages `/human/...`, platform adapters `/platform/...`, and each frontend at `/<app>/` (list at `/apps.txt`). The frontends are built with `VITE_API_BASE_URL=https://<host>/api` and served by Caddy on the same origin, so CloudFront isn't needed.
- **No GitHub token on the machine:** your laptop runs `git archive` and uploads the bundle to the private bucket. The machine downloads it with its instance role. SSM Run Command starts `deploy/aws/remote_deploy.sh` from the bundle. That script loads the secret into a 0600 file, builds the image and runs `docker compose up`.
- **Claude spending:** `CLAUDE_RUN_CAP_USD` and `CLAUDE_TOTAL_CAP_USD` go into the secret and into the core and organization containers. Both default to 0, which means no paid calls. Caps above $100 are refused. Today only `harvestnet_platform/budget.py` reads these variables. The deployed core server makes no Claude calls.

## Monthly cost estimate

These are **estimates**, not a bill. They use on-demand prices for us-east-2 from the AWS Price List API (checked on 2026-10-11), over 730 hours, with the defaults above.

| Item | Price used | Per month |
|---|---|---|
| EC2 t4g.micro | $0.0084/hour | $6.13 |
| Public IPv4 (the Elastic IP) | $0.005/hour | $3.65 |
| EBS gp3, 10 GB | $0.08/GB-month | $0.80 |
| Secrets Manager, 1 secret | $0.40/secret-month, plus $0.05 per 10,000 calls | $0.40 |
| S3 bundles (a few MB) | | about $0.01 |
| Data transfer out | first 100 GB/month to the internet is free | $0 for a demo |
| SSM Session Manager and Run Command, AWS Budgets alerts | free | $0 |
| CPU credits | standard mode never bills extra | $0 |
| **Total** | | **about $11/month (about $0.37/day)** |

With `INSTANCE_TYPE=t4g.small` (2 GB, $0.0168/hour), the total is about $17/month. With `CPU_CREDITS=unlimited`, the first boot is faster, but sustained CPU above the baseline costs $0.04 per vCPU-hour.

**The budget covers the whole account.** Linked accounts can't turn on cost-allocation tags, so it can't filter by `project=harvestnet`. Other spending in the account counts toward the $15.

## Redeploy a new version

```sh
GIT_REF=<branch, tag or SHA> ALERT_EMAIL=you@example.org deploy/aws/setup.sh
```

A branch name means the pushed branch on `origin` (the script runs `git fetch origin` first). The script finds the existing resources and sends the machine a new bundle. Containers are recreated, and data volumes are kept. To roll back, deploy the earlier SHA the same way. Setting a new provider key works the same way: set it in the environment and re-run. To change the instance size, stop the instance, change its type, and start it again (the script prints the command).

## Logs and access

```sh
deploy/aws/logs.sh              # status of every service, then the last 50 lines of each
deploy/aws/logs.sh core 200     # one service
deploy/aws/check_directory.sh   # registrations, cold-space search, memory use
```

These use SSM Run Command, so they need no plugin. `check_directory.sh` does not change records: it exits successfully only when both its registration list and capability search came from the AGNTCY Directory. It prints a labeled fallback and exits with a failure otherwise. Use `deploy/aws/check_directory.sh 250 2026-10-13T17:30:00-07:00` for another cold-space threshold and pickup time. A successful check verifies the daemon's current response, not that cooler changes or human approvals work end to end. For a shell on the machine, install the Session Manager plugin, then run `aws ssm start-session --profile incubator --region us-east-2 --target <instance-id>`. Container logs stay on the machine, capped at 30 MB per container. The machine's first-boot log is `/var/log/harvestnet-bootstrap.log`.

## Staff tokens

Each organization has its own staff token in the secret. To read one into your own terminal (never paste it into Git, chat or a household page):

```sh
aws secretsmanager get-secret-value --profile incubator --region us-east-2 --secret-id harvestnet/platform \
  --query SecretString --output text | jq -r '.HARVESTNET_STAFF_TOKENS | fromjson | .city'
```

## Tear it down

```sh
deploy/aws/teardown.sh --dry-run   # see what would be deleted
deploy/aws/teardown.sh             # asks you to type "delete harvestnet"
```

It deletes the instance with its disk and data, the Elastic IP, the security group, the IAM role and profile, the bucket and its bundles, the secret and the budget. The secret stays recoverable for 7 days, and a re-run of `setup.sh` restores it. Flags:

- `--yes` skips the prompt.
- `--purge-secret` deletes the secret at once.
- `--keep-budget` keeps the alert.
- `--include-skeleton` also deletes the `harvestnet-api-skeleton` Lambda, its URL, its logs and its role.

## Known limits

- `sslip.io` certificates depend on a free public DNS service and on Let's Encrypt rate limits. If Caddy can't get a certificate, use a real domain.
- The approvals service relays human decisions to the core with one `CORE_API_TOKEN`, but the core accepts each organization's own staff token. With one token, only that organization's decisions commit through the relay. This setup doesn't change that seam.
- A t4g.micro has 1 GB of memory. Nine small Python services use about 35 MB each when idle (measured locally); the Directory daemon adds another process with a 256 MB memory ceiling. Actual full-stack memory use has not been measured on the instance. If it runs short, use `INSTANCE_TYPE=t4g.small`.

## Reset the demo data

`deploy/aws/reset_data.sh` (add `--dry-run` to preview, `--yes` to skip the prompt) deletes the live core records, review links, cooler state and organization host data, restarts the services on a fresh synthetic scenario, and re-publishes the free rules-based evaluation. It keeps the Claude spending ledger, the Directory, the HTTPS certificates and every AWS resource.
