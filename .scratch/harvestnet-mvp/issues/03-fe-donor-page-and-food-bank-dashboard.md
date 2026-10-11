# 03: Frontend lane: donor page and food bank dashboard

**What to build:** Donor staff can report surplus produce and watch each item's status. Food bank managers can see offers and the agent's suggested reason, accept, counter, or decline, handle condition checks, see their fair-share gap as counts, and enter pickup codes. Both are built against the real API skeleton.

**Blocked by:** 01

**Owner:** Frontend person

**Status:** ready-for-agent

- [ ] Donor form: items (from the produce profiles list in the API), quantity and unit, condition grade, deadline, recall flag, and drop-off ability.
- [ ] Donor status per item: offered, negotiating, committed (with who moves it), delivered, households reached, unclaimed.
- [ ] Food bank dashboard: storage, pickup hours, truck, and cooler status, plus offers with Accept / Counter / Decline.
- [ ] Condition check: approve as "use today" or decline with a reason.
- [ ] Disagreements shown with each side's reason, and pickup-code entry.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
