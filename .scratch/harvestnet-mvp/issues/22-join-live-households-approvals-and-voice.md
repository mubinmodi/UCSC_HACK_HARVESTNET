# 22: Join: live households, approvals, and voice

**What to build:** The real API logic, the front-desk assistant, n8n, and the ElevenLabs agent work together. A household's call or web request creates a real request, managers approve real versions through n8n, and households get real pickup texts. The screens show real data with no changes.

**Blocked by:** 09, 14, 18

**Owner:** Full-stack A (Core)

**Status:** ready-for-agent

- [ ] A voice call and a web request each create a real request with the correct fair share.
- [ ] n8n approvals commit only the matching version.
- [ ] Pickup texts and "can't make it" work end to end.
- [ ] The screens from Lanes FE 02–04 work unchanged against the real logic.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
