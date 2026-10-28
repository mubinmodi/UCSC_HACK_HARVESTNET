#!/usr/bin/env bash
# Start (or stop) a LOCAL copy of the HarvestNet stack on 127.0.0.1 for recording the demo.
#
#   docs/demo/record/start_local_stack.sh up      # build frontends if needed, start everything, publish results
#   docs/demo/record/start_local_stack.sh down    # stop every local process this script started
#   docs/demo/record/start_local_stack.sh reset   # stop, wipe local data (not the tokens), start again
#
# Plain local Python processes (no Docker): core, approvals, systems, the five organization hosts
# (the three food banks run their own cooler watcher) and a small same-origin gateway that serves the
# three frontends and proxies /api, /human and /platform like deploy/aws/Caddyfile.
#
# Everything is synthetic. The test tokens are generated here, kept in demo-video/.local-env (gitignored,
# mode 600) and never printed. Nothing calls AWS, Claude or any email service: CLAUDE caps are 0 and no
# webhook is configured, so the negotiators are rules-based and no email is sent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/demo-video"
RUN="$OUT/run"
ENV_FILE="$OUT/.local-env"
PY="$ROOT/agents/.venv/bin/python"
GATEWAY_PORT=8080
CORE_PORT=8050; APPROVALS_PORT=8030; SYSTEMS_PORT=8010
ORG_PORTS=(market:8021 city:8022 rural:8023 eastside:8024 advocate:8025)
APPS=(household donor-dashboard results-strip landing)

mkdir -p "$RUN" "$OUT"
cd "$ROOT"

make_env() { # throwaway test tokens, generated once, never printed
  # An env file from before per-sender transport keys is replaced (its tokens are throwaway too).
  [ -f "$ENV_FILE" ] && grep -q '^TRANSPORT_VERIFY_KEYS_CITY=' "$ENV_FILE" && return
  umask 077
  "$PY" - > "$ENV_FILE" <<'PYEOF'
import json, secrets
from harvestnet_platform.transport_auth import generate_keys, host_env
t = lambda: secrets.token_urlsafe(24)
staff = {o: t() for o in ('market', 'city', 'rural', 'eastside', 'advocate')}
print(f'API_EVENTS_TOKEN={t()}')
print(f'DEMO_SWITCH_TOKEN={t()}')
print(f'HARVESTNET_APPROVALS_TOKEN={t()}')
print(f"HARVESTNET_STAFF_TOKENS='{json.dumps(staff)}'")
for key, value in host_env(generate_keys()).items():  # each host's own transport keys
    print(f"{key}='{value}'")
PYEOF
}

stop_all() {
  for f in "$RUN"/*.pid; do
    [ -f "$f" ] || continue
    pid="$(cat "$f")"; kill "$pid" 2>/dev/null || true; rm -f "$f"
  done
  sleep 1
}

build_frontends() {
  for app in "${APPS[@]}"; do
    if [ ! -f "$OUT/dist/$app/index.html" ]; then
      local base="/$app/"
      [ "$app" = landing ] && base="/" # the landing page is the site root, as on AWS
      echo "building frontend $app against http://127.0.0.1:$GATEWAY_PORT/api"
      ( cd "frontend/$app"
        [ -d node_modules ] || npm ci --silent
        VITE_API_BASE_URL="http://127.0.0.1:$GATEWAY_PORT/api" npm run build --silent -- --base="$base" >/dev/null )
      mkdir -p "$OUT/dist/$app"; cp -R "frontend/$app/dist/." "$OUT/dist/$app/"
    fi
  done
}

start() { # start NAME CMD...   (env must already be exported)
  local name="$1"; shift
  nohup "$@" > "$RUN/$name.log" 2>&1 &
  echo $! > "$RUN/$name.pid"
}

wait_http() { # wait_http URL
  for _ in $(seq 1 60); do
    curl -fsS -o /dev/null --max-time 2 "$1" 2>/dev/null && return 0
    sleep 0.5
  done
  echo "timed out waiting for $1 (see $RUN/*.log)" >&2; return 1
}

up() {
  [ -x "$PY" ] || { echo "run: cd agents && uv sync" >&2; exit 1; }
  PYTHONPATH="$ROOT" make_env
  set -a; . "$ENV_FILE"; set +a
  build_frontends
  export PYTHONPATH="$ROOT/agents/src:$ROOT" HARVESTNET_PLATFORM_SOURCE="$ROOT" PYTHONUNBUFFERED=1
  export CLAUDE_RUN_CAP_USD=0 CLAUDE_TOTAL_CAP_USD=0
  unset ANTHROPIC_API_KEY ELEVENLABS_API_KEY N8N_PICKUP_WEBHOOK_URL N8N_RELEASE_WEBHOOK_URL N8N_APPROVAL_WEBHOOK_URL \
        N8N_DECISION_WEBHOOK_URL APPROVER_EMAILS_JSON SES_TEST_RECIPIENTS AGNTCY_DIRECTORY_ADDRESS BEECEPTOR_BASE_URL 2>/dev/null || true
  mkdir -p "$RUN/data"
  local origin="http://127.0.0.1:$GATEWAY_PORT"

  ( export HOST=127.0.0.1 PORT=$CORE_PORT DATABASE_URL="$RUN/data/core.sqlite" \
      HARVESTNET_FIXTURE=docs/contracts/examples/scenario-normal-afternoon.json HARVESTNET_ALLOWED_ORIGIN="$origin"
    start core "$PY" -m harvestnet_core.server )
  wait_http "http://127.0.0.1:$CORE_PORT/health"

  ( export COOLER_STATE_PATH="$RUN/data/coolers.json" DEMO_SWITCH_TOKEN
    start systems "$PY" -m harvestnet_platform.systems --port $SYSTEMS_PORT --host 127.0.0.1 )
  ( export APPROVALS_DB="$RUN/data/approvals.sqlite" APPROVAL_PUBLIC_URL="$origin" CORE_API_URL="http://127.0.0.1:$CORE_PORT" \
      CORE_APPROVALS_TOKEN="$HARVESTNET_APPROVALS_TOKEN" ALLOW_INTERNAL_HTTP=1 API_EVENTS_TOKEN APPROVAL_LINK_TTL_SECONDS=86400
    start approvals "$PY" -m harvestnet_platform.approvals --port $APPROVALS_PORT --host 127.0.0.1 )
  wait_http "http://127.0.0.1:$SYSTEMS_PORT/health" || true
  wait_http "http://127.0.0.1:$APPROVALS_PORT/health" || true

  for entry in "${ORG_PORTS[@]}"; do
    org="${entry%%:*}"; port="${entry##*:}"
    ( upper="$(printf '%s' "$org" | tr '[:lower:]' '[:upper:]')"
      signing="TRANSPORT_SIGNING_KEY_$upper" verify="TRANSPORT_VERIFY_KEYS_$upper"
      own="$("$PY" -c 'import json, os, sys; print(json.loads(os.environ["HARVESTNET_STAFF_TOKENS"])[sys.argv[1]])' "$org")"
      # Each host keeps only its own credentials, as on AWS.
      unset HARVESTNET_STAFF_TOKENS HARVESTNET_APPROVALS_TOKEN
      export AGENT_POLICY=harvestnet_core.join_adapter:policy ALLOW_INTERNAL_HTTP=1 \
        TRANSPORT_SIGNING_KEY="${!signing}" TRANSPORT_VERIFY_KEYS="${!verify}" \
        RECEIPTS_DB="$RUN/data/receipts-$org.sqlite" AGENT_PUBLIC_URL="http://127.0.0.1:$port"
      case "$org" in city|rural|eastside)
        export COOLER_WATCH=1 COOLER_WATCH_INTERVAL_SECONDS=5 COOLER_WATCH_STATE="$RUN/data/cooler-watch-$org.json" \
               SYSTEMS_URL="http://127.0.0.1:$SYSTEMS_PORT" CORE_API_URL="http://127.0.0.1:$CORE_PORT" \
               APPROVALS_URL="http://127.0.0.1:$APPROVALS_PORT" HARVESTNET_STAFF_TOKEN="$own" API_EVENTS_TOKEN ;;
      esac
      start "org-$org" "$PY" -m harvestnet_platform.transport --organization "$org" --port "$port" --host 127.0.0.1 )
  done

  start gateway "$PY" "$ROOT/docs/demo/record/gateway.py" --port $GATEWAY_PORT --dist "$OUT/dist" \
        --core "http://127.0.0.1:$CORE_PORT" --approvals "http://127.0.0.1:$APPROVALS_PORT" --systems "http://127.0.0.1:$SYSTEMS_PORT"
  wait_http "http://127.0.0.1:$GATEWAY_PORT/api/health"

  # The free (rules-based) evaluation, so the results strip has numbers. No LLM cap is given, so the LLM
  # method reads "not run" and no model is called.
  "$PY" -m harvestnet_core evaluate --database "$RUN/data/core.sqlite" --output "$RUN/replays" \
        core_fixtures/*.json > "$RUN/evaluate.log" 2>&1
  echo "local stack is up: $origin  (household/, donor-dashboard/, results-strip/)"
  echo "tokens are in $ENV_FILE (not printed). Stop with: $0 down"
}

case "${1:-}" in
  up) up ;;
  down) stop_all; echo "local stack stopped" ;;
  reset) stop_all; rm -rf "$RUN/data" "$RUN/replays"; up ;;
  *) sed -n '2,10p' "$0"; exit 2 ;;
esac
