# 11: Lane B: rules-based negotiators

**What to build:** Rules-based donor, food bank, and advocate negotiators follow the agent move interface. They're tested by feeding them recorded inputs (draft version plus specialists' facts) and checking their moves, using the contract-day stand-in calculators.

**Blocked by:** 01

**Owner:** Full-stack B (Agents)

**Status:** ready-for-agent

- [ ] The donor accepts only plans that move produce before its deadline, and offers drop-off within its ability.
- [ ] The food bank bids only what its facts allow (storage, hours, truck, pickup windows), and counters with one amendment plus a reason.
- [ ] The advocate proposes amendments toward the biggest fair-share gap, and never accepts, rejects, or vetoes.
- [ ] Every move includes a reason.
- [ ] The tests pass using the example input/output pairs from contract day.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
