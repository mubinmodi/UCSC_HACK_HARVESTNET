# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# HarvestNet

A Cisco "When AI Agents Disagree" (Level 3) hackathon entry: each donor and food bank has its own agent, and they negotiate how surplus produce reaches low-income households, with no central decider.

## Working scope

The lead (mubinmodi) has authorized implementation, reviewing and merging teammates' PRs, completing their tickets, and deploying to AWS (October 11, 2026). Work in this checkout on `main`: pull first, test, commit, push.

- **Money:** stay inside the caps. AWS: only resources tagged `project=harvestnet`; the account also runs the lead's unrelated `clinical-trials-viz` stack, which stays untouched. Claude: `CLAUDE_RUN_CAP_USD` per run and `CLAUDE_TOTAL_CAP_USD` overall (`deploy/aws/.env`). Ask the lead before raising a cap or creating new paid resources.
- **Secrets:** they live in `deploy/aws/.env` (gitignored) and the Secrets Manager secret `harvestnet/platform`. Read them inside scripts; keep their values out of chat, logs and commits.
- **Results:** every number is synthetic unless a source says otherwise. Keep candidate, simulated and externally verified results distinct; agent agreement alone is not the lead's approval.

## Sources of truth

- **Design:** `docs/MVP_DESIGN.md` (Decided vs Proposed), `CONTEXT.md` (glossary), `docs/adr/0001`–`0012` (0001–0005 frozen framework, 0006–0009 MVP scope cuts, 0010–0012 build decisions), `docs/CHALLENGE.md` (Cisco rules). These win over any other file.
- **Interfaces:** `docs/contracts/` (agreed; contract-v0.2).
- **Tickets:** GitHub issues #1–#25 on `mubinmodi/UCSC_HACK_HARVESTNET`; `.scratch/harvestnet-mvp/` holds the spec, lane plan and the original ticket snapshot.
- **Cut scope:** `future scope/`, reference only, never current behavior.

## Code and commands

- `agents/` (`harvestnet_agents`): negotiators, produce profiles, fair share, front desk, cooler-failure logic, scenario runner. `cd agents && uv run pytest` (one test: `uv run pytest tests/<file>::<test>`).
- `harvestnet_core/` + `core_tests/` + `core_fixtures/`: records, calculators, harness, public API, evaluation. `cd agents && uv sync && cd .. && PYTHONPATH=agents/src HARVESTNET_PLATFORM_SOURCE=. agents/.venv/bin/python -m unittest discover -s core_tests`. Guide: `docs/core/README.md`.
- `harvestnet_platform/` + `tests/`: organization systems, A2A and Directory transport, approvals, n8n. `uv run --with pytest pytest -q` at the root. Guide: `docs/platform/`.
- `api_skeleton/`: the example-data API on Lambda. `cd api_skeleton && uv run pytest`.
- `frontend/<app>/` (household, donor-dashboard, results-strip): Vite + React. `npm ci && npm run typecheck && npm test && npm run build`.
- `deploy/aws/`: `setup.sh`, `teardown.sh`, `reset_data.sh`, `logs.sh` for the live stack at https://18-217-110-223.sslip.io. Guide: `deploy/aws/README.md`.
- `docs/demo/`: run sheet, script, slides, offline replay (`python -m harvestnet_core.demo_replay --check` keeps it current), recording scripts.

Run every suite before pushing.

## Writing conventions

- Label statements in `docs/MVP_DESIGN.md` **Decided** (the lead confirmed it) or **Proposed** (open for review), and mark every example number synthetic (ADR 0002).
- Use `CONTEXT.md` terms (Organization, Staff approver, Surplus lot, Produce profile, and the rest) instead of the synonyms it lists.
- When a change contradicts an ADR, say so explicitly and get the lead's decision.
- Record the lead's decisions in `COLLAB_claude_codex.md` as a new dated section ("User direction (date): …, recorded by Claude"), appended after earlier rounds.
- `docs/harvestnet_mvp_design.html` and `docs/HarvestNet_MVP_Design.pdf` render `docs/MVP_DESIGN.md`; after a material edit, flag them as stale or regenerate them.
- `learning/` teaches the lead the design: plain, short English, explanations only (`learning/NOTES.md`).
- `AGENTS.md` mirrors this file for Codex, without the Claude header. Edit both together.

## Agent skills

- **Issue tracker:** GitHub issues via `gh` (`docs/agents/issue-tracker.md`).
- **Triage labels:** `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` (`docs/agents/triage-labels.md`).
- **Domain docs:** single context, one `CONTEXT.md` and `docs/adr/` at the root (`docs/agents/domain.md`).
