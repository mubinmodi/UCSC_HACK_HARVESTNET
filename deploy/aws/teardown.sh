#!/usr/bin/env bash
# HarvestNet AWS teardown: deletes everything deploy/aws/setup.sh created, found by
# name and the project=harvestnet tag, and the public API skeleton Lambda and its role
# (keep those with --keep-skeleton).
#
#   deploy/aws/teardown.sh --dry-run   # list what would be deleted
#   deploy/aws/teardown.sh             # asks before deleting
#   deploy/aws/teardown.sh --yes       # no prompt
set -euo pipefail

# shellcheck source=deploy/aws/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

usage() {
  cat <<'EOF'
Usage: deploy/aws/teardown.sh [--dry-run] [--yes] [--keep-skeleton] [--keep-budget] [--purge-secret]

  --dry-run           run only read-only AWS calls; print the delete commands
  --yes               do not ask for confirmation
  --keep-skeleton     keep the harvestnet-api-skeleton Lambda, its public URL, logs and role
                      (default: delete them; the URL is public, so nothing is left running)
  --include-skeleton  accepted for older scripts; deleting the skeleton is now the default
  --keep-budget       keep the AWS Budgets alert (it costs nothing)
  --purge-secret      delete the secret at once (default: 7-day recovery window, no charge)

Environment: PROFILE [incubator], REGION [us-east-2], BUCKET [harvestnet-deploy-<account>-<region>]
EOF
}

YES=0 INCLUDE_SKELETON=1 KEEP_BUDGET=0 PURGE_SECRET=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --yes) YES=1 ;;
    --include-skeleton) INCLUDE_SKELETON=1 ;;
    --keep-skeleton) INCLUDE_SKELETON=0 ;;
    --keep-budget) KEEP_BUDGET=1 ;;
    --purge-secret) PURGE_SECRET=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $arg" ;;
  esac
done

step "Preflight"
[ "$DRY_RUN" = 1 ] && info "DRY RUN: read-only AWS calls only; deletes are printed with '+ aws', not run."
require_tool jq "needed by teardown.sh"
check_identity

step "Find HarvestNet resources"
INSTANCES="$(lookup ec2 describe-instances --filters "Name=tag:$PROJECT_TAG_KEY,Values=$PROJECT_TAG_VALUE" \
              "Name=instance-state-name,Values=pending,running,stopping,stopped" \
              --query 'Reservations[].Instances[].InstanceId' --output text)"
EIPS="$(lookup ec2 describe-addresses --filters "Name=tag:$PROJECT_TAG_KEY,Values=$PROJECT_TAG_VALUE" \
         --query 'Addresses[].[AllocationId,AssociationId,PublicIp]' --output text)"
VPC_ID="$(default_vpc)"
SG_ID=""
[ -n "$VPC_ID" ] && SG_ID="$(lookup ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" \
                              "Name=group-name,Values=$SG_NAME" --query 'SecurityGroups[0].GroupId' --output text)"
ROLE_FOUND="$(lookup iam get-role --role-name "$ROLE_NAME" --query Role.RoleName --output text)"
PROFILE_FOUND="$(lookup iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" \
                  --query InstanceProfile.InstanceProfileName --output text)"
BUCKET_FOUND=""
aws_ro s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1 && BUCKET_FOUND="$BUCKET"
SECRET_FOUND="$(lookup secretsmanager describe-secret --secret-id "$SECRET_NAME" --query Name --output text)"
BUDGET_FOUND=""
[ "$KEEP_BUDGET" = 1 ] || BUDGET_FOUND="$(lookup_global budgets describe-budget --account-id "$ACCOUNT_ID" \
                                          --budget-name "$BUDGET_NAME" --query Budget.BudgetName --output text)"
SKELETON_FOUND="" SKELETON_ROLE_FOUND=""
if [ "$INCLUDE_SKELETON" = 1 ]; then
  SKELETON_FOUND="$(lookup lambda get-function --function-name "$SKELETON_FUNCTION" --query Configuration.FunctionName --output text)"
  SKELETON_ROLE_FOUND="$(lookup iam get-role --role-name "$SKELETON_ROLE" --query Role.RoleName --output text)"
fi

info "EC2 instances:      ${INSTANCES:-none}"
EIP_LIST="$(awk 'NF {print $3}' <<<"$EIPS" | tr '\n' ' ')"
info "Elastic IPs:        ${EIP_LIST:-none}"
info "security group:     ${SG_ID:-none}"
info "IAM role/profile:   ${ROLE_FOUND:-none} / ${PROFILE_FOUND:-none}"
info "S3 bucket:          ${BUCKET_FOUND:-none} (all objects are deleted)"
info "secret:             ${SECRET_FOUND:-none}$([ "$PURGE_SECRET" = 1 ] && echo ' (deleted now)' || echo ' (7-day recovery window)')"
info "budget:             ${BUDGET_FOUND:-none}$([ "$KEEP_BUDGET" = 1 ] && echo ' (kept)')"
if [ "$INCLUDE_SKELETON" = 1 ]; then
  info "skeleton Lambda:    ${SKELETON_FOUND:-none}, role ${SKELETON_ROLE_FOUND:-none}"
else
  info "skeleton Lambda:    kept (--keep-skeleton)"
fi
info "data on the instance (core SQLite, approvals, receipts) is deleted with its volume."

if [ "$DRY_RUN" != 1 ] && [ "$YES" != 1 ]; then
  printf '\nType "delete harvestnet" to delete the resources above: '
  read -r answer
  [ "$answer" = "delete harvestnet" ] || die "cancelled; nothing was deleted"
fi

# ---------------------------------------------------------------------------
step "EC2 instance(s)"
if [ -n "$INSTANCES" ]; then
  # shellcheck disable=SC2086  # word splitting gives one argument per instance ID
  aws_rw ec2 terminate-instances --instance-ids $INSTANCES >/dev/null
  # shellcheck disable=SC2086
  aws_rw ec2 wait instance-terminated --instance-ids $INSTANCES
else
  info "none"
fi

step "Elastic IP(s)"
if [ -n "$EIPS" ]; then
  while read -r alloc assoc ip; do
    [ -n "$alloc" ] || continue
    if [ -n "$assoc" ] && [ "$assoc" != "None" ]; then
      aws_rw ec2 disassociate-address --association-id "$assoc" 2>/dev/null || true
    fi
    info "releasing $ip"
    aws_rw ec2 release-address --allocation-id "$alloc"
  done <<<"$EIPS"
else
  info "none"
fi

step "Security group"
if [ -n "$SG_ID" ]; then
  # The instance's network interface can take a minute to go away after termination.
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if aws_rw ec2 delete-security-group --group-id "$SG_ID" 2>/dev/null; then break; fi
    [ "$attempt" -lt 12 ] || die "could not delete security group $SG_ID; run teardown again in a minute"
    info "security group still in use; retrying in 10s"
    sleep 10
  done
else
  info "none"
fi

step "IAM instance profile and role"
if [ -n "$PROFILE_FOUND" ]; then
  if [ -n "$ROLE_FOUND" ]; then
    aws_rw iam remove-role-from-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" --role-name "$ROLE_NAME" 2>/dev/null || true
  fi
  aws_rw iam delete-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME"
fi
if [ -n "$ROLE_FOUND" ]; then
  aws_rw iam detach-role-policy --role-name "$ROLE_NAME" --policy-arn "$SSM_POLICY_ARN" 2>/dev/null || true
  aws_rw iam delete-role-policy --role-name "$ROLE_NAME" --policy-name "$INLINE_POLICY_NAME" 2>/dev/null || true
  aws_rw iam delete-role --role-name "$ROLE_NAME"
fi
[ -n "$PROFILE_FOUND$ROLE_FOUND" ] || info "none"

step "SES SMTP user and sender identity (created by hand for n8n email)"
SES_USER="harvestnet-ses-smtp"
if lookup iam get-user --user-name "$SES_USER" >/dev/null 2>&1; then
  for key in $(lookup iam list-access-keys --user-name "$SES_USER" --query 'AccessKeyMetadata[].AccessKeyId' --output text); do
    aws_rw iam delete-access-key --user-name "$SES_USER" --access-key-id "$key"
  done
  aws_rw iam delete-user-policy --user-name "$SES_USER" --policy-name harvestnet-ses-send 2>/dev/null || true
  aws_rw iam delete-user --user-name "$SES_USER"
else
  info "no SES SMTP user"
fi
if [ -n "${SES_SENDER_EMAIL:-}" ] && lookup sesv2 get-email-identity --email-identity "$SES_SENDER_EMAIL" >/dev/null 2>&1; then
  aws_rw sesv2 delete-email-identity --email-identity "$SES_SENDER_EMAIL"
else
  info "no SES identity to remove (set SES_SENDER_EMAIL to remove one)"
fi

step "S3 bucket"
if [ -n "$BUCKET_FOUND" ]; then
  aws_rw s3 rm "s3://$BUCKET" --recursive --only-show-errors
  aws_rw s3api delete-bucket --bucket "$BUCKET"
else
  info "none"
fi

step "Secret"
if [ -n "$SECRET_FOUND" ]; then
  if [ "$PURGE_SECRET" = 1 ]; then
    aws_rw secretsmanager delete-secret --secret-id "$SECRET_NAME" --force-delete-without-recovery >/dev/null
  else
    aws_rw secretsmanager delete-secret --secret-id "$SECRET_NAME" --recovery-window-in-days 7 >/dev/null
    info "recoverable for 7 days: aws secretsmanager restore-secret --secret-id $SECRET_NAME (setup.sh does this itself)"
  fi
else
  info "none"
fi

step "Budget"
if [ -n "$BUDGET_FOUND" ]; then
  aws_rw_global budgets delete-budget --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME"
else
  info "none or kept"
fi

if [ "$INCLUDE_SKELETON" = 1 ]; then
  step "API skeleton Lambda (public URL; keep it with --keep-skeleton)"
  if [ -n "$SKELETON_FOUND" ]; then
    aws_rw lambda delete-function-url-config --function-name "$SKELETON_FUNCTION" 2>/dev/null || true
    aws_rw lambda delete-function --function-name "$SKELETON_FUNCTION"
  fi
  if [ -n "$(lookup logs describe-log-groups --log-group-name-prefix "/aws/lambda/$SKELETON_FUNCTION" \
               --query 'logGroups[0].logGroupName' --output text)" ]; then
    aws_rw logs delete-log-group --log-group-name "/aws/lambda/$SKELETON_FUNCTION"
  fi
  if [ -n "$SKELETON_ROLE_FOUND" ]; then
    for arn in $(lookup iam list-attached-role-policies --role-name "$SKELETON_ROLE" --query 'AttachedPolicies[].PolicyArn' --output text); do
      aws_rw iam detach-role-policy --role-name "$SKELETON_ROLE" --policy-arn "$arn"
    done
    for name in $(lookup iam list-role-policies --role-name "$SKELETON_ROLE" --query 'PolicyNames[]' --output text); do
      aws_rw iam delete-role-policy --role-name "$SKELETON_ROLE" --policy-name "$name"
    done
    aws_rw iam delete-role --role-name "$SKELETON_ROLE"
  fi
fi

step "Done"
if [ "$DRY_RUN" = 1 ]; then
  info "(dry run) nothing was deleted"
else
  rm -f "$AWS_DIR/outputs.json"
  left="$(lookup resourcegroupstaggingapi get-resources --tag-filters "Key=$PROJECT_TAG_KEY,Values=$PROJECT_TAG_VALUE" \
           --query 'ResourceTagMappingList[].ResourceARN' --output text)"
  if [ -n "$left" ]; then
    info "still tagged $PROJECT_TAG_KEY=$PROJECT_TAG_VALUE (the tag index can lag a few minutes; re-run teardown if these remain):"
    tr '\t' '\n' <<<"$left" | sed 's/^/      /'
  else
    info "no resources tagged $PROJECT_TAG_KEY=$PROJECT_TAG_VALUE remain in $REGION"
  fi
fi
