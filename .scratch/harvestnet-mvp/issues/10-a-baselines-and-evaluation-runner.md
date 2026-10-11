# 10: Lane A: baselines and evaluation runner

**What to build:** First-come-first-served and nearest-food-bank methods run through the same harness and rules. The evaluation runner runs all five scenarios, calculates the metrics, saves recorded replays, and labels every run.

**Blocked by:** 08

**Owner:** Full-stack A (Core)

**Status:** ready-for-agent

- [ ] Both comparison methods respect the same rules and resources as HarvestNet.
- [ ] Five scenarios: normal afternoon, more produce than storage, more households than produce, cooler failure, and condition doubt or no agreement.
- [ ] Calculated metrics: produce wasted, worst-served fair-share coverage, households reached, pickup-window match, time to commitment, invalid commitments (must be zero), and number-check failures.
- [ ] Recorded replays re-run without any Claude calls.
- [ ] Results are written in the shape the API's results endpoint returns.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
