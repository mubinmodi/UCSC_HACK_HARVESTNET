# 15: Lane B: cooler-failure decision logic

**What to build:** When a food bank's cooler fails, its agent decides which items must move (from the produce profiles), assesses candidate food banks, and writes a reason card for every candidate. Tested with recorded candidate lists.

**Blocked by:** 12

**Owner:** Full-stack B (Agents)

**Status:** ready-for-agent

- [ ] Only items whose profile needs cold are marked to move. Apples and potatoes stay.
- [ ] Every candidate gets a reason card, chosen or rejected. Example: "pickup ends at 6 pm, so its households can't collect romaine tonight."
- [ ] The proposed new version names the receiving food bank, which still decides for itself.
- [ ] If no candidate fits, it proposes a same-day offer or an unclaimed outcome, with a reason.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
