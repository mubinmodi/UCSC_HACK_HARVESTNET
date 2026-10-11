# 17: Lane C: AGNTCY transport with stand-in agents

**What to build:** Each organization runs in its own container and exchanges agent moves over AGNTCY A2A, using simple stand-in agents that follow the move interface. Each registers its capabilities in the Directory and can be found by searching it.

**Blocked by:** 01

**Owner:** Full-stack C (Platform)

**Status:** ready-for-agent

- [ ] One container per organization (donor, three food banks, advocate).
- [ ] Moves travel over A2A, and message order is the same for everyone.
- [ ] Directory registration and search by capability (for example, cold space and pickup hours) work.
- [ ] SLIM group chat isn't used. An in-process fallback exists and is labeled.
- [ ] No component outside an organization can commit it. A test tries and fails as expected.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
