# 16: Lane C: Beeceptor organization systems and cooler switch

**What to build:** Beeceptor stands in for each organization's own systems: donor inventory, food bank storage, cooler temperature, and truck schedule. It includes a switch that makes a cooler fail with a labeled synthetic reading.

**Blocked by:** 01

**Owner:** Full-stack C (Platform)

**Status:** ready-for-agent

- [ ] Endpoints for each organization's systems, returning data in the agreed shapes.
- [ ] A cooler-failure switch that changes the reading for one food bank.
- [ ] Every reading is labeled synthetic.
- [ ] Offline recorded copies exist for demo fallback.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
