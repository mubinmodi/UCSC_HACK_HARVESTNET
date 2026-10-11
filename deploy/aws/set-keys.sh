#!/usr/bin/env bash
# Paste provider keys into deploy/aws/.env without them showing on screen.
# Press Enter to skip a key and keep its current value.
#   deploy/aws/set-keys.sh
set -euo pipefail
env_file="$(cd "$(dirname "$0")" && pwd)/.env"
[ -f "$env_file" ] || { echo "missing $env_file (copy env.template first)"; exit 1; }

set_key() { # name value: replace the value after NAME=, keeping any trailing comment
  python3 - "$env_file" "$1" "$2" <<'PY'
import re, sys
path, name, value = sys.argv[1:]
text = open(path).read()
pattern = re.compile(rf"^{re.escape(name)}=[^\s#]*", re.M)
text = pattern.sub(lambda m: f"{name}={value}", text, count=1) if pattern.search(text) else text + f"\n{name}={value}\n"
open(path, "w").write(text)
PY
}

for name in N8N_API_KEY ANTHROPIC_API_KEY ELEVENLABS_API_KEY BEECEPTOR_BASE_URL; do
  read -r -s -p "$name (Enter to skip): " value; echo
  value="$(printf '%s' "$value" | tr -d '[:space:]')"
  if [ -n "$value" ]; then set_key "$name" "$value"; echo "  saved $name (${#value} characters)"; else echo "  skipped"; fi
done
chmod 600 "$env_file"
echo "Done. Tell Claude 'keys saved'."
