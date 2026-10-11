# 19: Lane C: deployment hardening and fallbacks

**What to build:** Production-ready deployment: one container per organization alongside the API and Postgres, secrets in AWS Secrets Manager, and written redeploy steps. Every sponsor service has a working offline fallback.

**Blocked by:** 01

**Owner:** Full-stack C (Platform)

**Status:** ready-for-agent

- [ ] Secrets in Secrets Manager, none in the repository.
- [ ] Redeploy steps written so any teammate can follow them.
- [ ] Fallbacks: recorded fixtures instead of Beeceptor, text instead of voice, a local approve button instead of n8n, and an in-process fallback instead of AGNTCY. Each is labeled.
- [ ] A spending-cap setting for Claude runs.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
