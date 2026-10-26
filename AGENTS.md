# HarvestNet

## Current working scope

Work on idea development and Markdown design documents. Do not write application code or begin implementation unless the user explicitly requests it. Creating a plan or marking a ticket ready does not authorize implementation.

**Exception (user direction, October 11, 2026): Lane B implementation is authorized** for mubinmodi's tickets (#11–#15, #20, #23), following `.scratch/harvestnet-mvp/HANDOFF_parallel_lane_b.md`. A ticket starts only when all its GitHub blockers are closed and it is claimed with a `claimed: macbook` or `claimed: mac-mini` label. Default split: the MacBook Air takes #11, #13, #20, #23; the Mac mini takes #12, #14, #15. Later the same day the lead (mubinmodi) also authorized reviewing, fixing, and merging teammates' PRs, completing their remaining tickets, and deploying to AWS (cost kept minimal).

Read `docs/MVP_DESIGN.md` for the current design, with `CONTEXT.md` (vocabulary), `docs/adr/` (decisions), and `docs/CHALLENGE.md` (the Cisco rules). Everything outside the MVP is in `future scope/`. Use it for reference, never as current behavior. Use `COLLAB_claude_codex.md` for shared review, preserving existing contributor rounds and adding your own response. The original conversation transcripts are historical references in `future scope/history/`. Distinguish candidate outcomes, simulated results, and externally verified facts; agent agreement alone is not user approval.

## Repository shape

A hackathon entry (Cisco "When AI Agents Disagree", Level 3). Code on `main`:

- `agents/`: Lane B negotiators, profiles, front desk, cooler-failure logic (`harvestnet_agents`). `cd agents && uv run pytest` (one test: `uv run pytest tests/<file>::<test>`).
- `harvestnet_core/` + `core_tests/` + `core_fixtures/`: Lane A records, calculators, harness, public API, evaluation. `cd agents && uv sync && cd .. && PYTHONPATH=agents/src HARVESTNET_PLATFORM_SOURCE=. agents/.venv/bin/python -m unittest discover -s core_tests`. See `docs/core/README.md`.
- `harvestnet_platform/` + `tests/`: Lane C organization systems, A2A/Directory transport, approvals, n8n. `uv run --with pytest pytest -q` at the root. See `docs/platform/`.
- `api_skeleton/`: the example-data API (Lambda). `cd api_skeleton && uv run pytest`.
- `frontend/<app>/` (household, donor-dashboard, results-strip): Vite + React apps. `npm ci && npm run typecheck && npm test && npm run build`.
- `deploy/aws/`: `setup.sh` / `teardown.sh` for the live stack (profile `incubator`, us-east-2). See `deploy/aws/README.md`.
- Agreed interfaces: `docs/contracts/`.

- **Source of truth:** `docs/MVP_DESIGN.md`, `CONTEXT.md`, `docs/adr/0001`–`0012`. ADRs 0001–0005 come from the frozen whole-chain framework; 0006–0009 are the user's scope cuts that define the MVP; 0010–0012 are the October 11 build decisions (email via SES, committed produce is not waste, one small instance with SQLite). If any other file disagrees with these, these win.
- **Derived copies:** `docs/harvestnet_mvp_design.html` and `docs/HarvestNet_MVP_Design.pdf` are styled renderings of `docs/MVP_DESIGN.md`. When the Markdown changes materially, the copies go stale; say so, or regenerate them if asked.
- **Work plan:** `.scratch/harvestnet-mvp/spec.md`, `lanes.md` (four lanes, with integration only in join tickets 20–24), and 25 tickets in `issues/`. The live tickets are GitHub issues #1–#25 on `mubinmodi/UCSC_HACK_HARVESTNET`; the local `issues/` files are the original snapshot.
- **`learning/`:** a short course teaching the user the design (HTML lessons, PDFs, glossary). Follow `learning/NOTES.md`: plain, short English, and no quizzes or exercises.

## Writing conventions

- In `docs/MVP_DESIGN.md`, label statements **Decided** (the user confirmed it) or **Proposed** (Claude's design, open for review). All example numbers are synthetic and must be marked that way. Never present an invented figure as real (ADR-0002).
- Use `CONTEXT.md` terms (Organization, Specialist, Negotiator, and so on) and avoid the synonyms it lists.
- If a change contradicts an ADR, flag it explicitly instead of silently overriding it.
- Record user decisions in `COLLAB_claude_codex.md` as a new dated section ("User direction (date): …, recorded by Codex"). Append; never rewrite earlier rounds.
- `CLAUDE.md` mirrors this file for Claude Code (plus a Claude-specific header). Keep the two in sync when either changes.

## Agent skills

### Issue tracker

Issues are GitHub issues on `mubinmodi/UCSC_HACK_HARVESTNET`, managed with `gh`. The spec and lane plan stay in `.scratch/<feature-slug>/`; its `issues/` files are the original snapshot, not the live copy. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, applied as GitHub labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
