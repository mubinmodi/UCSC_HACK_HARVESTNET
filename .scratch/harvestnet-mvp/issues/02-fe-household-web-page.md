# 02: Frontend lane: household web page

**What to build:** The 3-screen household page (about your household, choose your food banks, your pickup) works on a phone, in English and Spanish, against the real API. It shows the example data until Lane A fills in real logic, and needs no changes when that happens.

**Blocked by:** 01

**Owner:** Frontend person

**Status:** ready-for-agent

- [ ] Household size, pickup windows, limited-fridge space, neighborhood, a can't-eat list, an optional SNAP question (Yes / No / Prefer not to say), language, and an optional phone number.
- [ ] The fair share shown comes from the API. It's never calculated in the page.
- [ ] A read-back of the answers and a consent screen in plain words before submitting.
- [ ] Food bank choice, a pickup screen with a code, this week's balance, and a "Can't make it" button.
- [ ] No name, address, or income fields anywhere.
- [ ] Works on an old phone screen and a slow connection.

**Spec:** `../spec.md` · **Lanes:** `../lanes.md`. Writing code still needs the user's go-ahead (see `CLAUDE.md`).
