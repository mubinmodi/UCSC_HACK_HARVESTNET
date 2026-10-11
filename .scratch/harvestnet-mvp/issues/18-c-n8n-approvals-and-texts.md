# 18: Lane C: n8n approvals and texts

**What to build:** n8n workflows for version-bound approvals (donor staff, food bank managers), household pickup texts, "can't make it" replies, and the Market Match tip. Built against the real API skeleton.

**Blocked by:** 01

**Owner:** Full-stack C (Platform)

**Status:** ready-for-agent

- [ ] Approval requests show the exact terms and version. An approval for an old version is rejected.
- [ ] n8n never approves on its own. With no answer, nothing is committed.
- [ ] Pickup texts include the food bank, items, pounds, time window, and code.
- [ ] A "can't make it" reply calls the API's release operation.
- [ ] The Market Match tip goes only to SNAP households, and only for markets marked verified.
- [ ] A local approve button works as a labeled offline fallback.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
