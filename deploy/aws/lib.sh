# Shared helpers for deploy/aws/setup.sh and deploy/aws/teardown.sh.
# Sourced, never run directly. Nothing here prints a secret value.

PROFILE="${PROFILE:-incubator}"
REGION="${REGION:-us-east-2}"
# Guard against deploying into the wrong account. Set EXPECTED_ACCOUNT_ID= (empty) to skip.
EXPECTED_ACCOUNT_ID="${EXPECTED_ACCOUNT_ID-649852688863}"

PROJECT_TAG_KEY="project"
PROJECT_TAG_VALUE="harvestnet"

# Resource names. setup.sh creates these; teardown.sh deletes them.
BUDGET_NAME="harvestnet-monthly"
SECRET_NAME="harvestnet/platform"
ROLE_NAME="harvestnet-ec2-role"
INSTANCE_PROFILE_NAME="harvestnet-ec2-profile"
INLINE_POLICY_NAME="harvestnet-ec2-access"
SSM_POLICY_ARN="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
SG_NAME="harvestnet-web"
EIP_NAME="harvestnet-eip"
INSTANCE_NAME="harvestnet-app"
SKELETON_FUNCTION="harvestnet-api-skeleton"
SKELETON_ROLE="harvestnet-api-skeleton-role"

DRY_RUN=0
STEP=0
AWS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$AWS_DIR/../.." && pwd)"

step() { STEP=$((STEP + 1)); printf '\n==> [%d] %s\n' "$STEP" "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Tags in the two shapes the AWS CLI takes.
tags_kv() { printf 'Key=%s,Value=%s' "$PROJECT_TAG_KEY" "$PROJECT_TAG_VALUE"; }
tag_spec() { # tag_spec RESOURCE_TYPE [NAME]
  local tags="{Key=$PROJECT_TAG_KEY,Value=$PROJECT_TAG_VALUE}"
  [ -n "${2:-}" ] && tags="$tags,{Key=Name,Value=$2}"
  printf 'ResourceType=%s,Tags=[%s]' "$1" "$tags"
}

# Read-only AWS call. Runs in --dry-run too.
aws_ro() { aws --profile "$PROFILE" --region "$REGION" "$@"; }
aws_ro_global() { aws --profile "$PROFILE" --region us-east-1 "$@"; }

# Read-only lookup that prints its text result, or nothing when absent ("None" or an error).
lookup() {
  local out
  out="$(aws_ro "$@" 2>/dev/null)" || out=""
  [ "$out" = "None" ] && out=""
  printf '%s' "$out"
}
lookup_global() {
  local out
  out="$(aws_ro_global "$@" 2>/dev/null)" || out=""
  [ "$out" = "None" ] && out=""
  printf '%s' "$out"
}

# Mutating AWS call. Printed on fd 3 (a copy of stderr, so neither $(...) capture nor
# 2>/dev/null hides the plan); skipped under --dry-run. Arguments never hold secret
# values (secrets go through 0600 temp files passed as file://).
exec 3>&2
_show() { { printf '    + aws'; printf ' %q' "$@"; printf '\n'; } >&3; }
aws_rw() {
  _show "$@"
  [ "$DRY_RUN" = 1 ] && return 0
  aws --profile "$PROFILE" --region "$REGION" "$@"
}
aws_rw_global() {
  _show "$@" --region us-east-1
  [ "$DRY_RUN" = 1 ] && return 0
  aws --profile "$PROFILE" --region us-east-1 "$@"
}

# has_line TEXT WORD: TEXT (tab or newline separated) contains WORD exactly, ignoring case.
# grep reads all input (no -q), so a pipefail pipeline never fails on SIGPIPE.
has_line() { [ -n "$(tr '\t' '\n' <<<"$1" | grep -ixF -- "$2")" ]; }

require_tool() { command -v "$1" >/dev/null 2>&1 || die "missing required tool: $1 ($2)"; }

# Credentials expire (browser sign-in). Check them before anything else.
check_identity() {
  require_tool aws "install the AWS CLI v2"
  local arn
  if ! ACCOUNT_ID="$(aws_ro sts get-caller-identity --query Account --output text 2>/dev/null)" || [ -z "$ACCOUNT_ID" ]; then
    die "AWS credentials for profile '$PROFILE' are missing or expired. Run: aws login --profile $PROFILE"
  fi
  arn="$(aws_ro sts get-caller-identity --query Arn --output text 2>/dev/null || true)"
  if [ -n "$EXPECTED_ACCOUNT_ID" ] && [ "$ACCOUNT_ID" != "$EXPECTED_ACCOUNT_ID" ]; then
    die "profile '$PROFILE' is account $ACCOUNT_ID, expected $EXPECTED_ACCOUNT_ID (set EXPECTED_ACCOUNT_ID to override)"
  fi
  info "account $ACCOUNT_ID, region $REGION, profile $PROFILE"
  info "signed in as $arn"
  BUCKET="${BUCKET:-harvestnet-deploy-$ACCOUNT_ID-$REGION}"
  SECRET_ARN_PATTERN="arn:aws:secretsmanager:$REGION:$ACCOUNT_ID:secret:$SECRET_NAME-??????"
}

default_vpc() { lookup ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text; }

# Make a private scratch directory, removed on exit.
make_tmp() {
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/harvestnet-aws.XXXXXX")"
  chmod 700 "$TMP_DIR"
  trap 'rm -rf "$TMP_DIR"' EXIT
}
