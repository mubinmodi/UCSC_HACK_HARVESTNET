# 01: Contract day and real API skeleton

**What to build:** The team agrees on the four shared interfaces, and the real public API goes live on AWS at its real address, with every agreed endpoint returning example data. From this point, all four lanes work in parallel with no waiting.

**Blocked by:** None (can start immediately)

**Owner:** Everyone (C deploys the skeleton)

**Status:** ready-for-agent

- [ ] The scenario fixture format is agreed, with one example: a normal afternoon with households, a donor's surplus lot, three food banks, and a timed cooler failure.
- [ ] The agent move interface is agreed (inputs: draft version, specialists' facts, turn; moves: accept, counter with one amendment plus a reason, reject with a reason, request a hold, ask a human), with 3 example input/output pairs.
- [ ] The calculator interface is agreed (fair share, household portion, storage over time, pickup-window feasibility, unit conversion, fair-share gap), with example inputs and outputs that work as stand-ins.
- [ ] The public API contract is written in plain language, with an example request and response for every household, donor, food bank, voice-intake, approval, and results operation.
- [ ] The real API skeleton is deployed on AWS over HTTPS and returns those example responses at its real address.
- [ ] The frontend person has called the skeleton from a browser and seen example data.
- [ ] Every interface uses `CONTEXT.md` terms.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
