# Deployment and fallbacks (#19)

## Run tonight without accounts

Python 3.12+ is the only requirement. From the repo root:

```powershell
python -m unittest discover -s tests -v
python -m harvestnet_platform.demo
```

Open the URL saved in `runtime/demo-url.txt`. Keep the terminal running. The page
has the cooler switch and capability discovery, five organization turns, explicit
human review buttons, and text intake read-back. Every mode is labeled. It is a
**platform rehearsal**, not the whole HarvestNet application. No Claude calls,
real SMS messages, household saves, or actual produce commitments occur.

## Fallbacks

- Beeceptor outage: recorded synthetic fixtures, timestamp and fallback reason.
- ElevenLabs outage: validated text draft/read-back, awaiting consent; real core
  submission belongs to #9/#14. No food is promised by text intake.
- n8n outage: local review page with exact version and Approve/Decline buttons.
  A missing core records a decision but cannot commit it.
- AGNTCY outage: choose `InProcess` before starting a run, visibly labeled.
  Never switch policies mid-event after a partial network delivery.
- Claude outage/budget exhaustion: rules or replay. Live calls default disabled.

## Claude spending cap

`Budget.from_env()` reads `CLAUDE_RUN_CAP_USD` and `CLAUDE_TOTAL_CAP_USD`, both
default **0**. Wrap every live call in `Budget.call(run_id, call_id,
maximum_cost_usd, function)`. The function returns `(result, actual_cost_usd)`.
Maximum cost must cover input tokens, capped output tokens, tool calls/retries,
and current configured prices. Do not estimate a smaller average. Reservations
are atomic/durable, repeated call IDs cannot repeat a live request, and uncertain
failures retain the entire reservation. Unexpected actual cost above the bound
fails and leaves the reservation charged. Correct conservative bounds are a
prerequisite, not a guaranteed provider billing cap. Share ONE ledger across all
processes using the same credit, or give each its own partition of the cap.
Lane B's Claude client must use this guard; that client does not yet exist here.

## AWS deployment (prepared, not executed)

There is no configured AWS account, EC2 host, domain, Docker installation, or
reviewed Lane A API image here. These steps deliberately stop at those missing
inputs; no fake HTTPS address or deployment claim is produced.

1. On the authorized EC2 host, install Docker Engine with Compose, Git, Python
   and `boto3`. Set DNS to the host and allow only 80/443 from the internet.
   Keep Postgres, agent services, mock controls and Directory private. Use SSM
   or restricted SSH for administration. Back up persistent volumes first.
2. Create a Secrets Manager JSON secret containing random `TRANSPORT_TOKEN`,
   `API_EVENTS_TOKEN`, `DEMO_SWITCH_TOKEN`, `POSTGRES_PASSWORD`, plus configured
   URLs/domain/API image and any provider keys. Attach an EC2 instance role
   granting `secretsmanager:GetSecretValue` only for this secret (and KMS decrypt
   only if its key requires it). No static AWS keys in Git or user data.
3. Check out the reviewed commit on the host. Run:

```sh
python deploy/load_secrets.py --secret-id YOUR_SECRET_ARN --region YOUR_REGION
docker compose --env-file runtime/deploy.env -f compose.platform.yaml -f compose.deployment.yaml config --quiet
docker compose --env-file runtime/deploy.env -f compose.platform.yaml -f compose.deployment.yaml up --build -d
```

4. Caddy obtains TLS for `HARVESTNET_DOMAIN`. Set `APPROVAL_PUBLIC_URL` to
   `https://DOMAIN` (review routes are `/human/*`); platform adapter events are
   `https://DOMAIN/platform/*`. The real Lane A API is proxied at `/api/*`.
   `CORE_API_IMAGE` must be the actual reviewed API image listening on 8000,
   using the proposed env/endpoint contracts or a documented adapter. It is
   intentionally required: an absent backend must not be disguised as production.
5. For native App SDK hosts, also pass `-f compose.agntcy.yaml`. Install/run the
   official Directory daemon using its own repository setup at pinned commit
   `cbda60bed59008bee3396d12c50485b2a179bf74`. Its Compose stack includes its own
   registry/Postgres. Configure `AGNTCY_DIRECTORY_ADDRESS` to a reachable private
   gRPC endpoint, then register the five cards with `harvestnet_platform.directory`.
   Test push/search before a live demo. Native daemon/container execution remains
   unverified on this Windows machine; base HTTP and SDK message shapes are tested.
6. Import/configure the inactive n8n workflows and Beeceptor examples. Send only
   explicit test traffic after confirming credentials and recipient ownership.
   Verify stale approvals return 409, unsigned callbacks fail, all five agent
   health endpoints respond internally, and the core never commits absent fresh
   human approvals/valid holds. Check `/platform/health` and core health over HTTPS.

## Redeploy and rollback

Record the running source commit and immutable API image digest. Run the tests,
fetch a reviewed commit, reload secrets, then rerun the same Compose command.
`config --quiet` validates without printing interpolated secrets. Do not paste
plain `docker compose config`, `docker inspect`, or environment dumps into logs.
Secret rotation requires recreating affected containers. Roll back by checking
out the prior reviewed commit/image digest and running `up -d --build` again.
Do not run `down -v`: volumes contain approvals and core data. Restrict access to
`runtime/deploy.env` (0600 on Linux); it is ignored by Git and reloadable from
Secrets Manager. Stop/remove it when the host no longer needs it. Never log
approval links, household phone numbers, transcripts or SNAP answers.

Source: [AWS Secrets Manager Python retrieval](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets-python-sdk.html).
