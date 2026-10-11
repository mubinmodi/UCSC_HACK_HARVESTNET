#!/usr/bin/env bash
# Check the live AGNTCY Directory on the HarvestNet instance, through SSM Run Command.
# Read-only on the instance: it lists the registered organizations, runs one search by
# capability (cold space and a pickup time), and shows the Directory's memory use.
# It registers nothing; each organization host keeps its own record current.
#
#   deploy/aws/check_directory.sh                                  # 100 lb cold, 2026-10-13 19:00 PDT
#   deploy/aws/check_directory.sh 250 2026-10-13T17:30:00-07:00    # another query
#
# Prints "Directory: live" when both answers came from the AGNTCY Directory, and exits 1
# otherwise (for example when the hosts fell back to the labeled local registry).
set -euo pipefail

# shellcheck source=deploy/aws/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

cold_lb="${1:-100}"
pickup_at="${2:-2026-10-13T19:00:00-07:00}"
[[ "$cold_lb" =~ ^[0-9]+([.][0-9]+)?$ ]] || die "cold space must be a number of pounds"
[[ "$pickup_at" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2})?([+-][0-9]{2}:[0-9]{2}|Z)$ ]] \
  || die "pickup time must be ISO 8601 with a timezone, e.g. 2026-10-13T19:00:00-07:00"

check_identity >/dev/null
instance="$(lookup ec2 describe-instances --filters "Name=tag:Name,Values=$INSTANCE_NAME" \
             "Name=tag:$PROJECT_TAG_KEY,Values=$PROJECT_TAG_VALUE" "Name=instance-state-name,Values=running" \
             --query 'Reservations[0].Instances[0].InstanceId' --output text)"
[ -n "$instance" ] || die "no running $INSTANCE_NAME instance"

# The search runs inside the city host, which has the Directory SDK and AGNTCY_DIRECTORY_ADDRESS.
# AGENT_ENDPOINTS is only used for the labeled local fallback if the Directory is down.
compose='docker compose -p harvestnet --env-file /opt/harvestnet/deploy.env -f compose.platform.yaml -f deploy/aws/compose.aws.yaml -f deploy/aws/compose.directory.yaml'
endpoints='{"market":"http://donor:8020","city":"http://city:8020","rural":"http://rural:8020","eastside":"http://eastside:8020","advocate":"http://advocate:8020"}'
query="$compose exec -T -e AGENT_ENDPOINTS='$endpoints' city python -m harvestnet_platform.directory"
script="cd /opt/harvestnet/current && export HARVESTNET_RELEASE=\$(cat /opt/harvestnet/current-release)
$compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}' directory
echo '--- registered organizations'
$query --list; echo \"exit=\$?\"
echo '--- search: at least $cold_lb lb cold space, open for pickup at $pickup_at'
$query --brief --cold-lb $cold_lb --pickup-at $pickup_at; echo \"exit=\$?\"
echo '--- memory'
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}' | sort
free -m"
make_tmp
jq -n --arg s "$script" '{commands: [$s]}' > "$TMP_DIR/params.json"
command_id="$(aws_rw ssm send-command --instance-ids "$instance" --document-name AWS-RunShellScript \
               --comment "harvestnet directory check" --parameters "file://$TMP_DIR/params.json" \
               --query Command.CommandId --output text 2>/dev/null)"
for _ in $(seq 1 20); do
  sleep 3
  status="$(lookup ssm get-command-invocation --command-id "$command_id" --instance-id "$instance" --query Status --output text)"
  case "$status" in Success|Failed|Cancelled|TimedOut) break ;; esac
done
output="$(aws_ro ssm get-command-invocation --command-id "$command_id" --instance-id "$instance" \
            --query '[StandardOutputContent,StandardErrorContent]' --output text)"
printf '%s\n' "$output"
# Both answers must be live: two "mode": "agntcy_directory" lines and two clean exits.
if [ "$(grep -c '"mode": "agntcy_directory"' <<<"$output")" -eq 2 ] && [ "$(grep -c '^exit=0$' <<<"$output")" -eq 2 ]; then
  echo "Directory: live (both answers came from the AGNTCY Directory)"
else
  echo "Directory: NOT live (see the mode and exit lines above)" >&2
  exit 1
fi
