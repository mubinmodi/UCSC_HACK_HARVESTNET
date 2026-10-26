# The whole stack runs on one small instance, with SQLite

October 11, 2026, decided by the user ("be careful with AWS cost; use what is necessary"). The spec planned Postgres, and a managed database or load balancer would cost more than everything else combined. The demo needs one always-on, HTTPS-reachable copy of the system, not scale.

## Decision

- One EC2 t4g.micro runs every service with Docker Compose: the core, the five organization hosts, the approvals service, the organization systems, the AGNTCY Directory daemon, and Caddy for HTTPS on an `sslip.io` name. The frontends are served from the same address.
- The core stores its records in SQLite on the instance's disk instead of Postgres. The core keeps Postgres support, and CI still tests it.
- No RDS, load balancer, NAT gateway or CloudFront. Secrets live in one Secrets Manager secret, and a $45 monthly AWS Budget alert covers the whole account. The estimated cost is about $11 a month.
- `deploy/aws/setup.sh` and `teardown.sh` create and remove everything tagged `project=harvestnet`.

## Consequences

- There is no redundancy: if the instance stops, the demo is down. The offline recorded replay is the fallback.
- Data lives in Docker volumes on one disk and is lost on teardown. `deploy/aws/reset_data.sh` wipes it between rehearsals on purpose.
- Memory is tight (1 GB plus swap). Adding services means checking memory first, and moving to t4g.small (about $17 a month) if needed.
- Moving to Postgres later is a configuration change for the core (`DATABASE_URL`), plus a managed or self-hosted database to pay for.
