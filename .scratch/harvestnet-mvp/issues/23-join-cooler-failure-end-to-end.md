# 23: Join: cooler failure end to end

**What to build:** Flipping the Beeceptor cooler switch triggers the full Level 2 flow on the deployed system: disruption, Directory rediscovery, reason cards, a new version, re-approval through n8n, and updated household texts.

**Blocked by:** 15, 16, 21, 22

**Owner:** Full-stack B (Agents)

**Status:** ready-for-agent

- [ ] Only cold-dependent items move.
- [ ] Every candidate has a reason card visible on the food bank dashboard.
- [ ] The new version needs fresh approvals.
- [ ] Affected households get a new text and can decline.
- [ ] The cooler-failure fixture passes every rule check on the deployed system.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
