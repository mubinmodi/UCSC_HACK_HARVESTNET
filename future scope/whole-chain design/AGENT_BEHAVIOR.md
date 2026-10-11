# How each HarvestNet agent works and decides

**Status:** proposed by Claude on October 10, 2026, for review by Codex and the user. Not yet agreed. It builds on `CONTEXT.md`, ADRs 0001–0004, and the mandate table and scenario in `docs/CURRENT_DESIGN.md` and `docs/HARVESTNET_SCENARIOS.md`. Example numbers are the scenario's synthetic values.

## 1. One decision loop for every organization

Every organization runs the same loop. Only its specialists, food profiles, limits, and preferences differ (ADR 0003).

1. **Something arrives.** For example a surplus offer, a new draft agreement version, an amendment, a hold request, a disruption, a funding decision, or an approval result.
2. **Specialists check the facts.** Deterministic calculators read the organization's *own* systems (Beeceptor mocks) and the relevant food profile. They return facts and limits, for example "free cold space: 1,200 lb from t25 to t28." No LLM is involved (ADR 0002).
3. **The mandate splits facts into two kinds:**
   - **Hard limits:** things the organization can't do, such as exceed storage, overspend its budget, or miss a food-profile deadline.
   - **Preferences:** things it would rather have, such as an early slot or more food. Its human managers set these weights. In the simulation we set them and label them as assumptions.
4. **The walk-away option sets the bar.** Each organization knows what it gets if there's no deal. For a farm that's leaving the crop unharvested; for a food bank it's receiving nothing; for a trucker, other jobs; for the fund, keeping its money for other requests. **A deal must beat the walk-away option, or the answer is no.**
5. **List the possible moves:**
   - accept the current version
   - reject it, naming the specific limit or reason
   - on its turn, propose one amendment
   - grant or decline a hold on its own resource
   - ask a human
6. **Pick the move.** The organization scores the moves with its own private preferences, against its walk-away option. (The full rule is in section 2.)
7. **The validator re-checks it.** Calculators recheck every number in the chosen move. The LLM can't change a number.
8. **Approval gate.** If the move creates a commitment, exceeds a human-set threshold, or touches food safety, the organization's own n8n workflow asks its human (ADR 0004).
9. **Send and log.** The move goes out over AGNTCY with a short reason, and the event log records it for replay.

## 2. How the negotiator picks a move

| Situation | Move |
|---|---|
| The current version breaks one of my hard limits | **Reject**, naming the limit. On my turn, propose an amendment that fixes it, if one exists. |
| It meets my limits and beats my walk-away, and I see no better amendment the others could plausibly accept | **Accept** |
| It's acceptable, but I can see an improvement | On my turn, **propose one amendment** that helps me without breaking anyone's *published* limits. I can't see their private ones. |
| Nothing acceptable exists and the deadline is near | Keep refusing. **Never go below the walk-away option.** |
| The same terms have come back three times | Stop. The event becomes a **preserved disagreement** (stop rule). |
| Food safety is uncertain, or money or quantity exceeds what I'm authorized for | **Ask a human** |

**Time pressure (proposed):** as an event's deadline gets closer, each organization's minimum acceptable outcome moves *toward* its walk-away option, but never past it. That explains why organizations concede late in a negotiation, and every concession records which change justified it.

**Where the LLM fits, and where rules fit:**

| Step | Rules-based negotiator | LLM negotiator |
|---|---|---|
| Read messy input (voice, free text) | Text fields only | Turns speech or text into a draft offer, which a human confirms |
| Check facts and limits | Calculators | The same calculators |
| Suggest amendments | Picks from a fixed menu (shift quantity by fixed steps, change slot, change cost share) | Can propose creative combinations, such as splitting a lot or trading timing for money |
| Score moves | The same scoring function | The same scoring function |
| Explain reasons | A template sentence | A plain-English explanation that cites the facts |

Both versions share the calculators, scoring, validator, and approvals. The only differences are how creative the amendments are and how readable the explanations are. That's why the rules-based comparison is fair.

## 3. Each organization type

| Organization | What it wants | Hard limits | Walk-away option | Specialists (what they check) | Says yes when… |
|---|---|---|---|---|---|
| **Farm** | Costs covered; no harvested food wasted | Preparation ceiling (8,000 lb); commitments by t3.5; never harvests uncommitted food | Leave the crop unharvested, or sell the soft sublot to the processor | Market (real USDA AMS price vs. harvest cost), cost, harvest and cooling capacity | Payments cover recovery cost for every committed pound and the pickup is confirmed |
| **Food bank** | Usable food reaching its community | Cold space over time, receiving windows, distributing before the food profile's shelf life ends, budget cap | Receive nothing from this event | Storage, demand, receiving labor, budget | The usable food it can distribute is worth more to it than its pledge plus receiving costs, within its limits |
| **Trucker** | Paid trips it can actually run | Capacity, the food profile's temperature range, no overlapping holds, driver hours | Other jobs | Fleet and telematics, route (OSRM), pricing | The quote covers the trip, and the hold fits its schedule. It also *reports* disruptions it detects in its telematics. |
| **Cross-dock** | Paid, compatible use of its space | Occupancy over time, compatible storage zones | Leave the space empty | Occupancy, storage compatibility | There's space for the whole interval and the onward leg is already secured |
| **Processor** | Usable input at a good price | Input specification, its own budget, yield | Buy elsewhere | Input checks, yield, budget | The lot meets its specification and the price is below the value to it |
| **Rescue fund** | Its money doing the most good under its published rule | Pool size, eligibility | Keep money for other requests | Eligibility, coverage, pool balance | It runs fund rule v1: it decides at each request's funding-needed-by time, ranks requests, sets aside money for higher-ranked known requests, and can make partial awards |
| **Advocate** | Better worst-served coverage | Has no resources and no approvals, so it can't accept or reject on anyone's behalf | n/a | Need context (Food Access Research Atlas), coverage so far | It doesn't accept. On its turn, it proposes amendments that raise worst-served coverage and cites evidence. |
| **Distributor / grocery / restaurant** | Avoid disposal cost; get receipts | Required paperwork (rejection reason, date codes, allergen and holding records) | Pay for disposal or compost | Lot evidence, disposal cost | It costs less than disposal and the paperwork is complete |

## 4. Worked example: Food Bank A receives the advocate's amendment

The current version is 3,800 / 3,200. The advocate proposes 3,000 / 4,000.

1. **Specialists:** storage fits either version. The early slot (t25) fits 3,000 lb and the existing volunteer shift, which saves $300 in receiving labor. Its pledge at $0.50/lb is $1,500 instead of $1,900.
2. **Hard limits:** both versions pass.
3. **Walk-away option:** both versions beat receiving nothing.
4. **Preferences decide:** 800 lb less food, against $400 less pledged and $300 less receiving cost. The answer depends on how much Food Bank A's manager values food versus money. In the simulation we set that value and also vary it, so the results show both outcomes.
5. **If A accepts:** the move goes through its n8n workflow, because it's over the 2,000 lb approval threshold. In the demo, this is the live click.
6. **If A rejects:** the reason sent is "800 lb less food is not worth $700 to us." The draft stays at 3,800 / 3,200, and the advocate can try again on its next turn.

## 5. Open items for review

1. Should "walk-away option" be added to `CONTEXT.md` as a term?
2. Is the time-pressure rule acceptable, or should concessions only follow new facts?
3. **Who sets each organization's preference weights?** In the simulation we choose them and label them. The evaluation should vary them, so no single setting decides the headline result.
