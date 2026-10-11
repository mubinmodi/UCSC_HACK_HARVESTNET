# 14: Lane B: front-desk assistant logic

**What to build:** The front-desk assistant turns a voice transcript or web form into a draft request, produces the read-back and consent wording, and phrases pickup information using only facts it's given. Tested on recorded transcripts in English and Spanish.

**Blocked by:** 01

**Owner:** Full-stack B (Agents)

**Status:** ready-for-agent

- [ ] Recorded transcripts become correct draft requests, with missing fields marked as missing, never guessed.
- [ ] The read-back wording matches the draft exactly.
- [ ] It reports only committed produce, never produce still being negotiated.
- [ ] Works for English and Spanish transcripts.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
