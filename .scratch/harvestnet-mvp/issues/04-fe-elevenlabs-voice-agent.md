# 04: Frontend lane: ElevenLabs voice agent

**What to build:** The ElevenLabs voice agent is set up in its dashboard, with the HarvestNet script in English and Spanish, and sends each call's transcript to the API's voice-intake endpoint. It speaks back whatever the API returns: the read-back, the fair share, the food banks, and the code.

**Blocked by:** 01

**Owner:** Frontend person

**Status:** ready-for-agent

- [ ] The script covers household size, pickup times, fridge space, neighborhood, and an optional SNAP question that can be skipped.
- [ ] Read-back and consent happen before submitting.
- [ ] Transcripts reach the API's voice-intake endpoint, and the example response is spoken back correctly.
- [ ] The pickup code is read out twice.
- [ ] Works in both English and Spanish.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
