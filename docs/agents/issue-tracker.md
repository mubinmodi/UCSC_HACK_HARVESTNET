# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues on `mubinmodi/UCSC_HACK_HARVESTNET`. Use the `gh` CLI for every operation.

## Conventions

- One issue per ticket. The title starts with the ticket number (`12: Lane B: …`).
- The body carries the ticket's **Branch**, **Assignee**, **What to build**, **Blocked by**, and a done-when checklist (`- [ ]` items).
- Blocking uses GitHub's native dependencies. Read them with `gh api repos/mubinmodi/UCSC_HACK_HARVESTNET/issues/<n>/dependencies/blocked_by --jq '[.[] | {number, state}]'`. A ticket is unblocked when every blocker is closed.
- Triage state is a label (see `triage-labels.md`). Lane labels (`lane: core`, `lane: frontend`, `lane: agents`, `lane: platform`, `join`, `team`) group tickets.
- A machine claims a ticket with a `claimed: macbook` or `claimed: mac-mini` label plus an issue comment before starting. Skip tickets another machine has claimed.
- Conversation and progress go in issue comments. A PR that finishes a ticket says `Closes #N`.
- The spec and lane plan stay in the repo: `.scratch/<feature-slug>/spec.md` and `lanes.md`. The files in `.scratch/<feature-slug>/issues/` are the original snapshot the GitHub issues were made from. GitHub is the live copy; don't update the local files to track progress.

## When a skill says "publish to the issue tracker"

Create a GitHub issue with `gh issue create -R mubinmodi/UCSC_HACK_HARVESTNET`, using the body conventions above, and add the triage and lane labels.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <n> -R mubinmodi/UCSC_HACK_HARVESTNET --comments`. The user will normally pass the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is one issue, and each **child** is its own issue.

- **Map**: an issue titled `Map: <effort>` with the Notes / Decisions-so-far / Fog body.
- **Child ticket**: an issue with the question in the body, linked to the map as a sub-issue. A `type: research|prototype|grilling|task` label records the type.
- **Blocking**: GitHub's native "blocked by" dependencies.
- **Frontier**: open, unblocked, unclaimed child issues; lowest number wins.
- **Claim**: add the machine's `claimed:` label and a comment before any work.
- **Resolve**: post the answer as a comment headed `## Answer`, close the issue, then add a gist and link to the map issue's Decisions-so-far.
