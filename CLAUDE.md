# HarvestNet

## Current working scope

Work on idea development and Markdown design documents. Do not write application code or begin implementation unless the user explicitly requests it. Creating a plan or marking a ticket ready does not authorize implementation.

Read `docs/MVP_DESIGN.md` for the current design, with `CONTEXT.md` (vocabulary), `docs/adr/` (decisions), and `docs/CHALLENGE.md` (the Cisco rules). Everything outside the MVP is in `future scope/`. Use it for reference, never as current behavior. Use `COLLAB_claude_codex.md` for shared review, preserving existing contributor rounds and adding your own response. The original conversation transcripts are historical references in `future scope/history/`. Distinguish candidate outcomes, simulated results, and externally verified facts; agent agreement alone is not user approval.

## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, recorded as a `Status:` line in each issue file. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
