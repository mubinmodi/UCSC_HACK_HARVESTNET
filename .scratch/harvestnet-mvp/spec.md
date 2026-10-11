# Spec: HarvestNet MVP

Status: ready-for-agent

Created: October 10, 2026. Source design: `docs/MVP_DESIGN.md`. Decisions: `docs/adr/` 0001–0009. Vocabulary: `CONTEXT.md`. Competition rules: `docs/CHALLENGE.md`.

**Marking this spec ready does not authorize implementation** (see `CLAUDE.md`). Writing code needs the user's explicit go-ahead.

---

## Problem Statement

Farms, packers, distributors, grocers, and farmers markets regularly have good fresh produce they can't sell, and it spoils within days. Nearby, low-income households would use it, but getting the right produce to the right food bank in time is hard:
- Food banks in low-access areas get less than those near donors.
- Families can only pick up at certain times.
- Some households have little fridge space.
- Small donors have no truck.
- When a food bank's cooler fails, the cold-dependent produce in it is lost.

Today this is arranged by phone and email. Nobody can see whether produce reaches the households furthest behind.

For the hackathon team, the problem is also practical. We have to build this as a Cisco "When AI Agents Disagree" Level 3 entry, with one frontend person who has limited technical experience and three full-stack developers. The work has to split so that nobody blocks anyone else, and so that every piece tests against the same rules.

## Solution

HarvestNet gives each **donor** and each **food bank** its own AI **negotiator**, backed by **specialists**: deterministic calculators that read the organization's own data. For each **surplus lot**, the negotiators edit one shared, numbered **draft agreement**. It records how much of each item goes to which food bank, and who moves it (the donor drops it off, or the food bank collects).

An **advocate** agent, with no vote, pushes produce toward the food bank whose households are furthest below their **fair share**. The fair share is a SNAP-style weekly produce amount set by household size.

A deal becomes a **commitment** only when every named organization's human approves the same version and every **hold** is valid. Otherwise it ends as a **preserved disagreement** or as unclaimed produce, with reasons. **Nothing is ever committed automatically.**

**Households** use a mobile web page or a voice line. They give household size, pickup windows, fridge space, neighborhood, and anything they can't eat. Optionally, they say whether they receive SNAP/CalFresh. They choose food banks, get a text with what's ready and a pickup code, and confirm pickup.

A food bank's cooler failure triggers rediscovery of other food banks through the AGNTCY Directory, with a reason card for every candidate (Level 2). Results are compared against first-come-first-served and reported honestly.

## User Stories

### Households

1. As a household, I want to ask for produce on a simple mobile web page, so that I don't need to install an app or create an account.
2. As a household without a smartphone or data plan, I want to call a voice line, so that I can still take part.
3. As a Spanish-speaking household, I want to use the web page and voice line in Spanish, so that I understand every step.
4. As a household, I want to give my household size and see my weekly fair share, so that I know what to expect.
5. As a household, I want to say when I can pick up, so that I'm only offered produce I can actually collect.
6. As a household with limited fridge space, I want to say so, so that I'm not given large amounts of produce that needs a fridge.
7. As a household, I want to list foods I can't eat, so that I'm not offered them.
8. As a household, I want the option to say I receive SNAP/CalFresh, with "prefer not to say" always available, so that I can share it only if I choose.
9. As a household, I want to hear or see my answers read back before anything is saved, so that mistakes get corrected.
10. As a household, I want to be asked for consent in plain words, so that I know what's kept and for how long.
11. As a household, I want to choose which food banks I can reach, so that I'm only sent to places I can get to.
12. As a household, I want to see what produce is already committed at my food banks, so that I don't make a wasted trip.
13. As a household, I want to be put on a list and texted when produce is ready, so that I don't have to keep checking.
14. As a household, I want a text with the food bank, time window, items, pounds, and a short pickup code, so that pickup is quick.
15. As a household with no phone for texts, I want a food bank, a time window, and a code to come back with, so that I'm not left out.
16. As a household, I want to tap or reply "can't make it," so that my portion goes to another family instead of being wasted.
17. As a household, I want to see how much of this week's fair share I've received, so that I know what's left.
18. As a household, I want a text if my pickup time or location changes, for example after a cooler failure, so that I don't go to the wrong place.
19. As a household that said it receives SNAP, I want a tip about a nearby Market Match farmers market, so that my CalFresh dollars buy more produce.
20. As a household, I want no name, address, or income question, so that I can ask for help without giving up my privacy.
21. As a household, I want my request deleted after 7 days, so that nothing about me is kept longer than needed.

### Donors

22. As donor staff, I want to report surplus produce by web page or voice, so that reporting takes a minute.
23. As donor staff, I want to pick items from a list of produce types, so that the system knows how each item must be handled.
24. As donor staff, I want to enter quantity and unit for each item, so that calculators can convert and split it correctly.
25. As donor staff, I want to grade the produce's condition and flag any recall, so that unsafe produce is never offered.
26. As donor staff, I want to set a pickup deadline, so that produce leaves before it spoils.
27. As donor staff, I want to say whether I can drop the produce off, and where and when, so that the agents can agree who moves it.
28. As donor staff, I want to approve the plan before any produce is promised, so that my organization decides for itself.
29. As donor staff, I want to see the live status of each item, so that I know where my produce went.
30. As donor staff, I want any item with no taker clearly marked unclaimed with a reason, so that nothing is silently wasted.
31. As a farmers market manager, I want to report what's left at market close, so that end-of-day produce reaches families.

### Food banks

32. As a food bank manager, I want to set my cold and dry storage, pickup hours, and truck availability, so that my agent only accepts what we can handle.
33. As a food bank manager, I want to see incoming offers with the current draft and my agent's suggested reason, so that I can decide quickly.
34. As a food bank manager, I want to accept, counter, or decline an offer, so that I stay in control.
35. As a food bank manager, I want to approve large deliveries, anything marked "use soon," and every truck run, so that nothing commits us without me.
36. As a food bank manager, I want to see my households' combined fair-share gap as counts only, so that I can argue for produce without seeing anyone's private data.
37. As a food bank manager, I want disagreements involving my food bank shown with each side's reason, so that I understand what's stuck.
38. As a food bank manager, I want to see expected arrivals, so that I can plan staff and space.
39. As food bank staff, I want to enter a household's pickup code, so that the pickup is confirmed and their balance updates.
40. As a food bank manager, I want my agent to report a failed cooler and find another food bank with cold space, so that cold produce isn't lost.
41. As a food bank manager receiving produce after another food bank's cooler fails, I want to accept or refuse it myself, so that I'm never forced to take more than I can store.

### Agents and network

42. As a donor negotiator, I want to read my specialists' facts (inventory, condition, deadline, drop-off), so that every offer is grounded in real data.
43. As a food bank negotiator, I want my specialists' facts (demand counts, storage over time, hours, truck, distribution before spoilage), so that every bid is feasible.
44. As the advocate, I want pooled fair-share gaps per food bank and Food Access Atlas context, so that I can argue for the households furthest behind.
45. As the advocate, I want to propose an amendment on my turn, so that I can influence the split without a vote.
46. As any negotiator, I want each amendment to create a new draft version with my reason attached, so that everyone sees what changed and why.
47. As any negotiator, I want old approvals to stop counting when the terms change, so that nobody is bound to terms they didn't approve.
48. As any resource owner, I want to place an expiring hold tied to one version, so that the same space, truck, or produce is never promised twice.
49. As any negotiator, I want a calculator tool for any extra number, so that I never invent quantities.
50. As any negotiator, I want my outgoing message checked so every number matches a calculator result, so that invented numbers never leave my organization.
51. As any negotiator, I want a template-sentence fallback after two failed number checks, so that negotiation continues safely.
52. As a food bank negotiator, I want to find other food banks by capability through the Directory, so that I can recover from a cooler failure.
53. As a food bank negotiator, I want to write a reason card for every candidate, chosen or rejected, so that the choice is explainable.
54. As any participant, I want negotiation to stop after three rounds with no new terms and record a preserved disagreement, so that it never loops forever.
55. As any participant, I want a lot to become unclaimed with reasons when the donor's deadline passes, so that nothing is committed automatically.

### Judges and the demo

56. As a judge, I want to watch the draft change version by version with reasons, so that I can see a real negotiation.
57. As a judge, I want to see a live human approval, so that I believe organizations stay in control.
58. As a judge, I want to see a cooler fail and a replacement chosen with reason cards, so that I can credit Level 2.
59. As a judge, I want a results strip comparing produce wasted, fair-share coverage, and households reached against first-come-first-served, so that I can judge the evidence.
60. As a judge, I want to know whether a run was live, replay, or synthetic, so that I trust what I'm shown.

### Team and evaluation

61. As a developer, I want to run a scripted day through the scenario harness and get the full event log and outcomes, so that I can test behavior without any UI or sponsor services.
62. As a developer, I want the harness to check the rules on every run (no double booking, every pound accounted for, fair share respected, no auto-commit, approvals tied to versions), so that rule breaks are caught at once.
63. As a developer, I want to swap negotiation methods (first-come-first-served, nearest food bank, rules-based, LLM) on the same scenario, so that comparisons are fair.
64. As a developer, I want recorded replays that cost nothing, so that we save the $100 Claude credit for real LLM runs.
65. As the frontend person, I want the real API live from day one with realistic example data, so that I can build every screen without waiting for the backend, and never have to switch later.
66. As the frontend person, I want the API to be described in plain words with example responses, so that I can use it without deep backend knowledge.
67. As a developer, I want each organization to run as its own container, so that "no central decider" is literally true in the architecture.
68. As a developer, I want every sponsor service to have an offline fallback (recorded data, text instead of voice, a local approve button), so that the demo survives an outage.

## Implementation Decisions

### Recommended work split

**Superseded by the independent lane plan in `lanes.md`, with 25 tickets in `issues/`.** The table below still describes each person's area.

The split follows the two seams, so each person can test their part without waiting for anyone else.

| Person | Owns | Why this fits |
|---|---|---|
| **Frontend person** (limited technical experience) | **Screens and the people-facing experience:** the household web page (3 screens), donor page, and food bank dashboard, all built against the **real API skeleton**, which returns example data until Lane A adds real logic. Plus no-code and low-code work: the **ElevenLabs voice agent** (configured in its dashboard: script, read-back, Spanish), all **copy and Spanish translations**, and the **demo script and slides**. | Mostly visual and writing work, with no backend logic. The real API is live from day one, so they never wait. ElevenLabs is configured in a web dashboard. |
| **Full-stack A: Core** | **Records and the scenario harness (Seam 1):** the data model, draft agreements and versions, holds, approvals, stop rules, all calculators (fair share, portions, storage over time, spoil-by, unit conversion), the outgoing validator and number check, the event log, the rule checks, and the **baseline methods** (first-come-first-served, nearest food bank). | The foundation everyone else builds on. Must start first and stay stable. |
| **Full-stack B: Agents** | **Negotiators and profiles:** donor, food bank, and advocate negotiators, **rules-based first**, then **LLM versions** (Claude) using calculator tools. The front-desk assistant's logic. The produce profile data and the fair-share table data. | Pure agent work behind A's interfaces. It can start with rules-based policies on day one against A's fixtures. |
| **Full-stack C: Platform** | **Integrations:** deploying the **real API skeleton** on day one, the **Beeceptor mocks** of the outside organizations' own systems, **AGNTCY** A2A transport, Directory, and the cooler-failure path, **n8n** approvals and texts, the **ElevenLabs** webhook, **AWS** deployment, and the results data for the results strip. | All the outside-world wiring. It pairs with the frontend person on the API contract and ElevenLabs. |

**Pairings:**
- **C + frontend person:** API contract and mock first, then ElevenLabs.
- **A + B:** agent and harness interfaces.
- **A + C:** the event log feeds the API.

**If someone is ahead, help in this order:** evaluation runs, then demo rehearsal, then the dashboards.

### Contract day (do first, together, before splitting)

Agree on four interfaces, so all four people can work in parallel:
1. **Scenario fixture format:** a scripted day. Households' requests, donors' surplus offers, food banks' storage, hours, and trucks, a timed fault (cooler failure), and the clock. Owned by A.
2. **Agent move interface:** what a negotiator receives (the current draft version, its specialists' facts, its turn) and what it can return (accept, counter with one amendment plus a reason, reject with a reason, request a hold, ask a human). Owned by A and B.
3. **Public API contract:** the endpoints for households, donors, food banks, voice intake, approvals, and results, with example responses. It ends contract day **deployed as the real API skeleton on AWS**, returning those examples. Owned by C and the frontend person.
4. **Calculator interface:** the named calculators and their inputs and outputs, which both rules-based and LLM negotiators call. Owned by A.

### Modules

- **Records:** households' requests (short code, size, fair share, received this week, pickup windows, limited-fridge flag, neighborhood, can't-eat list, optional SNAP answer, chosen food banks, consent, 7-day expiry), surplus offers, food bank status, draft agreements (versioned), holds, approvals, pickup notices, pickup confirmations, and outcomes (each item's **pathway**, with pounds and reasons). Postgres.
- **Calculators (specialists):** fair share from the published table, household portions capped at fair share, storage over time, pickup-window feasibility before spoilage, unit conversion, and fair-share gap per food bank. All deterministic.
- **Validator and number check:** rejects infeasible moves, and blocks any outgoing message whose numbers don't match calculator results for the current version. Template fallback after two failures, with each failure counted.
- **Negotiation protocol:** one draft per surplus lot, a published turn order, a new version for every amendment, holds owned by resource owners, approvals bound to a version, commitment when all named parties approve the same version with valid holds, and the stop rules (three rounds with no new terms, deadline, ask a human).
- **Negotiators:** donor, food bank, and advocate. Each has a rules-based policy and an LLM policy behind the same move interface. Models (proposed): Opus 5.5 for food banks and the advocate, Sonnet 5.5 for donors and the front desk.
- **Front-desk assistant:** turns a web form or voice transcript into a draft request, with read-back and consent, and reports only committed produce. It never allocates.
- **Produce profiles:** needs a fridge, days usable cold and at room temperature, transport temperature, condition grade, and units. Rules read profile fields, never crop names (ADR 0003).
- **Scenario harness and evaluation runner:** runs a fixture through any negotiation method and outputs the event log, outcomes, and rule-check results. Supports live, replay, and synthetic modes, always labeled.
- **Public API:** household, donor, and food bank operations. It reads from records and never decides anything.
- **Integrations:**
  - **AGNTCY:** A2A between organization containers, plus Directory search. Skip SLIM group chat, which is experimental.
  - **n8n:** approval requests with authenticated callbacks bound to a version, household texts, and the "can't make it" release.
  - **ElevenLabs:** the voice agent posts transcripts to the API.
  - **Beeceptor:** mocks of each organization's systems, plus the cooler-failure switch.
- **Deployment:** one AWS EC2 machine running Docker Compose, with one container per organization agent plus the API, Directory, and Postgres. One public HTTPS endpoint, and keys in Secrets Manager.

### Architectural rules (from the ADRs; every module must respect them)

- **No central decider:** nothing can commit an organization to something it didn't approve (ADR 0001). The fair-share table is a published shared rule that assigns nothing (ADR 0009).
- **The AI never produces numbers:** calculators first, calculator tools for anything extra, a number check on every output (ADR 0002).
- **Sponsors never decide:** n8n carries a human's decision, and Beeceptor mocks aren't authoritative records (ADR 0004).
- **Privacy:**
  - No names, addresses, or income questions.
  - The SNAP answer is optional, never changes the fair share, and agents see it as counts only.
  - Requests expire after 7 days.
- **No silent waste:** every pound ends in a recorded pathway.

## Testing Decisions

- **Good tests check outcomes at a seam, not internals.** Given a scripted day, assert what was committed, where every pound went, each household's fair-share balance, which candidates got reason cards, and which rules held. Don't assert on prompts, internal function calls, or the order of internal steps.
- **Seam 1: the scenario harness.** This is where all backend behavior is tested. Each test is a fixture plus expected outcomes, and every run also checks these rules automatically:
  - zero invalid or unauthorized commitments
  - no double booking of storage, trucks, or produce
  - pounds conserved per item across custody changes
  - no household above its fair share while another at the same food bank is below it
  - every approval tied to the current version
  - no auto-commit at the deadline
  - every pound with a pathway
  - number-check failures counted
- **Scenarios** (from `docs/MVP_DESIGN.md` section 16):
  - a normal afternoon
  - more produce than storage
  - more households than produce
  - a cooler failure
  - a condition doubt or no agreement

  Each runs under first-come-first-served, nearest food bank, rules-based, and LLM negotiation on identical inputs.
- **Seam 2: the public API contract.** The real API is live from day one with example data. Contract tests check that each endpoint's real logic returns the same shapes as the agreed examples, so the screens never need to change.
- **LLM runs:** compare repeated runs and report the variation. Use replays for rehearsal. Keep live LLM runs within the $100 budget.
- **Prior art:** none. This is a new project with no code yet. The scenario fixture format and rule checks agreed on contract day become the pattern for every later test.

## Out of Scope

Everything in `future scope/`:
- the rescue fund and all money flows
- volunteer drivers and the coordinator role
- community fridges
- shelters and people experiencing homelessness
- cooked or prepared meals and restaurants
- farm harvest economics and gleaning
- cross-docks and processors
- compost and animal-feed partners
- home delivery
- multi-city regions
- live shadow runs and the full whole-chain test catalog

Also out of scope: income verification, payments, SLIM group chat, and Kubernetes.

## Further Notes

- **Build order** (from the design):
  1. A and B start rules-based negotiation in one process, on fixtures.
  2. B adds produce profiles and the fair-share calculator.
  3. The frontend person builds screens on the real API skeleton, from day one.
  4. C deploys to AWS early.
  5. C wires up AGNTCY and the cooler-failure path.
  6. B adds LLM negotiators and the front desk.
  7. C adds n8n, and C with the frontend person adds ElevenLabs.
  8. Everyone helps with evaluation runs, dashboards, and demo rehearsal.
- **Biggest risks:**
  - AGNTCY setup (verify early, and label any in-process fallback)
  - sponsor plan limits (unverified)
  - LLM run cost and variation
  - the frontend person blocked on the backend, which the day-one real API skeleton prevents
- **Proposed values still open:** the fair-share table numbers, the exact models per role, the headline measures (produce wasted and worst-served fair-share coverage), and verified Market Match markets near the demo region.
- **Headline claim, reported honestly:** worst-served fair-share coverage and produce wasted, compared against first-come-first-served. If negotiation doesn't win, say so.
