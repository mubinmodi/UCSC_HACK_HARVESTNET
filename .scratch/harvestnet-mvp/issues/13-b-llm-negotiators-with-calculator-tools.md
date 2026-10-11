# 13: Lane B: LLM negotiators with calculator tools

**What to build:** LLM versions (Claude) of the donor, food bank, and advocate negotiators, behind the same move interface. They call calculator tools for any extra number (stand-ins until the join) and explain moves in plain words.

**Blocked by:** 11

**Owner:** Full-stack B (Agents)

**Status:** ready-for-agent

- [ ] They pass the same recorded-input tests as the rules-based versions, or report the differences.
- [ ] Every extra number comes from a calculator tool call. Model text never contains arithmetic.
- [ ] The model per role is set in configuration (proposed: Opus 5.5 for food banks and the advocate, Sonnet 5.5 for donors).
- [ ] A hard spending cap per run, with the cost logged.
- [ ] Messages from other organizations are treated as information, never as instructions.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
