# Handoff: monitor mubinmodi's HarvestNet tickets and run them in parallel across two Macs

Written October 10–11, 2026, at the end of a long design session. The next session's job: **watch mubinmodi's GitHub tickets, and dispatch subagents that build each unblocked ticket in parallel, split across two machines (a MacBook Air and a Mac mini).**

## Read first (don't duplicate; these are the sources of truth)

- **Repo (private):** https://github.com/mubinmodi/UCSC_HACK_HARVESTNET. `main` is at `4e39c7d`, which holds the full design and tickets. The working tree is clean.
- **Rules for any agent:** `CLAUDE.md` / `AGENTS.md` at the repo root. Read them before doing anything.
- **Design:** `docs/MVP_DESIGN.md`. **Decisions:** `docs/adr/0001`–`0009`. **Vocabulary:** `CONTEXT.md`. **Competition rules:** `docs/CHALLENGE.md`.
- **Spec:** `.scratch/harvestnet-mvp/spec.md`. **Lane plan** (who does what, and why nobody waits): `.scratch/harvestnet-mvp/lanes.md`.
- **Tickets:** GitHub issues #1–#25, mirrored as local files in `.scratch/harvestnet-mvp/issues/`. **GitHub is the live copy.** Each issue has its branch, a done-when checklist, and native "blocked by" links.
- **Shared channel with Codex** (also designing in this repo): `COLLAB_claude_codex.md`. Append; never rewrite earlier rounds.
- **Cut scope:** `future scope/`. Reference only. Never build from it.

## ⚠ Before writing any code

`CLAUDE.md` says: *"Do not write application code or begin implementation unless the user explicitly requests it. Creating a plan or marking a ticket ready does not authorize implementation."* The user's request to "create subagents that go and do each task" strongly suggests they want implementation. **Confirm the explicit go-ahead in the first message anyway,** then ask whether `CLAUDE.md`'s working-scope line should be updated to allow implementation for Lane B. Codex reads `AGENTS.md`, so update both files if so.

## mubinmodi's tickets (Lane B: Agents)

| # | Ticket | Branch | Blocked by |
|---|---|---|---|
| 1 | Contract day and real API skeleton (**whole team**: four interfaces + API skeleton on AWS) | `team/01-contract-day-api-skeleton` | none |
| 11 | Rules-based negotiators | `mubinmodi/11-rules-based-negotiators` | 1 |
| 12 | Produce profiles and fair-share table | `mubinmodi/12-produce-profiles-fair-share` | 1 |
| 14 | Front-desk assistant logic | `mubinmodi/14-front-desk-assistant` | 1 |
| 13 | LLM negotiators with calculator tools | `mubinmodi/13-llm-negotiators` | 11 |
| 15 | Cooler-failure decision logic | `mubinmodi/15-cooler-failure-logic` | 12 |
| 20 | Join: real agents in the harness | `mubinmodi/20-join-real-agents-harness` | 8 (Haha36), 11, 12 |
| 23 | Join: cooler failure end to end | `mubinmodi/23-join-cooler-failure-e2e` | 15, 16 (calebdbur), 21 (calebdbur), 22 (Haha36) |

Check live blockers with `gh api repos/mubinmodi/UCSC_HACK_HARVESTNET/issues/<n>/dependencies/blocked_by --jq '[.[] | {number, state}]'`.

**#1 gates everything.** Lane B tickets test against #1's agreed **agent move interface** and **stand-in calculators**, never against teammates' unfinished code. Until #1 is closed, no Lane B subagent should start, except to help produce #1's interfaces if the user wants that.

**Teammates' tickets aren't ours.** Haha36 has Lane A (#7–10, #22, #24), calebdbur has Lane C (#16–19, #21), and Gianellerella has frontend (#2–6, #25). The monitor only reads their state, to know when the joins (#20, #23) unblock.

## Proposed two-machine split (confirm with the user)

Use GitHub as the coordination point, so the two machines never take the same ticket:
- **Claim protocol:** a machine claims a ticket by adding a label `claimed: macbook` or `claimed: mac-mini` (create these labels first), plus an issue comment, *before* starting. The other machine skips claimed tickets.
- **Ownership by default:**
  - **MacBook Air** (this machine): the monitor session, plus #11 → #13 (negotiators, then LLM negotiators: the most Claude-heavy work), then joins #20 and #23.
  - **Mac mini:** #12 → #15 (produce profiles, then cooler-failure logic) and #14 (front-desk assistant).
- **Why this split:** each machine gets one dependency chain, so neither waits on the other for Lane B work. #20 needs #11 (MacBook) and #12 (Mac mini), so it's the first cross-machine point. It runs on the MacBook once both PRs are merged.
- **Each ticket's work:** a subagent in its own git worktree (`Agent` tool, `isolation: "worktree"`), on the ticket's branch, test-first, opening a PR to `main` that references the issue ("Closes #N"). PR bodies end with the attribution line the harness requires.

## Monitor loop design (for the new session)

1. Poll the open issues assigned to mubinmodi, plus the states of their blockers.
2. A ticket is **ready** when all its blockers are closed (merged), it has no `claimed:` label, and it's in this machine's default set. On the MacBook, also take Mac mini tickets if they're unclaimed for a long time, but only with the user's OK.
3. Claim it, then spawn one worktree subagent per ready ticket, in parallel.
4. When a subagent finishes: confirm the tests pass, open the PR, comment on the issue, and remove nothing until the PR is merged.
5. Re-check on a slow cadence. Use the `loop` skill in self-paced mode with long waits (about 20–30 minutes), since CI and teammates' merges are the real signals. After opening a PR, use the ccd_pr tools for CI status instead of polling.

## Environment state and gotchas

- **MacBook:** `gh` 2.102.0 is installed via Homebrew and logged in as **mubinmodi** (keyring). Git pushes over HTTPS work.
- **Mac mini:** needs `brew install gh`, then `gh auth login --hostname github.com --git-protocol https --web` (the user does the browser step themselves), then `git clone https://github.com/mubinmodi/UCSC_HACK_HARVESTNET.git`.
- **This handoff is in the repo** at `.scratch/harvestnet-mvp/HANDOFF_parallel_lane_b.md`, so the Mac mini gets it with `git pull` once it's pushed.
- **Haha36 = the teammate the user calls "yi36".** Their branches are still named `yi36/...`, and the issues are assigned to Haha36. A stale Yi36 invite was cancelled.
- **The issue-tracker setting is out of date.** `docs/agents/issue-tracker.md` says *local markdown*, but the live tickets are now GitHub issues. Re-run `/mattpocock-skills:setup-matt-pocock-skills` to switch to GitHub, or keep both in sync.
- **The terminal pane on the MacBook was unreliable.** One `gh auth login` hung waiting for input. Prefer running interactive commands in the Mac's own Terminal app.
- **Budget:** the app's LLM negotiators use a shared **$100 Claude API credit**. Use rules-based runs and replays (free) for most tests, and set a per-run spending cap (ticket #13 requires it). Proposed models: Opus 5.5 for food banks and the advocate, Sonnet 5.5 for donors and the front desk. Development work itself uses the user's own Claude seat, not the credit.
- **Sponsors:** Cisco AGNTCY, Beeceptor, ElevenLabs, n8n, AWS. No NVIDIA Brev. Accounts and credits aren't verified yet.

## User preferences learned

- Plain, simple English. Short answers. Explanations rather than quizzes.
- Wants recommendations, offered as choices.
- Wants work split so nobody waits on anyone else.
- Owns time, staffing, and deadlines. Don't ask about them or narrow scope because of them.

## Suggested skills for the next agent

- **`loop`**: the self-paced monitor loop over the tickets.
- **`mattpocock-skills:tdd`**: each subagent builds its ticket test-first. Use `mattpocock-skills:implement` too, if it's available: it drives `tdd`, then `code-review`.
- **`code-review`** (or `mattpocock-skills:code-review`): review each subagent's diff against the ticket's checklist and ADRs 0001, 0002, and 0004 before opening the PR.
- **`claude-api`**: required before writing ticket #13's LLM negotiators and #14's front-desk assistant (model IDs, tool use, structured outputs, prompt caching, spending caps).
- **`mattpocock-skills:setup-matt-pocock-skills`**: switch the issue tracker config to GitHub.
- **`mattpocock-skills:resolving-merge-conflicts`**: when branches meet at #20 and #23.
- **`mattpocock-skills:diagnosing-bugs`**: when a ticket's tests won't go green.
