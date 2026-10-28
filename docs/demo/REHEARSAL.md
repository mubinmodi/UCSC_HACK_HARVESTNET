# Demo rehearsal checklist (ticket #25)

The one-page run sheet for the team is `docs/demo/run-sheet.html`. The rehearsal is a human task. This page says who does what, how long each part takes, and what
to switch to when something fails. The words to say are in `docs/demo/SCRIPT.md`. The slides are
`docs/demo/slides.html`. The backup is the recorded replay, `docs/demo/replay.html`.

Ticket #25 stays open until the team has rehearsed on the deployed system and ticked the boxes
below.

## The deployed system

| Screen | URL |
|---|---|
| Household page | https://18-217-110-223.sslip.io/household/ |
| Donor page and food bank dashboards | https://18-217-110-223.sslip.io/donor-dashboard/ |
| Results strip | https://18-217-110-223.sslip.io/results-strip/ |
| API (health check) | https://18-217-110-223.sslip.io/api/health |
| Backup, no network needed | `docs/demo/replay.html`, opened from a laptop |

All five answered with HTTP 200 on October 11, 2026, and the API reported `mode: synthetic`.
Check them again before each run. If the deployed system or the network fails, switch to the
recorded replay (see the fallback table below).

## Roles

One person can hold more than one role. Agree on names before the first run.

| Role | Does | Suggested owner |
|---|---|---|
| **Presenter** | Says the script, moves the slides, keeps time | Frontend person (lead for #25) |
| **Caller** | Makes the Spanish voice call on a phone (moment 1), or types into the household page if voice is down | Anyone who speaks Spanish |
| **Operator** | Drives the donor page and the food bank dashboards, and flips the cooler switch (moments 2, 3, 5) | Full-stack C (platform) |
| **Approvers** | Approve as the market manager and the city and eastside managers, through n8n or the dashboards (moments 4, 5) | Full-stack A and B |
| **Timekeeper and backup** | Holds a stopwatch, calls "skip ahead" at the marks, and opens the replay if the network fails | Anyone not presenting |

## Timings (target 2:50, hard stop 3:00)

| Mark | Moment | Screen | Level |
|---|---|---|---|
| 0:00 | Opening | Slides 1 to 3 | |
| 0:15 | 1. Household call in Spanish | Voice line, then slide 6 | Level 1 |
| 0:40 | 2. Farmers market reports surplus | Donor page | Level 1 |
| 0:55 | 3. Agents negotiate | Version history | Level 3 |
| 1:25 | 4. Live approval | n8n message or dashboard | Level 3 |
| 1:40 | 5. Cooler fails | Cooler switch (command below), city dashboard | Level 2 |
| 2:10 | 6. Household gets a text | Household page or phone | Evidence |
| 2:25 | 7. Results strip | Results strip | Evidence |
| 2:45 | Close | Slide 16 | |

If a moment runs 10 seconds over its mark, skip to the next one. For negotiation, show the finished
version history instead of waiting.

## Before each run

- [ ] Check the deployed system: https://18-217-110-223.sslip.io/api/health returns
      `"status": "ok"`.
- [ ] Check that the results strip shows numbers labeled synthetic:
      https://18-217-110-223.sslip.io/results-strip/ (the API serves
      `/api/results?scenario_id=normal-afternoon`). If it shows none, the deployment needs
      `python -m harvestnet_core evaluate core_fixtures/*.json` run against its database
      (see `docs/core/README.md`).
- [ ] Check that the replay is current: `python -m harvestnet_core.demo_replay --check` prints
      "recording matches the code". If not, run it without `--check` and commit.
- [ ] Open, in order: the slides, https://18-217-110-223.sslip.io/household/,
      https://18-217-110-223.sslip.io/donor-dashboard/ (donor, then the city and eastside
      dashboards), https://18-217-110-223.sslip.io/results-strip/, and `docs/demo/replay.html`
      (kept in a background tab).
- [ ] Start from a fresh scenario: `deploy/aws/reset_data.sh` wipes the live demo data (lots, households, review links, cooler state) and re-publishes the results strip. It keeps the Claude spending ledger. Then check the cooler switch reads working (see "The cooler switch" below).
- [ ] Check the phone for the voice line, and the phones or inboxes that receive n8n messages.
- [ ] Spending cap: set `CLAUDE_RUN_CAP_USD` only if the team agreed to live Claude calls
      (`docs/platform/DEPLOYMENT.md`). Zero means rules and templates only. Say so if asked.

## The cooler switch (moment 5, live on AWS)

The switch is reachable through the gateway at `POST /systems/demo/<city|rural|eastside>/cooler`,
behind the `DEMO_SWITCH_TOKEN` bearer. Without the token, or with a wrong one, it answers 401.
Nothing else on the systems service is public.

Read the token once, before the run, and keep it off screen:

```
export DEMO_SWITCH_TOKEN=$(aws secretsmanager get-secret-value --profile incubator --region us-east-2 \
  --secret-id harvestnet/platform --query SecretString --output text \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["DEMO_SWITCH_TOKEN"])')
```

Fail the city cooler (the reply shows `"status": "failed"` and `"synthetic": true`):

```
curl -sS -X POST -H "Authorization: Bearer $DEMO_SWITCH_TOKEN" -H "Content-Type: application/json" \
  https://18-217-110-223.sslip.io/systems/demo/city/cooler -d '{"failed": true}'
```

Reset it to working (after the run, and before the next one):

```
curl -sS -X POST -H "Authorization: Bearer $DEMO_SWITCH_TOKEN" -H "Content-Type: application/json" \
  https://18-217-110-223.sslip.io/systems/demo/city/cooler -d '{"failed": false}'
```

What happens after the failing command, with no further action:

- The city organization host polls its own cooler reading every 10 seconds
  (`COOLER_WATCH_INTERVAL_SECONDS`). Allow about 15 seconds.
- When the reading turns failed, the city food bank's agent records the failed cooler in its own
  status, reads its committed holding, asks the other food banks for their own answers, runs the
  cooler-failure flow and proposes the new version. It then asks the approval service to send the
  review emails to the two named organizations. It never approves or commits; each manager does,
  on their own review link.
- One failure proposes once per lot. Polling again, or restarting the host, proposes nothing more.
  The city host's log lines start with `cooler-watch:` (`deploy/aws/logs.sh`). All of it is
  labeled synthetic.
- Resetting the switch ends that failure. Failing it again starts a new one, which can propose
  again against the lot's then-current committed version. If the first proposal is still awaiting
  approvals, the core refuses a second one and the watcher logs that. If a manager declined the
  proposed version, it is not proposed again (its review links were already used); start from a
  fresh offer. If both managers approved, the plan has moved the romaine, so another failure on
  the same lot proposes nothing new.
- If the switch or the host fails live, use the recorded replay (fallback table below).

## Fallback switches

Use a fallback as soon as a step fails. Each fallback is labeled on screen. Say the label out loud.

| If this fails | Switch to | How | Say |
|---|---|---|---|
| **Beeceptor** (organization systems, cooler switch) | Recorded fixtures | The platform serves its recorded synthetic copy and reports `mode: replay` with a reason (`docs/platform/CONTRACTS.md`). The local demo switch at `python -m harvestnet_platform.demo` flips the cooler. | "These readings are a recorded copy." |
| **ElevenLabs** (voice line) | Text | The Caller types the same answers into the household page, which uses the same read-back and consent question. Or use the platform's text intake. | "Voice is down, so we use the web page. Same questions, same read-back." |
| **n8n** (approvals and texts) | Local approval | Each Approver opens the local review link and presses Approve (`docs/platform/APPROVALS.md`). Show the text body on the household page. | "This is the local approval page. Each manager still approves the exact version." |
| **AGNTCY** (A2A and Directory) | In-process | Live moves come from each organization's own host over signed A2A. If a host cannot answer, that turn is made in process and labeled `in_process_fallback` (lot versions, the food bank dashboard data, the core log). To run the whole stack in process, set `HARVESTNET_MOVE_TRANSPORT=in_process` before a run, never in the middle of one (`docs/platform/DEPLOYMENT.md`). The cooler dashboard flags Directory results from "local_directory_fallback". | "These moves were made in process, not over AGNTCY." |
| **Claude** (cap reached or outage) | Rules-based negotiators | Nothing to do. Negotiators fall back to their rules-based move. | "These moves come from the rules-based negotiators." |
| **The network, or the whole system** | Recorded replay | Open `docs/demo/replay.html` from a laptop. It needs no network. Use the arrow keys, and L for Spanish or English. Keep the slides for framing. | "This is a recorded replay of the same scenario, made from our code. It is not live." |

## The replay page

- It is labeled **RECORDED REPLAY** on every step and says the data is synthetic.
- It follows the demo: household request, offer, moves with reasons, versions, holds and approvals,
  the cooler failure with reason cards, the households' new texts, then pickups and results.
- It differs from the shipped scenario in one way, which the page states: the eastside manager
  answers after 10 minutes, not 15. With 15, the core refuses the late answer and the romaine waits
  for a human. The page shows that outcome too, in the results step.
- To refresh it after a code change, run `python -m harvestnet_core.demo_replay` (from the repo
  root, with `agents/src` on `PYTHONPATH` and `HARVESTNET_PLATFORM_SOURCE=.`).
  `core_tests/test_demo_replay.py` fails if it is stale.

## Rehearsal record (fill in)

Copy this block for each run.

```text
Date and time:
Where (deployed URL or local):
Total time:
Who held each role:
Moments that ran over:
Fallbacks used, and whether each worked (Beeceptor / voice / n8n / AGNTCY / replay):
Problems to fix before the next run:
```

## Ticket #25 checklist

- [ ] The demo runs end to end in under 3 minutes, on the deployed system.
- [ ] Each moment matches its slide (what it proves). The slide numbers are in the timings table.
- [x] A labeled recorded replay exists (`docs/demo/replay.html`, `docs/demo/replay/recording.json`).
- [ ] Every sponsor fallback works during rehearsal (the table above, one run each).
