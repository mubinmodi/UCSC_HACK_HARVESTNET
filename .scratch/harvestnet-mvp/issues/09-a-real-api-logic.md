# 09: Lane A: real API logic

**What to build:** Each API endpoint swaps example data for real logic backed by the records, one endpoint at a time, at the same address and with the same response shapes. The frontend screens keep working without any changes.

**Blocked by:** 08

**Owner:** Full-stack A (Core)

**Status:** ready-for-agent

- [ ] Household endpoints: create a request (fair share from the calculator, 7-day expiry, no name), choose food banks, pickup status and balance, "can't make it."
- [ ] Donor endpoints: report surplus, and item status.
- [ ] Food bank endpoints: offers, Accept / Counter / Decline, condition checks, pickup-code confirmation.
- [ ] Contract tests pass: real responses match the agreed example shapes.
- [ ] An expired request is deleted, and a test confirms it.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
