# 07: Lane A: scenario harness and records

**What to build:** The scenario harness runs a fixture with A's own stand-in agents, which follow the agent move interface. One donor, one food bank, and one household go from an offer to a draft, holds, simulated approvals, a commitment, a pickup, and a confirmation. Every run checks the rules automatically and records the full event log in Postgres.

**Blocked by:** 01

**Owner:** Full-stack A (Core)

**Status:** ready-for-agent

- [ ] The normal-afternoon fixture produces a commitment, a pickup notice, and a pickup confirmation in the event log.
- [ ] A commitment is recorded only when every named organization approved the same version with valid holds.
- [ ] The automatic rule checks run on every run: no double booking, pounds conserved per item, approvals tied to the version, no auto-commit, and every pound with a pathway.
- [ ] A fixture that double-books storage fails the rule check.
- [ ] Stand-in agents are clearly separated so real agents can replace them later.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
