#!/usr/bin/env bash
# Re-record the whole demo video on this Mac, from a clean local stack, then stop the stack.
#
#   docs/demo/record/record_all.sh
#
# Needs: uv, node and npm, ffmpeg and ffprobe, and (first time only) a Playwright Chromium download of about 150 MB.
# Output: demo-video/harvestnet-demo.mp4, demo-video/harvestnet-demo-short.mp4 and demo-video/README.txt (gitignored).
# Localhost only, synthetic data, no email, no AWS, no paid model calls.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
cd "$ROOT"

[ -x agents/.venv/bin/python ] || (cd agents && uv sync)
uv run --with playwright playwright install chromium

trap '"$HERE/start_local_stack.sh" down' EXIT
"$HERE/start_local_stack.sh" reset
uv run --with playwright python "$HERE/record_demo.py"
python3 "$HERE/stitch.py"
