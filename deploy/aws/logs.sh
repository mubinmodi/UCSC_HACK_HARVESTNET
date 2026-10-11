#!/usr/bin/env bash
# Show recent container logs from the HarvestNet instance through SSM Run Command.
# Needs no SSH and no Session Manager plugin.
#
#   deploy/aws/logs.sh            # status of every service, then the last 50 lines of each
#   deploy/aws/logs.sh core 200   # last 200 lines of one service
set -euo pipefail

# shellcheck source=deploy/aws/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

service="${1:-}"
lines="${2:-50}"
[[ "$lines" =~ ^[0-9]+$ ]] || die "line count must be a number"
[[ -z "$service" || "$service" =~ ^[a-z]+$ ]] || die "service must be a compose service name, e.g. core"

check_identity >/dev/null
instance="$(lookup ec2 describe-instances --filters "Name=tag:Name,Values=$INSTANCE_NAME" \
             "Name=tag:$PROJECT_TAG_KEY,Values=$PROJECT_TAG_VALUE" "Name=instance-state-name,Values=running" \
             --query 'Reservations[0].Instances[0].InstanceId' --output text)"
[ -n "$instance" ] || die "no running $INSTANCE_NAME instance"

compose='docker compose -p harvestnet --env-file /opt/harvestnet/deploy.env -f compose.platform.yaml -f deploy/aws/compose.aws.yaml'
script="cd /opt/harvestnet/current && export HARVESTNET_RELEASE=\$(cat /opt/harvestnet/current-release) && $compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}' && $compose logs --no-color --tail $lines $service"
make_tmp
jq -n --arg s "$script" '{commands: [$s]}' > "$TMP_DIR/params.json"
command_id="$(aws_rw ssm send-command --instance-ids "$instance" --document-name AWS-RunShellScript \
               --comment "harvestnet logs" --parameters "file://$TMP_DIR/params.json" \
               --query Command.CommandId --output text 2>/dev/null)"
for _ in $(seq 1 20); do
  sleep 3
  status="$(lookup ssm get-command-invocation --command-id "$command_id" --instance-id "$instance" --query Status --output text)"
  case "$status" in Success|Failed|Cancelled|TimedOut) break ;; esac
done
# Run Command returns at most the last 24,000 characters of output.
aws_ro ssm get-command-invocation --command-id "$command_id" --instance-id "$instance" \
  --query '[StandardOutputContent,StandardErrorContent]' --output text
