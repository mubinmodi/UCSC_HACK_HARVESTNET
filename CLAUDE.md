# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# HarvestNet

## Current working scope

Work on idea development and Markdown design documents. Do not write application code or begin implementation unless the user explicitly requests it. Creating a plan or marking a ticket ready does not authorize implementation.

**Exception (user direction, October 11, 2026): Lane B implementation is authorized** for mubinmodi's tickets (#11â€“#15, #20, #23), following `.scratch/harvestnet-mvp/HANDOFF_parallel_lane_b.md`. A ticket starts only when all its GitHub blockers are closed and it is claimed with a `claimed: macbook` or `claimed: mac-mini` label. Default split: the MacBook Air takes #11, #13, #20, #23; the Mac mini takes #12, #14, #15. Teammates' tickets stay read-only.

Read `docs/MVP_DESIGN.md` for the current design, with `CONTEXT.md` (vocabulary), `docs/adr/` (decisions), and `docs/CHALLENGE.md` (the Cisco rules). Everything outside the MVP is in `future scope/`. Use it for reference, never as current behavior. Use `COLLAB_claude_codex.md` for shared review, preserving existing contributor rounds and adding your own response. The original conversation transcripts are historical references in `future scope/history/`. Distinguish candidate outcomes, simulated results, and externally verified facts; agent agreement alone is not user approval.

**User direction (October 11, 2026): Caleb authorized takeover implementation of Lane A issues #7, #8, #9, #10, #22 and #24 after inspecting yi36's branches.** Work is isolated on `calebdbur/core-six-issue-takeover`; preserve the teammate branches and existing Lane C review stack. Keep external acceptance gates open until actually verified. Core tests: `PYTHONPATH=agents/src python -m unittest discover -s core_tests -v`; run agent and skeleton regressions too. See `docs/core/README.md`.

## Repository shape

`main` now has Lane B code in `agents/` (the Python package `harvestnet_agents`; see `agents/README.md`). Run its tests with `cd agents && uv run pytest`, or one test with `uv run pytest tests/<file>::<test>`. There are no build or lint commands yet. Lane C code exists on the unmerged `calebdbur/16`â€“`19` branches; each ticket's PR should add its own commands here. Everything else in the repo is design documents for a hackathon entry (Cisco "When AI Agents Disagree", Level 3).

- **Source of truth:** `docs/MVP_DESIGN.md`, `CONTEXT.md`, `docs/adr/0001`â€“`0009`. ADRs 0001â€“0005 come from the frozen whole-chain framework; 0006â€“0009 are the user's scope cuts that define the MVP. If any other file disagrees with these, these win.
- **Derived copies:** `docs/harvestnet_mvp_design.html` and `docs/HarvestNet_MVP_Design.pdf` are styled renderings of `docs/MVP_DESIGN.md`. When the Markdown changes materially, the copies go stale; say so, or regenerate them if asked.
- **Work plan:** `.scratch/harvestnet-mvp/spec.md`, `lanes.md` (four lanes, with integration only in join tickets 20â€“24), and 25 tickets in `issues/`. The live tickets are GitHub issues #1â€“#25 on `mubinmodi/UCSC_HACK_HARVESTNET`; the local `issues/` files are the original snapshot.
- **`learning/`:** a short course teaching the user the design (HTML lessons, PDFs, glossary). Follow `learning/NOTES.md`: plain, short English, and no quizzes or exercises.

## Writing conventions

- In `docs/MVP_DESIGN.md`, label statements **Decided** (the user confirmed it) or **Proposed** (Claude's design, open for review). All example numbers are synthetic and must be marked that way. Never present an invented figure as real (ADR-0002).
- Use `CONTEXT.md` terms (Organization, Specialist, Negotiator, and so on) and avoid the synonyms it lists.
- If a change contradicts an ADR, flag it explicitly instead of silently overriding it.
- Record user decisions in `COLLAB_claude_codex.md` as a new dated section ("User direction (date): â€¦, recorded by Claude"). Append; never rewrite earlier rounds.
- `AGENTS.md` mirrors this file for Codex (without the Claude header). Keep the two in sync when either changes.

## Agent skills

### Issue tracker

Issues are GitHub issues on `mubinmodi/UCSC_HACK_HARVESTNET`, managed with `gh`. The spec and lane plan stay in `.scratch/<feature-slug>/`; its `issues/` files are the original snapshot, not the live copy. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, applied as GitHub labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
