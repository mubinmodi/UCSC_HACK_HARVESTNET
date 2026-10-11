# 08: Lane A: calculators, matching, versions, and stop rules

**What to build:** A mixed surplus lot is split item by item across three food banks using the real calculators and matching rules, still with stand-in agents. Versions, turn order, holds, approvals, and the stop rules all work.

**Blocked by:** 07

**Owner:** Full-stack A (Core)

**Status:** ready-for-agent

- [ ] Real calculators for fair share, household portion, storage over time, pickup-window feasibility, unit conversion, and fair-share gap.
- [ ] Hard rule: produce goes only to food banks whose households can collect it before it spoils. Needs-fridge produce goes to limited-fridge households only for same-day pickup.
- [ ] Fair-share rule: no household goes above its share while another at the same food bank is below it.
- [ ] Every amendment creates a new version, and old approvals stop counting.
- [ ] Three rounds with no new terms produce a preserved disagreement. The deadline produces unclaimed, with a reason, never an auto-commit. Recalled lots are never offered.
- [ ] Outgoing-message number check, with a template fallback after two failures and each failure counted.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
