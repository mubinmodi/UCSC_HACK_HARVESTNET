#!/usr/bin/env bash
# Wipe the live demo data and start from a fresh synthetic scenario, then re-publish
# the free (rules-based) evaluation so the results strip isn't empty.
#
#   deploy/aws/reset_data.sh --dry-run   # show what it would do
#   deploy/aws/reset_data.sh             # asks before deleting
#   deploy/aws/reset_data.sh --yes       # no prompt
#
# Deletes: core records (lots, households, pickups, email outbox, results), review links,
# cooler switch state, and each organization host's runtime data.
# Keeps: the Claude spending ledger (budget-data volume, /app/budget/claude-spend.json), the Directory, HTTPS certificates,
# the secret, and every AWS resource. No AWS resource is created or deleted.
set -euo pipefail
# shellcheck source=deploy/aws/lib.sh
source "$(dirname "$0")/lib.sh"

YES=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --yes) YES=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) die "unknown option: $arg" ;;
  esac
done

check_identity >/dev/null
instance="$(lookup ec2 describe-instances --filters "Name=tag:Name,Values=$INSTANCE_NAME" \
             "Name=tag:$PROJECT_TAG_KEY,Values=$PROJECT_TAG_VALUE" "Name=instance-state-name,Values=running" \
             --query 'Reservations[0].Instances[0].InstanceId' --output text)"
[[ "$instance" == i-* ]] || die "no running $INSTANCE_NAME instance"

services="core approvals systems donor city rural eastside advocate"
volumes="core-data approvals-data systems-data donor-data city-data rural-data eastside-data advocate-data"
compose='docker compose -p harvestnet --env-file /opt/harvestnet/deploy.env -f compose.platform.yaml -f deploy/aws/compose.aws.yaml -f deploy/aws/compose.directory.yaml'
rm_volumes=""
for v in $volumes; do rm_volumes="$rm_volumes harvestnet_$v"; done
script="set -eu
cd /opt/harvestnet/current
export HARVESTNET_RELEASE=\$(cat /opt/harvestnet/current-release)
$compose stop $services
$compose rm -f $services
docker volume rm$rm_volumes
$compose up --detach --no-build --wait --wait-timeout 300
$compose exec -T core sh -c 'python -m harvestnet_core evaluate --output /tmp/replays core_fixtures/*.json >/dev/null && echo results re-published'
$compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}'"

step "Reset live demo data on $instance"
info "deletes volumes:$rm_volumes"
info "keeps: budget-data (Claude spending ledger, claude-spend.json), directory, caddy certificates, all AWS resources"
if [ "$DRY_RUN" = 1 ]; then
  printf '%s\n' "$script" | sed 's/^/        /'
  exit 0
fi
if [ "$YES" != 1 ]; then
  read -r -p "Delete all live demo data and start fresh? Type 'reset' to continue: " answer
  [ "$answer" = reset ] || die "cancelled"
fi

make_tmp
jq -n --arg s "$script" '{commands: [$s], executionTimeout: ["900"]}' > "$TMP_DIR/params.json"
command_id="$(aws_rw ssm send-command --instance-ids "$instance" --document-name AWS-RunShellScript \
               --comment "harvestnet reset data" --timeout-seconds 900 --parameters "file://$TMP_DIR/params.json" \
               --query Command.CommandId --output text)"
status=""
for _ in $(seq 1 120); do
  sleep 5
  status="$(lookup ssm get-command-invocation --command-id "$command_id" --instance-id "$instance" --query Status --output text 2>/dev/null || true)"
  case "$status" in Success|Failed|Cancelled|TimedOut) break ;; esac
done
aws_ro ssm get-command-invocation --command-id "$command_id" --instance-id "$instance" \
  --query '[StandardOutputContent,StandardErrorContent]' --output text | sed 's/^/    | /'
[ "$status" = Success ] || die "reset finished with status '$status'"
info "done: fresh synthetic scenario, results strip re-published (rules-based; LLM shows not run)"
