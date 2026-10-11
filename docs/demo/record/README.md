# Recording the demo video

One command re-records the whole demo against a local copy of the stack:

```sh
docs/demo/record/record_all.sh
```

It writes `demo-video/harvestnet-demo.mp4` (about 5 minutes), `demo-video/harvestnet-demo-short.mp4`
(about 75 seconds) and `demo-video/README.txt`. `demo-video/` is gitignored; the videos are not committed.

Everything runs on this Mac, on `127.0.0.1`. The data is the repo's synthetic fixtures, the negotiators are
rules-based (Claude caps are 0), and nothing sends email or touches AWS. Throwaway test tokens are generated
once into `demo-video/.local-env` (mode 600, gitignored) and are never printed.

## Needs

`uv`, Node and npm, `ffmpeg` and `ffprobe`. The first run downloads Playwright's Chromium (about 150 MB).

## The pieces

| File | What it does |
|---|---|
| `start_local_stack.sh up`, `down`, `reset` | Plain local processes: the core, the approvals service, the organization systems, the five organization hosts (the three food banks run their own cooler watcher), and `gateway.py`. It builds the three frontends against the local gateway and publishes the free (rules-based) evaluation so the results strip has numbers. |
| `gateway.py` | A same-origin stand-in for `deploy/aws/Caddyfile`: serves the frontends and proxies `/api`, `/human`, `/platform` and the cooler demo switch. |
| `record_demo.py` | Playwright (Python) at 1280x720 with video. One clip per moment, a caption bar on each (moment name, one line from `SCRIPT.md`, "Synthetic data · local run of the same code"), and a visible cursor. `--only 05` records one clip, which needs the earlier state. |
| `stitch.py` | ffmpeg: joins the clips into one H.264 MP4, adds title cards, and cuts the short version from the timestamps in `demo-video/marks.json`. |

## What is live and what stands in

All seven moments are driven live in the browser. Two places stand in for services the local run does not have:

- **Email.** The real system sends review links and pickup texts through n8n and SES. Locally the script asks the
  approvals service to issue the review links (the same call the core and the cooler watcher make), opens them as each
  organization's human, and shows the household's pickup screen instead of an email.
- **Voice.** The voice line is shown as the household web form, labeled as the text fallback.

The cooler is flipped with the same demo-switch call as the run sheet, against the local systems service. The
organization hosts' own watchers notice it, propose the new version, and the city dashboard shows the reason cards.

If a step cannot be driven, `docs/demo/replay.html` is the labeled fallback. This recording did not need it.

## Run the pieces by hand

```sh
docs/demo/record/start_local_stack.sh up      # http://127.0.0.1:8080/household/ , /donor-dashboard/ , /results-strip/
uv run --with playwright python docs/demo/record/record_demo.py
python3 docs/demo/record/stitch.py
docs/demo/record/start_local_stack.sh down
```
