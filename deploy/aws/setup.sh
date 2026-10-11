#!/usr/bin/env bash
# HarvestNet AWS setup: one small EC2 instance runs the whole stack with Docker Compose
# (core API on SQLite, Lane C organization hosts and adapters, Caddy for HTTPS, and
# the frontend apps). Safe to re-run: it finds what exists and updates it.
#
#   ALERT_EMAIL=you@example.org deploy/aws/setup.sh            # create or update
#   ALERT_EMAIL=you@example.org deploy/aws/setup.sh --dry-run  # print the plan only
#
# See deploy/aws/README.md for what it creates and what it costs.
set -euo pipefail

# shellcheck source=deploy/aws/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

usage() {
  cat <<'EOF'
Usage: deploy/aws/setup.sh [--dry-run]

Required environment:
  ALERT_EMAIL           address for budget alerts (50%, 80%, 100%)

Optional environment (defaults in brackets):
  PROFILE [incubator]   REGION [us-east-2]   GIT_REF [main]
  BUDGET_USD [15]       INSTANCE_TYPE [t4g.micro]   VOLUME_GB [10]
  CPU_CREDITS [standard] (standard never bills extra CPU; unlimited can)
  HARVESTNET_DOMAIN     a hostname whose DNS points at the Elastic IP [<ip>.sslip.io]
  CLAUDE_RUN_CAP_USD [0]  CLAUDE_TOTAL_CAP_USD [same as run cap]  (0 = no paid calls)
  ANTHROPIC_API_KEY ELEVENLABS_API_KEY BEECEPTOR_BASE_URL DEMO_SWITCH_TOKEN
  N8N_DECISION_WEBHOOK_URL N8N_WEBHOOK_TOKEN CORE_API_TOKEN
                        stored in the secret only when set; never printed
  NO_FETCH=1            do not run 'git fetch origin' before resolving GIT_REF
  SKIP_HEALTH_CHECK=1   do not wait for the HTTPS health check at the end

--dry-run runs only read-only AWS calls and prints every command that would change
something, without running it.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $arg" ;;
  esac
done

GIT_REF="${GIT_REF:-main}"
BUDGET_USD="${BUDGET_USD:-15}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t4g.micro}"
VOLUME_GB="${VOLUME_GB:-10}"
CPU_CREDITS="${CPU_CREDITS:-standard}"
CLAUDE_RUN_CAP_USD="${CLAUDE_RUN_CAP_USD:-0}"
CLAUDE_TOTAL_CAP_USD="${CLAUDE_TOTAL_CAP_USD:-$CLAUDE_RUN_CAP_USD}"
CORE_FIXTURE="docs/contracts/examples/scenario-normal-afternoon.json"
# Optional provider settings copied into the secret when set in the environment.
OPTIONAL_SECRET_KEYS='["ANTHROPIC_API_KEY","ELEVENLABS_API_KEY","BEECEPTOR_BASE_URL","N8N_DECISION_WEBHOOK_URL","N8N_WEBHOOK_TOKEN","CORE_API_TOKEN"]'

is_number() { [[ "$1" =~ ^[0-9]+([.][0-9]+)?$ ]]; }

# ---------------------------------------------------------------------------
preflight() {
  step "Preflight"
  [ "$DRY_RUN" = 1 ] && info "DRY RUN: read-only AWS calls only; changes are printed with '+ aws', not run."
  for tool in jq git tar openssl curl; do require_tool "$tool" "needed by setup.sh"; done
  check_identity
  [ -n "${ALERT_EMAIL:-}" ] || die "set ALERT_EMAIL to the address that should get budget alerts"
  [[ "$ALERT_EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]] || die "ALERT_EMAIL does not look like an email address"
  is_number "$BUDGET_USD" || die "BUDGET_USD must be a number"
  [[ "$VOLUME_GB" =~ ^[0-9]+$ ]] && [ "$VOLUME_GB" -ge 8 ] && [ "$VOLUME_GB" -le 30 ] || die "VOLUME_GB must be 8-30"
  case "$CPU_CREDITS" in standard|unlimited) ;; *) die "CPU_CREDITS must be standard or unlimited" ;; esac
  for cap in "$CLAUDE_RUN_CAP_USD" "$CLAUDE_TOTAL_CAP_USD"; do
    is_number "$cap" || die "Claude caps must be numbers"
    awk -v c="$cap" 'BEGIN{exit !(c <= 100)}' || die "Claude caps above \$100 are refused"
  done
  awk -v r="$CLAUDE_RUN_CAP_USD" -v t="$CLAUDE_TOTAL_CAP_USD" 'BEGIN{exit !(r <= t)}' \
    || die "CLAUDE_RUN_CAP_USD cannot exceed CLAUDE_TOTAL_CAP_USD"

  if [ "${NO_FETCH:-0}" != 1 ]; then
    git -C "$REPO_ROOT" fetch origin --quiet || warn "git fetch origin failed; using local refs"
  fi
  # A branch name means the pushed branch on origin; HEAD or a SHA means exactly that commit.
  if [ "$GIT_REF" != HEAD ] && git -C "$REPO_ROOT" rev-parse --verify --quiet "origin/$GIT_REF^{commit}" >/dev/null; then
    SHA="$(git -C "$REPO_ROOT" rev-parse "origin/$GIT_REF^{commit}")"
  elif git -C "$REPO_ROOT" rev-parse --verify --quiet "$GIT_REF^{commit}" >/dev/null; then
    SHA="$(git -C "$REPO_ROOT" rev-parse "$GIT_REF^{commit}")"
  else
    die "git ref '$GIT_REF' not found (try a branch, tag or commit SHA)"
  fi
  git -C "$REPO_ROOT" cat-file -e "$SHA:deploy/aws/remote_deploy.sh" 2>/dev/null \
    || die "git ref $GIT_REF does not contain deploy/aws (this setup); until it is merged, use GIT_REF=mubinmodi/aws-setup"
  git -C "$REPO_ROOT" show "$SHA:harvestnet_core/server.py" | grep bind_address >/dev/null \
    || die "git ref $GIT_REF has a core server without the HOST setting; deploy a newer ref"
  RELEASE="${SHA:0:12}-$(date -u +%Y%m%d%H%M%S)"
  BUNDLE_KEY="releases/$RELEASE.tar.gz"
  FRONTEND_APPS=()
  local app
  while IFS= read -r app; do
    [ -n "$app" ] && FRONTEND_APPS+=("$app")
  done < <(git -C "$REPO_ROOT" ls-tree --name-only "$SHA" frontend/ 2>/dev/null \
            | while IFS= read -r dir; do
                git -C "$REPO_ROOT" cat-file -e "$SHA:$dir/package.json" 2>/dev/null && basename "$dir"
              done)
  if [ "${#FRONTEND_APPS[@]}" -gt 0 ]; then
    require_tool npm "needed to build the frontend apps"
  fi
  info "git ref $GIT_REF = $SHA (release $RELEASE)"
  info "frontend apps at this ref: ${FRONTEND_APPS[*]:-none}"
  info "docker is not needed here: the instance builds the image itself"
  make_tmp
}

# ---------------------------------------------------------------------------
setup_budget() {
  step "Cost guardrail: AWS Budgets '$BUDGET_NAME' (\$$BUDGET_USD/month, alerts to the ALERT_EMAIL address)"
  info "This budget watches the whole account's cost, not only HarvestNet."
  local current thresholds threshold subscribers
  current="$(lookup_global budgets describe-budget --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME" \
              --query 'Budget.BudgetLimit.Amount' --output text)"
  jq -n --arg name "$BUDGET_NAME" --arg amount "$BUDGET_USD" \
    '{BudgetName: $name, BudgetLimit: {Amount: $amount, Unit: "USD"}, TimeUnit: "MONTHLY", BudgetType: "COST"}' \
    > "$TMP_DIR/budget.json"
  if [ -z "$current" ]; then
    jq -n --arg email "$ALERT_EMAIL" '[50, 80, 100] | map({
        Notification: {NotificationType: "ACTUAL", ComparisonOperator: "GREATER_THAN", Threshold: ., ThresholdType: "PERCENTAGE"},
        Subscribers: [{SubscriptionType: "EMAIL", Address: $email}]})' > "$TMP_DIR/notifications.json"
    aws_rw_global budgets create-budget --account-id "$ACCOUNT_ID" --budget "file://$TMP_DIR/budget.json" \
      --notifications-with-subscribers "file://$TMP_DIR/notifications.json" \
      --resource-tags "$(tags_kv)"
    return
  fi
  if awk -v a="$current" -v b="$BUDGET_USD" 'BEGIN{exit !(a + 0 == b + 0)}'; then
    info "budget exists at \$$current/month"
  else
    info "budget exists at \$$current/month; updating to \$$BUDGET_USD"
    aws_rw_global budgets update-budget --account-id "$ACCOUNT_ID" --new-budget "file://$TMP_DIR/budget.json"
  fi
  thresholds="$(lookup_global budgets describe-notifications-for-budget --account-id "$ACCOUNT_ID" \
                --budget-name "$BUDGET_NAME" --query 'Notifications[?NotificationType==`ACTUAL`].Threshold' --output text)"
  for threshold in 50 80 100; do
    local notification="NotificationType=ACTUAL,ComparisonOperator=GREATER_THAN,Threshold=$threshold,ThresholdType=PERCENTAGE"
    if ! tr '\t' '\n' <<<"$thresholds" | awk -v t="$threshold" '$1 + 0 == t {found = 1} END {exit !found}'; then
      aws_rw_global budgets create-notification --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME" \
        --notification "$notification" --subscribers "SubscriptionType=EMAIL,Address=$ALERT_EMAIL"
      continue
    fi
    subscribers="$(lookup_global budgets describe-subscribers-for-notification --account-id "$ACCOUNT_ID" \
                   --budget-name "$BUDGET_NAME" --notification "$notification" --query 'Subscribers[].Address' --output text)"
    if has_line "$subscribers" "$ALERT_EMAIL"; then
      info "alert at $threshold% already goes to that address"
    else
      aws_rw_global budgets create-subscriber --account-id "$ACCOUNT_ID" --budget-name "$BUDGET_NAME" \
        --notification "$notification" --subscriber "SubscriptionType=EMAIL,Address=$ALERT_EMAIL"
    fi
  done
}

# ---------------------------------------------------------------------------
setup_bucket() {
  step "Private S3 bucket for release bundles: $BUCKET"
  if aws_ro s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
    info "bucket exists"
  else
    local location=()
    [ "$REGION" != "us-east-1" ] && location=(--create-bucket-configuration "LocationConstraint=$REGION")
    aws_rw s3api create-bucket --bucket "$BUCKET" ${location[@]+"${location[@]}"} >/dev/null
  fi
  # Re-applied on every run so the settings stay as written here.
  aws_rw s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws_rw s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws_rw s3api put-bucket-tagging --bucket "$BUCKET" \
    --tagging "TagSet=[{Key=$PROJECT_TAG_KEY,Value=$PROJECT_TAG_VALUE}]"
  aws_rw s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration \
    '{"Rules":[{"ID":"expire-old-releases","Status":"Enabled","Filter":{"Prefix":"releases/"},"Expiration":{"Days":14}}]}'
  jq -n --arg b "$BUCKET" '{Version: "2012-10-17", Statement: [{Sid: "DenyInsecureTransport", Effect: "Deny",
      Principal: "*", Action: "s3:*", Resource: ["arn:aws:s3:::\($b)", "arn:aws:s3:::\($b)/*"],
      Condition: {Bool: {"aws:SecureTransport": "false"}}}]}' > "$TMP_DIR/bucket-policy.json"
  aws_rw s3api put-bucket-policy --bucket "$BUCKET" --policy "file://$TMP_DIR/bucket-policy.json"
}

# ---------------------------------------------------------------------------
setup_eip() {
  step "Elastic IP '$EIP_NAME' (stable address for HTTPS)"
  local found
  found="$(lookup ec2 describe-addresses --filters "Name=tag:$PROJECT_TAG_KEY,Values=$PROJECT_TAG_VALUE" \
            "Name=tag:Name,Values=$EIP_NAME" --query 'Addresses[0].[AllocationId,PublicIp]' --output text)"
  if [ -n "$found" ]; then
    read -r EIP_ALLOC PUBLIC_IP <<<"$found"
    info "found $PUBLIC_IP ($EIP_ALLOC)"
  else
    found="$(aws_rw ec2 allocate-address --domain vpc --tag-specifications "$(tag_spec elastic-ip "$EIP_NAME")" \
              --query '[AllocationId,PublicIp]' --output text)"
    if [ -n "$found" ]; then read -r EIP_ALLOC PUBLIC_IP <<<"$found"; else EIP_ALLOC="<new-allocation>"; PUBLIC_IP="<elastic-ip>"; fi
  fi
  if [ -n "${HARVESTNET_DOMAIN:-}" ]; then
    DOMAIN="$HARVESTNET_DOMAIN"
    info "using HARVESTNET_DOMAIN=$DOMAIN; its DNS A record must point at $PUBLIC_IP"
  else
    DOMAIN="${PUBLIC_IP//./-}.sslip.io"
    info "HTTPS hostname: $DOMAIN (free sslip.io name that resolves to the Elastic IP)"
  fi
}

# ---------------------------------------------------------------------------
setup_secret() {
  step "Secrets Manager secret '$SECRET_NAME'"
  local arn deleted orgs count i changed old_json
  read -r arn deleted <<<"$(lookup secretsmanager describe-secret --secret-id "$SECRET_NAME" \
                             --query '[ARN,DeletedDate]' --output text)" || true
  if [ -n "${arn:-}" ] && [ -n "${deleted:-}" ] && [ "$deleted" != "None" ]; then
    info "secret is scheduled for deletion; restoring it"
    aws_rw secretsmanager restore-secret --secret-id "$SECRET_NAME" >/dev/null
  fi
  orgs="$(git -C "$REPO_ROOT" show "$SHA:$CORE_FIXTURE" | jq -c '[.organizations[].organization_id]')"
  count=$(( $(jq 'length' <<<"$orgs") + 3 ))
  old_json="$TMP_DIR/secret-old.json"
  ( umask 077
    if [ -n "${arn:-}" ] && [ "$DRY_RUN" = 1 ] && [ -n "${deleted:-}" ] && [ "$deleted" != "None" ]; then
      printf '{}' > "$old_json"  # a secret pending deletion can't be read until it is restored
    elif [ -n "${arn:-}" ]; then
      aws_ro secretsmanager get-secret-value --secret-id "$SECRET_NAME" --query SecretString --output text > "$old_json"
    else
      printf '{}' > "$old_json"
    fi )
  jq -e 'type == "object"' "$old_json" >/dev/null 2>&1 || die "existing secret is not a JSON object; fix it in the console"
  # Random tokens for anything not set yet. They pass through the environment, never argv or output.
  local generated=""
  for (( i = 0; i < count; i++ )); do generated+="$(openssl rand -hex 32)"$'\n'; done
  # shellcheck disable=SC2016  # $ENV and $x below are jq variables, not shell.
  ( umask 077
    GEN_TOKENS="$generated" jq -S --argjson orgs "$orgs" --argjson optional "$OPTIONAL_SECRET_KEYS" \
      --arg domain "$DOMAIN" --arg run_cap "$CLAUDE_RUN_CAP_USD" --arg total_cap "$CLAUDE_TOTAL_CAP_USD" '
      def set_value: . != null and . != "";
      ($ENV.GEN_TOKENS | split("\n")) as $gen
      | . as $old
      | (reduce range(0; $orgs | length) as $i
           (($old.HARVESTNET_STAFF_TOKENS // "{}") | fromjson;
            if (.[$orgs[$i]] | set_value) then . else .[$orgs[$i]] = $gen[3 + $i] end)) as $staff
      | .TRANSPORT_TOKEN = (if ($old.TRANSPORT_TOKEN | set_value) then $old.TRANSPORT_TOKEN else $gen[0] end)
      | .API_EVENTS_TOKEN = (if ($old.API_EVENTS_TOKEN | set_value) then $old.API_EVENTS_TOKEN else $gen[1] end)
      | .DEMO_SWITCH_TOKEN = (if ($ENV.DEMO_SWITCH_TOKEN | set_value) then $ENV.DEMO_SWITCH_TOKEN
                              elif ($old.DEMO_SWITCH_TOKEN | set_value) then $old.DEMO_SWITCH_TOKEN else $gen[2] end)
      | .HARVESTNET_STAFF_TOKENS = ($staff | tojson)
      | .HARVESTNET_DOMAIN = $domain
      | .APPROVAL_PUBLIC_URL = "https://\($domain)"
      | .HARVESTNET_ALLOWED_ORIGIN = "https://\($domain)"
      | .CORE_API_URL = "http://core:8000"
      | .CLAUDE_RUN_CAP_USD = $run_cap
      | .CLAUDE_TOTAL_CAP_USD = $total_cap
      | reduce $optional[] as $k (.; if ($ENV[$k] | set_value) then .[$k] = $ENV[$k] else . end)
    ' "$old_json" > "$TMP_DIR/secret.json" )
  # deploy/load_secrets.py takes only single-line strings without quotes or backslashes.
  local bad
  bad="$(jq -r --arg q "'" '[to_entries[] | select((.value | type) != "string"
          or (.value | contains($q) or contains("\\") or contains("\n") or contains("\r"))) | .key] | join(", ")' "$TMP_DIR/secret.json")"
  [ -z "$bad" ] || die "these secret values are not single-line strings without quotes/backslashes: $bad"
  info "keys: $(jq -r 'keys | join(", ")' "$TMP_DIR/secret.json")"
  info "staff tokens for organizations: $(jq -r 'join(", ")' <<<"$orgs") (values are never printed)"
  if [ -z "${arn:-}" ]; then
    aws_rw secretsmanager create-secret --name "$SECRET_NAME" \
      --description "HarvestNet deployment configuration and tokens (deploy/aws/setup.sh)" \
      --secret-string "file://$TMP_DIR/secret.json" --tags "$(tags_kv)" --query ARN --output text >/dev/null
    return
  fi
  changed="$(jq -rn --slurpfile a "$old_json" --slurpfile b "$TMP_DIR/secret.json" \
              '[($a[0] + $b[0]) | keys[] as $k | select($a[0][$k] != $b[0][$k]) | $k] | join(", ")')"
  if [ -z "$changed" ]; then
    info "secret is up to date"
  else
    info "updating keys: $changed"
    aws_rw secretsmanager put-secret-value --secret-id "$SECRET_NAME" \
      --secret-string "file://$TMP_DIR/secret.json" --query VersionId --output text >/dev/null
  fi
  aws_rw secretsmanager tag-resource --secret-id "$SECRET_NAME" --tags "$(tags_kv)"
}

# ---------------------------------------------------------------------------
frontend_routes() { # frontend_routes APP... : Caddy routes for each app (served by the gateway)
  echo "# Generated by deploy/aws/setup.sh for release $RELEASE. Do not edit."
  local app list=""
  for app in "$@"; do
    list+="/$app/ "
    cat <<EOF
redir /$app /$app/ 308
handle /$app/* {
	root * /srv/frontend
	try_files {path} /$app/index.html
	file_server
}
EOF
  done
  printf 'handle /apps.txt {\n\trespond "Frontend apps: %s" 200\n}\n' "${list:-none}"
}

build_bundle() {
  step "Release bundle $BUNDLE_KEY (git $SHA, no GitHub token needed on the instance)"
  local src="$TMP_DIR/src" app paths=() path
  for path in pyproject.toml requirements-agntcy.txt compose.platform.yaml harvestnet_platform harvestnet_core \
              agents/pyproject.toml agents/src docs/contracts core_fixtures deploy frontend; do
    git -C "$REPO_ROOT" cat-file -e "$SHA:$path" 2>/dev/null && paths+=("$path")
  done
  mkdir -p "$src"
  git -C "$REPO_ROOT" archive --format=tar "$SHA" -- "${paths[@]}" | tar -xf - -C "$src"
  mkdir -p "$src/frontend-dist"
  for app in ${FRONTEND_APPS[@]+"${FRONTEND_APPS[@]}"}; do
    [[ "$app" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "frontend app name '$app' must be lowercase letters, digits and dashes"
    info "frontend $app: VITE_API_BASE_URL=https://$DOMAIN/api, served at /$app/"
    if [ "$DRY_RUN" = 1 ]; then
      info "(dry run) would run: npm ci && npm run build -- --base=/$app/   in frontend/$app"
      continue
    fi
    ( cd "$src/frontend/$app"
      if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
      VITE_API_BASE_URL="https://$DOMAIN/api" npm run build -- --base="/$app/" )
    [ -f "$src/frontend/$app/dist/index.html" ] || die "frontend $app build produced no dist/index.html"
    mkdir -p "$src/frontend-dist/$app"
    cp -R "$src/frontend/$app/dist/." "$src/frontend-dist/$app/"
    rm -rf "$src/frontend/$app/node_modules"
  done
  frontend_routes ${FRONTEND_APPS[@]+"${FRONTEND_APPS[@]}"} > "$src/deploy/aws/frontends.caddy"
  COPYFILE_DISABLE=1 tar --no-xattrs -czf "$TMP_DIR/bundle.tar.gz" -C "$src" .
  info "bundle size: $(du -h "$TMP_DIR/bundle.tar.gz" | cut -f1)"
  aws_rw s3 cp "$TMP_DIR/bundle.tar.gz" "s3://$BUCKET/$BUNDLE_KEY" --only-show-errors
}

# ---------------------------------------------------------------------------
setup_iam() {
  step "IAM role '$ROLE_NAME' and instance profile (SSM + read this secret + read release bundles)"
  jq -n '{Version: "2012-10-17", Statement: [{Effect: "Allow", Principal: {Service: "ec2.amazonaws.com"}, Action: "sts:AssumeRole"}]}' \
    > "$TMP_DIR/trust.json"
  jq -n --arg secret "$SECRET_ARN_PATTERN" --arg bucket "$BUCKET" '{Version: "2012-10-17", Statement: [
      {Sid: "ReadDeploySecret", Effect: "Allow", Action: "secretsmanager:GetSecretValue", Resource: $secret},
      {Sid: "ReadReleaseBundles", Effect: "Allow", Action: "s3:GetObject", Resource: "arn:aws:s3:::\($bucket)/releases/*"}]}' \
    > "$TMP_DIR/inline-policy.json"
  if [ -n "$(lookup iam get-role --role-name "$ROLE_NAME" --query Role.RoleName --output text)" ]; then
    info "role exists"
  else
    aws_rw iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document "file://$TMP_DIR/trust.json" \
      --description "HarvestNet EC2 instance: SSM, one secret, release bundles" --tags "$(tags_kv)" >/dev/null
  fi
  if has_line "$(lookup iam list-attached-role-policies --role-name "$ROLE_NAME" \
                  --query 'AttachedPolicies[].PolicyArn' --output text)" "$SSM_POLICY_ARN"; then
    info "AmazonSSMManagedInstanceCore attached"
  else
    aws_rw iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn "$SSM_POLICY_ARN"
  fi
  local current
  current="$(lookup iam get-role-policy --role-name "$ROLE_NAME" --policy-name "$INLINE_POLICY_NAME" \
              --query PolicyDocument --output json)"
  if [ -n "$current" ] && [ "$(jq -S . <<<"$current")" = "$(jq -S . "$TMP_DIR/inline-policy.json")" ]; then
    info "inline policy $INLINE_POLICY_NAME is up to date"
  else
    aws_rw iam put-role-policy --role-name "$ROLE_NAME" --policy-name "$INLINE_POLICY_NAME" \
      --policy-document "file://$TMP_DIR/inline-policy.json"
  fi
  local roles=""
  if [ -z "$(lookup iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" \
               --query InstanceProfile.InstanceProfileName --output text)" ]; then
    aws_rw iam create-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" --tags "$(tags_kv)" >/dev/null
  else
    roles="$(lookup iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" \
              --query 'InstanceProfile.Roles[].RoleName' --output text)"
  fi
  if has_line "$roles" "$ROLE_NAME"; then
    info "instance profile $INSTANCE_PROFILE_NAME has the role"
  else
    aws_rw iam add-role-to-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" --role-name "$ROLE_NAME"
  fi
}

# ---------------------------------------------------------------------------
setup_security_group() {
  step "Security group '$SG_NAME': ports 80 and 443 only (no SSH; use SSM)"
  VPC_ID="$(default_vpc)"
  [ -n "$VPC_ID" ] || die "no default VPC in $REGION"
  SG_ID="$(lookup ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=$SG_NAME" \
            --query 'SecurityGroups[0].GroupId' --output text)"
  if [ -z "$SG_ID" ]; then
    SG_ID="$(aws_rw ec2 create-security-group --group-name "$SG_NAME" --vpc-id "$VPC_ID" \
              --description "HarvestNet: HTTP and HTTPS for Caddy only" \
              --tag-specifications "$(tag_spec security-group "$SG_NAME")" --query GroupId --output text)"
    [ -n "$SG_ID" ] || SG_ID="<new-security-group>"
  else
    info "found $SG_ID in $VPC_ID"
  fi
  local port have
  for port in 80 443; do
    have=""
    [[ "$SG_ID" == sg-* ]] && have="$(lookup ec2 describe-security-groups --group-ids "$SG_ID" \
      --query "length(SecurityGroups[0].IpPermissions[?FromPort==\`$port\` && ToPort==\`$port\` && IpProtocol=='tcp'].IpRanges[?CidrIp=='0.0.0.0/0'][])" \
      --output text)"
    if [ "${have:-0}" -ge 1 ] 2>/dev/null; then
      info "port $port open"
    else
      aws_rw ec2 authorize-security-group-ingress --group-id "$SG_ID" \
        --ip-permissions "IpProtocol=tcp,FromPort=$port,ToPort=$port,IpRanges=[{CidrIp=0.0.0.0/0,Description=caddy}]" \
        --tag-specifications "$(tag_spec security-group-rule)" >/dev/null
    fi
  done
  if [[ "$SG_ID" == sg-* ]]; then
    local extra
    extra="$(lookup ec2 describe-security-groups --group-ids "$SG_ID" \
              --query 'SecurityGroups[0].IpPermissions[?FromPort!=`80` && FromPort!=`443`].FromPort' --output text)"
    [ -z "$extra" ] || warn "security group $SG_ID also allows ports: $extra (remove them; SSM needs no inbound port)"
  fi
}

# ---------------------------------------------------------------------------
launch_instance() {
  local ami root_dev az subnet attempt out
  ami="${AMI_ID:-$(lookup ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id \
                   --query Parameter.Value --output text)}"
  [ -n "$ami" ] || die "could not find the Ubuntu 24.04 arm64 AMI"
  root_dev="$(lookup ec2 describe-images --image-ids "$ami" --query 'Images[0].RootDeviceName' --output text)"
  root_dev="${root_dev:-/dev/sda1}"
  az="$(lookup ec2 describe-instance-type-offerings --location-type availability-zone \
          --filters "Name=instance-type,Values=$INSTANCE_TYPE" --query 'sort(InstanceTypeOfferings[].Location)[0]' --output text)"
  [ -n "$az" ] || die "$INSTANCE_TYPE is not offered in $REGION"
  subnet="$(lookup ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" "Name=availability-zone,Values=$az" \
              "Name=default-for-az,Values=true" --query 'Subnets[0].SubnetId' --output text)"
  [ -n "$subnet" ] || die "no default subnet in $az"
  info "launching $INSTANCE_TYPE (Ubuntu 24.04 arm64, $ami) in $az, ${VOLUME_GB} GB gp3, CPU credits $CPU_CREDITS"
  # No auto-assigned public IP: the Elastic IP is the only public address (one IPv4 charge).
  for attempt in 1 2 3 4 5 6; do
    if out="$(aws_rw ec2 run-instances --count 1 --image-id "$ami" --instance-type "$INSTANCE_TYPE" \
          --iam-instance-profile "Name=$INSTANCE_PROFILE_NAME" \
          --network-interfaces "DeviceIndex=0,SubnetId=$subnet,Groups=$SG_ID,AssociatePublicIpAddress=false,DeleteOnTermination=true" \
          --block-device-mappings "DeviceName=$root_dev,Ebs={VolumeSize=$VOLUME_GB,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}" \
          --metadata-options "HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1" \
          --credit-specification "CpuCredits=$CPU_CREDITS" \
          --user-data "file://$AWS_DIR/user-data.sh" \
          --tag-specifications "$(tag_spec instance "$INSTANCE_NAME")" "$(tag_spec volume "$INSTANCE_NAME")" \
                               "$(tag_spec network-interface "$INSTANCE_NAME")" \
          --query 'Instances[0].InstanceId' --output text 2>"$TMP_DIR/run.err")"; then
      INSTANCE_ID="${out:-<new-instance>}"
      return
    fi
    # A new instance profile takes a few seconds to become usable.
    if grep -q "Invalid IAM Instance Profile\|iamInstanceProfile" "$TMP_DIR/run.err" && [ "$attempt" -lt 6 ]; then
      info "instance profile not ready yet; retrying in 10s"
      sleep 10
      continue
    fi
    cat "$TMP_DIR/run.err" >&2
    die "run-instances failed"
  done
}

setup_instance() {
  step "EC2 instance '$INSTANCE_NAME'"
  local found state type
  found="$(lookup ec2 describe-instances --filters "Name=tag:$PROJECT_TAG_KEY,Values=$PROJECT_TAG_VALUE" \
            "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
            --query 'Reservations[].Instances[].[InstanceId,State.Name,InstanceType]' --output text)"
  [ "$(printf '%s' "$found" | grep -c .)" -le 1 ] || die "more than one '$INSTANCE_NAME' instance exists; remove the extra one"
  NEW_INSTANCE=0
  if [ -n "$found" ]; then
    read -r INSTANCE_ID state type <<<"$found"
    info "found $INSTANCE_ID ($state, $type)"
    [ "$type" = "$INSTANCE_TYPE" ] || warn "instance is $type but INSTANCE_TYPE=$INSTANCE_TYPE; to change it: stop it, run 'aws ec2 modify-instance-attribute --instance-id $INSTANCE_ID --instance-type Value=$INSTANCE_TYPE', start it"
    case "$state" in
      stopped|stopping)
        aws_rw ec2 wait instance-stopped --instance-ids "$INSTANCE_ID"
        aws_rw ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null ;;
    esac
  else
    NEW_INSTANCE=1
    launch_instance
  fi
  aws_rw ec2 wait instance-running --instance-ids "$INSTANCE_ID"
  local attached
  attached="$(lookup ec2 describe-addresses --filters "Name=tag:Name,Values=$EIP_NAME" "Name=tag:$PROJECT_TAG_KEY,Values=$PROJECT_TAG_VALUE" \
               --query 'Addresses[0].InstanceId' --output text)"
  if [ -n "$attached" ] && [ "$attached" = "$INSTANCE_ID" ]; then
    info "Elastic IP $PUBLIC_IP is attached"
  else
    aws_rw ec2 associate-address --allocation-id "$EIP_ALLOC" --instance-id "$INSTANCE_ID" --allow-reassociation \
      --query AssociationId --output text >/dev/null
  fi
}

# ---------------------------------------------------------------------------
deploy_commands() { # the script SSM Run Command executes on the instance (no secrets in it)
  cat <<EOF
set -euo pipefail
cloud-init status --wait >/dev/null 2>&1 || true
test -f /var/lib/harvestnet/bootstrap-done || { echo 'instance bootstrap did not finish; see /var/log/harvestnet-bootstrap.log'; exit 1; }
release_dir=/opt/harvestnet/releases/$RELEASE
python3 -c 'import sys, boto3; boto3.client("s3", region_name=sys.argv[1]).download_file(sys.argv[2], sys.argv[3], sys.argv[4])' $REGION $BUCKET $BUNDLE_KEY /opt/harvestnet/bundle.tar.gz
rm -rf "\$release_dir"
mkdir -p "\$release_dir"
tar -xzf /opt/harvestnet/bundle.tar.gz --no-same-owner -C "\$release_dir"
rm -f /opt/harvestnet/bundle.tar.gz
bash "\$release_dir/deploy/aws/remote_deploy.sh" "\$release_dir" $SECRET_NAME $REGION $RELEASE
EOF
}

deploy_release() {
  step "Deploy release $RELEASE on the instance (SSM Run Command)"
  jq -n --arg script "$(deploy_commands)" '{commands: [$script], executionTimeout: ["2700"]}' > "$TMP_DIR/ssm-params.json"
  if [ "$DRY_RUN" = 1 ]; then
    aws_rw ssm send-command --instance-ids "$INSTANCE_ID" --document-name AWS-RunShellScript \
      --comment "harvestnet deploy $RELEASE" --timeout-seconds 900 --parameters "file://$TMP_DIR/ssm-params.json"
    info "(dry run) the instance would run:"
    deploy_commands | sed 's/^/        /'
    return
  fi
  local waited=0 ping=""
  [ "$NEW_INSTANCE" = 1 ] && info "first boot installs Docker; with standard CPU credits this can take 10-20 minutes"
  while [ "$waited" -lt 1500 ]; do
    ping="$(lookup ssm describe-instance-information --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
             --query 'InstanceInformationList[0].PingStatus' --output text)"
    [ "$ping" = "Online" ] && break
    sleep 15; waited=$((waited + 15))
  done
  [ "$ping" = "Online" ] || die "instance $INSTANCE_ID did not register with SSM in 25 minutes; check the EC2 console's system log"
  local command_id status=""
  command_id="$(aws_rw ssm send-command --instance-ids "$INSTANCE_ID" --document-name AWS-RunShellScript \
                 --comment "harvestnet deploy $RELEASE" --timeout-seconds 900 \
                 --parameters "file://$TMP_DIR/ssm-params.json" --query Command.CommandId --output text)"
  info "SSM command $command_id; waiting for it to finish"
  waited=0
  while [ "$waited" -lt 2800 ]; do
    sleep 15; waited=$((waited + 15))
    status="$(lookup ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE_ID" \
               --query Status --output text)"
    case "$status" in Success|Failed|Cancelled|TimedOut) break ;; esac
  done
  aws_ro ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE_ID" \
    --query StandardOutputContent --output text | tail -n 25 | sed 's/^/    | /'
  if [ "$status" != "Success" ]; then
    aws_ro ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE_ID" \
      --query StandardErrorContent --output text | tail -n 25 | sed 's/^/    ! /' >&2
    die "deploy finished with status '${status:-unknown}'"
  fi
}

health_check() {
  step "HTTPS health check"
  if [ "$DRY_RUN" = 1 ] || [ "${SKIP_HEALTH_CHECK:-0}" = 1 ]; then
    info "skipped; check by hand: curl https://$DOMAIN/api/health"
    return
  fi
  local waited=0
  while [ "$waited" -lt 600 ]; do
    if curl -fsS --max-time 10 "https://$DOMAIN/api/health" >/dev/null 2>&1; then
      info "https://$DOMAIN/api/health answers"
      return
    fi
    sleep 15; waited=$((waited + 15))
  done
  warn "https://$DOMAIN/api/health did not answer in 10 minutes (Caddy may still be getting its certificate)"
}

# ---------------------------------------------------------------------------
hourly_price() { # USD per hour, Linux on-demand, us-east-2 (AWS Price List API, 2026-10-11)
  case "$1" in t4g.nano) echo 0.0042 ;; t4g.micro) echo 0.0084 ;; t4g.small) echo 0.0168 ;; t4g.medium) echo 0.0336 ;; *) echo "" ;; esac
}

cost_estimate() {
  local hourly
  hourly="$(hourly_price "$INSTANCE_TYPE")"
  awk -v it="$INSTANCE_TYPE" -v hr="$hourly" -v gb="$VOLUME_GB" -v credits="$CPU_CREDITS" 'BEGIN {
    h = 730
    printf "    Monthly cost ESTIMATE (on-demand prices for us-east-2 from the AWS Price List API, 2026-10-11; 730 hours):\n"
    if (hr == "") { printf "      EC2 %-24s price not in this table; see https://aws.amazon.com/ec2/pricing/on-demand/\n", it; ec2 = 0 }
    else { ec2 = hr * h; printf "      EC2 %-24s$%6.2f  ($%s/hour)\n", it, ec2, hr }
    ip = 0.005 * h;  printf "      Elastic IP (public IPv4)    $%6.2f  ($0.005/hour)\n", ip
    ebs = 0.08 * gb; printf "      EBS gp3 %2d GB               $%6.2f  ($0.08/GB-month)\n", gb, ebs
    sm = 0.40;       printf "      Secrets Manager, 1 secret   $%6.2f  (+$0.05 per 10,000 API calls)\n", sm
    printf "      S3 release bundles          $  0.01  (a few MB; releases expire after 14 days)\n"
    printf "      Data transfer out           $  0.00  (demo traffic; first 100 GB/month to the internet is free)\n"
    printf "      SSM, AWS Budgets            $  0.00  (Session Manager, Run Command and alert-only budgets are free)\n"
    if (credits == "unlimited") printf "      CPU credits (unlimited)     extra $0.04 per vCPU-hour above baseline, if used\n"
    else printf "      CPU credits (standard)      $  0.00  (standard mode never bills extra CPU)\n"
    printf "      TOTAL                       $%6.2f per month (about $%.2f per day)\n", ec2 + ip + ebs + sm + 0.01, (ec2 + ip + ebs + sm + 0.01) / 30
  }'
}

# ---------------------------------------------------------------------------
summary() {
  step "Summary"
  local skeleton core frontends=() app logs
  skeleton="$(lookup lambda get-function-url-config --function-name "$SKELETON_FUNCTION" --query FunctionUrl --output text)"
  core="https://$DOMAIN/api"
  for app in ${FRONTEND_APPS[@]+"${FRONTEND_APPS[@]}"}; do frontends+=("https://$DOMAIN/$app/"); done
  logs="deploy/aws/logs.sh [service] [lines]   (or: aws ssm start-session --profile $PROFILE --region $REGION --target $INSTANCE_ID)"
  info "core API:           $core   (health: $core/health)"
  info "review pages:       https://$DOMAIN/human/...   platform adapters: https://$DOMAIN/platform/health"
  for app in ${frontends[@]+"${frontends[@]}"}; do info "frontend:           $app"; done
  [ "${#frontends[@]}" -gt 0 ] || info "frontend:           none at this git ref"
  info "API skeleton:       ${skeleton:-not found} (left unchanged)"
  info "secret:             $SECRET_NAME   (read a staff token: see deploy/aws/README.md)"
  info "instance:           $INSTANCE_ID  $INSTANCE_TYPE  $PUBLIC_IP"
  info "logs:               $logs"
  info "redeploy:           GIT_REF=<branch-or-sha> ALERT_EMAIL=... deploy/aws/setup.sh"
  info "teardown:           deploy/aws/teardown.sh   (add --dry-run to preview)"
  cost_estimate
  if [ "$DRY_RUN" = 1 ]; then
    info "(dry run) deploy/aws/outputs.json not written"
    return
  fi
  jq -n --arg core "$core" --arg domain "$DOMAIN" --arg ip "$PUBLIC_IP" --arg instance "$INSTANCE_ID" \
    --arg type "$INSTANCE_TYPE" --arg secret "$SECRET_NAME" --arg bucket "$BUCKET" --arg release "$RELEASE" \
    --arg sha "$SHA" --arg skeleton "$skeleton" --arg logs "$logs" --arg region "$REGION" --arg profile "$PROFILE" \
    --arg cost "$(cost_estimate | sed 's/^ *//')" \
    '{core_api_url: $core, domain: $domain, elastic_ip: $ip, instance_id: $instance, instance_type: $type,
      frontend_urls: $ARGS.positional, skeleton_url: (if $skeleton == "" then null else $skeleton end),
      secret_name: $secret, bucket: $bucket, release: $release, git_sha: $sha, region: $region, profile: $profile,
      logs: $logs, teardown: "deploy/aws/teardown.sh", monthly_cost_estimate: ($cost | split("\n"))}' \
    --args ${frontends[@]+"${frontends[@]}"} > "$AWS_DIR/outputs.json"
  info "wrote deploy/aws/outputs.json (no secrets)"
}

main() {
  preflight
  setup_budget
  setup_bucket
  setup_eip
  setup_secret
  build_bundle
  setup_iam
  setup_security_group
  setup_instance
  deploy_release
  health_check
  summary
}

# Run only when executed; tests source this file to call single functions.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main
fi
