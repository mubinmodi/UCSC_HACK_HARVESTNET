# Historical numerical fixture — October 10, 2026

This preserves the earlier worked strawberry example for arithmetic regression and review history. It is not the current product specification, a required live outcome, or validated operational data. The current [evaluation catalog](../HARVESTNET_SCENARIOS.md) and [framework](../CURRENT_DESIGN.md) supersede its main-versus-variant framing. Numbers may be reused only as explicitly identified synthetic test inputs.

---

# HarvestNet — whole-chain scenario sheet

October 10, 2026. Fixture revised in Codex Round 6; funding direction updated with the user decisions in Round 9. Read with [CURRENT_DESIGN.md](../CURRENT_DESIGN.md). This is a proposed simulation fixture. Every quantity, cost, capacity, request, and time below is an assumption, not an observed operational value. Arithmetic and declared intervals are reviewable; routes, pallet volume, labor throughput, handling profiles, and actual outcomes remain unvalidated. Historical fixed-pledge examples are retained as a sensitivity case below.

## Scenario clock and resources

Use hours relative to a simulation start, t0. These are not real-world appointment times or universal shelf-life rules. Weight is the simplified capacity unit; operational validation must also cover pallet volume and packaging.

| Resource | Owner and assumed capability | Availability / limit |
|---|---|---|
| R1 | Original refrigerated transport provider | 8,500 lb; failure at t0.5 makes every unexecuted affected quote or reservation unavailable |
| R2 | Replacement provider, found by capability search | 7,000 lb; separate sequential runs with scenario-approved handling profiles and turnaround intervals; operational validation pending |
| C1 | Independent cooled van provider | 2,000 lb; processor run only, reserved t23–27 |
| V1 | Independent prepared-food carrier | 180 lb in an authorized holding setup; meal run reserved t1–2 |
| X | Cross-dock operator | 3,500 lb compatible cold storage; lettuce occupies 3,000 lb t31–36 |
| Bank A | Receiving and distribution organization | Strawberry limit 4,500 lb; only 3,000 lb in preferred early slot; physical cold storage 4,500 lb shared with dairy over time |
| Bank B | Rural receiving and distribution organization | Strawberry acceptance/distribution limit 4,000 lb; declared unmet demand 8,000 lb |
| Y | Lettuce pantry | Can receive and distribute 3,000 lb; receiving opens t36 and closes t38 |
| Shelter S | Prepared-meal recipient | Can receive and serve 150 meals, modeled as 180 lb |
| Rescue fund | Independently controlled funding participant | Shared ceiling $3,100 for this scenario batch; optional scarcity variant $2,800. No automatic per-event allocation |

Operational requests are synthetic: A needs 4,500 lb of strawberries, B needs 8,000 lb, Y needs 3,000 lb of lettuce, A's pantry network needs 1,500 lb of dairy, and S requests 150 meals. They are not inferred from annual county hunger statistics. Need denominators stay fixed within each event; deliveries decrement unmet requests in any repeated-event evaluation.

## Deep event: field strawberries

Farm F offers a modeled 10,000 lb field lot. It begins harvesting only after a confirmed agreement. Assume an assessed 1,000 lb sublot meets a processor's separate input specification; softness alone cannot establish eligibility. The other modeled berries are eligible for fresh use under the scenario's approved lot profile.

All harvest commitments must be final by t3.5. Assume 20 workers harvesting t4–10, with a combined preparation ceiling of 8,000 lb. This implies 66.7 lb per worker-hour at full capacity: an unverified throughput assumption, not a measured picker rate. Packing and cooling operate in rolling batches immediately after picking; the last batch is assumed ready by t12, with suitable cold holding until pickup at t24. Do not leave early batches warm until the harvest ends. UC Davis emphasizes prompt cooling and reports deterioration when cooling is delayed; it does not validate this crew or cooling schedule. [UC Davis strawberry handling guidance](https://postharvest.ucdavis.edu/produce-facts-sheets/strawberry).

The farm's internal assessment must check recoverable quantity, preparation cost, crew and cooling capacity, packaging, batch readiness, cold holding, and collection timing. Requests above the shared 8,000 lb preparation ceiling are rejected. If commitments or batch readiness miss their deadlines, downstream terms must be renegotiated rather than silently retaining the original times.

Before R1 fails, a possible 8,000 lb donation plan sends 4,000 lb to each bank. Recovery at $0.60/lb costs $4,800 and R1's bundled trip quote is $600: $5,400 total. Under the quantity model below, maximum bank contributions are A $2,000 and B $1,500; a $1,900 grant closes the gap. This is an illustrative offer, not committed expenditure. No field work starts before the failure at t0.5.

After failure, R2 can move 7,000 lb for a bundled $1,200 quote. Recovery is $0.60/lb, split for discussion into $0.40 harvest, $0.10 packing, and $0.10 cooling. Thus 7,000 lb recovery costs $4,200 and the complete donation bundle costs $5,400. These rates and trip quotes are uncalibrated assumptions. Bundled quotes already include the modeled driver's labor and empty return; do not add those expenses again.

The strawberry request may qualify for up to $1,800 base support, plus up to $600 more if every named strawberry bank reaches at least 40% of its declared unmet strawberry demand. These are request limits against the shared fund, not reserved envelopes. A single-recipient agreement can receive base support in this fixture; B still stays in the extra-support denominator with zero fulfillment. Only required expenses are funded. Eligibility does not guarantee a grant: shared funds must be available and the fund must accept the current agreement.

### Contribution model and shared fund

Use private illustrative affordability ceilings: A can offer at most $0.50 per received pound, capped at $2,100; B at most $0.375 per received pound, capped at $1,500. A has a separate $300 receiving reserve for a late slot. These invented ceilings are not automatically pledged, and affordability is not a complete preference model. Each bank decides whether the quantity, timing, actual pledge, and residual need make an agreement acceptable. For comparable arithmetic only, the table assumes both banks pledge their ceilings and the fund covers the remaining eligible expense.

All four events request the same $3,100 pool. The user-approved direction is urgent eligible transfers first, then least-served communities. The fund must publish the detailed eligibility, urgency bands, fulfillment measures, decision windows, and deterministic tie-break before negotiation. Retain crop-specific fulfillment, prepared-meal portions, timing, and dollars as separate measures; ranking only pounds per dollar would bias comparisons across unlike foods. The fund may propose a partial award, reserve its own money against an agreement version, or refuse with a reason. The reservation protocol prevents simultaneous promises from exceeding its pool. All methods receive the same policy.

The worked finance examples below assume no additional protected contingency reserve. Claude's proposed 15% reserve would leave only $2,280 available after meals in the $2,800 variant, below the $2,300/$2,400 strawberry grants. A separate reserve variant needs explicit access and release rules and a recomputed timeline; that percentage is not user-approved.

The nominal early candidate uses exactly $3,100, so it does not by itself demonstrate funding scarcity. Run a separate $2,800-pool variant with the same requests to expose a $300 gap and require changed terms or an explicit refusal. Reallocation alone cannot erase that gap.

### Competing post-failure agreements

| Candidate | A / B quantities | A / B fulfillment | Farm / transport cost | Maximum bank support + eligible grant | Interpretation |
|---|---|---|---|---|---|
| First-claim, full truck | 4,500 / 2,500 lb | 100% / 31.25% | $4,200 / $1,200 | $4,837.50: A $2,100 + B $937.50 + grant up to $1,800 | $562.50 short |
| First-claim, reduced quantity | 4,500 / 1,500 lb | 100% / 18.75% | $3,600 / $1,200 | $4,462.50: A $2,100 + B $562.50 + grant up to $1,800 | $337.50 short |
| First-claim, A alone | 4,500 / 0 lb | 100% / 0% | $2,700 / $1,200 | $3,900: A $2,100 + base grant $1,800 | Financially feasible; needs the late receiving slot and grant acceptance |
| Threshold-feasible amendment | 3,800 / 3,200 lb | 84.44% / 40% | $4,200 / $1,200 | Ceiling $5,500: A $1,900 + B $1,200 + grant up to $2,400 | Requires only $2,300 grant; $100 of eligibility remains unused |
| Advocate's proposed amendment | 3,000 / 4,000 lb | 66.67% / 50% | $4,200 / $1,200 | $5,400: A $1,500 + B $1,500 + grant $2,400 | Improves lower fulfillment; needs voluntary acceptance and the full grant |

A can accept up to 3,000 lb at t25 using an existing volunteer shift. Larger loads arrive at t26–27 and require $300 from its separate receiving reserve. Against 3,800/3,200, the early 3,000/4,000 candidate reduces A's illustrated pledge by $400 and saves $300 receiving expense, but gives A 800 lb less. That can explain a negotiation motive; it does not establish A's consent. The fund also spends $100 more on the early candidate. Do not fabricate a unanimous result.

For a 3,000/4,000 candidate, R2's occupied interval is t23–27.5: pickup t24, A receives t25, B receives t26. Larger A allocations extend the occupied interval through t28, with B receiving by t27 when present. This blocks the distributor's initial overlapping transport request. Late receiving expense is additional to transfer cost and belongs in total cost metrics.

Keep receipts separate from distribution. Assume A's accepted strawberries are distributed by t31 and B's by t32, for either slot. Those are simulated events to execute, not facts implied by acceptance. A distribution failure must preserve receipt records, reduce distributed quantity, and potentially block the later dairy receipt.

### Sensitivity to the contribution model

The earlier fixed sponsorship case remains valid as an alternative assumption: A pledges $2,100 and B $900 independent of positive quantity received. Then 4,500/1,500 costs $4,800 and is funded exactly with the $1,800 base grant; both 7,000 lb threshold-passing candidates are funded with $2,400. Fixed sponsorship may reflect a mission budget, but requires a rationale and actual consent. It is not inherently impossible.

Separately keep quantity-linked rates but reduce B's cap to the earlier $900. Then the 3,800/3,200 ceiling is $5,200, short $200; the 3,000/4,000 ceiling is $4,800, short $600. Claude's proposed model changes both the contribution rule and B's cap. Vary those independently rather than adjusting assumptions until a preferred split wins. The A-only case also prevents an automatic claim of zero baseline rescue. State each baseline's partial-load search and refusal policy before comparing methods.

### Processor sub-agreement and residual produce

Processor P may independently accept the assessed 1,000 lb sublot. It pays F $600 for recovery and C1 $150 for cooled collection: $750 from P's own authorized budget. C1 picks up at t24 and delivers by t26 within its t23–27 reservation. The combined donation and processor preparation is 8,000 lb, within F's limit. P's processing costs and finished-product yield require its own assessment; raw input weight is not counted as finished jam or a donated meal.

If both agreements complete, source-lot accounting is 7,000 lb donated, 1,000 lb received for upcycling, and 2,000 lb left unharvested. Until confirmed and executed, display those as proposed or committed destinations, not completed outcomes. If P refuses, the 1,000 lb stays unharvested, raising that residual to 3,000 lb. There is no automatic feed or compost disposition.

### Separate processor-competition variant

Replace the soft-sublot purchase with an alternative firm order for exactly 2,000 lb fresh-eligible berries at $0.80/lb, with a 2,000 lb minimum. P pays $1,600 to F and $150 to C1, or $1,750 total before its own processing expenses. This synthetic minimum creates an actual capacity trade-off: the shared 8,000 lb preparation ceiling then leaves at most 6,000 lb for donation. Without a minimum, a 1,000 lb processor purchase could coexist with the original 7,000 lb donation and would not necessarily compete.

One candidate is A 2,800/B 3,200 lb donated. Recovery $3,600 + R2 $1,200 = $4,800; ceiling pledges A $1,400 + B $1,200 + grant $2,200 close it. Fulfillment is 62.22%/40%, satisfying the extra-support condition. Farm receipts are $3,600 for donation recovery + $1,600 for P's order = $5,200 against $4,800 total preparation cost, a $400 modeled surplus before any omitted costs. Compare this with the donation-first candidate's $4,800 receipts against $4,800 preparation cost. The farm now has a reason to prefer the commercial bid; recipients and the fund may prefer another allocation.

These are mutually exclusive processor offers, not two purchases of the same capacity. Both fresh input eligibility and P's processing economics still require assessment. Record 6,000 lb donation, 2,000 lb upcycling input, and 2,000 lb unharvested only if that candidate executes; do not count commercial output as donated food. Keep this variation outside the core three-minute demo unless it is needed to explain the farm's choice.

### Approvals and a real non-agreement case

The farm approves costs and field work; each bank approves quantity, receiving window, contribution, and distribution plan; each carrier approves its reservation; the fund approves its eligible spend; P approves its purchase and input profile. Uncertain condition or handling evidence goes to an authorized reviewer before commitment. Human approvals are simulated explicitly in the fixture and must be labeled as such.

To test non-agreement, make R2's quote $4,000 and its minimum load 5,000 lb. The cheapest permitted donation trip costs $3,000 recovery plus $4,000 transport: $7,000. Even a loose upper bound on support, A's $2,100 cap + B's $1,500 cap + maximum grant $2,400, is only $6,000. Both changes matter: a higher quote alone might still permit a small partial load. Receiving reserves cannot be repurposed without an explicit amendment. Participants must not invent subsidy or silently lower the minimum. A separately feasible processor agreement may still proceed.

## Other simultaneous events

| Event | Lot, evidence, and recipients | Resources and time windows | Cost and payer |
|---|---|---|---|
| Distributor lettuce | 3,000 lb packed and cooled; commercial rejection documented, no unresolved safety rejection; Y requests the full lot | Initial R1/R2 request t25–27 conflicts with farm. DC needs collection by t30, but Y cannot receive before t36. R2 DC→X t29–31, pickup t30; X holds t31–36. R2 X→Y t35–38, pickup t36, receive by t38; modeled distribution by t42 | Two transport legs $300 + X handling/storage $150 = $450. DC offers $100; request $350 from shared fund |
| Grocery dairy | 1,500 lb intact labeled packages; lot, date, and handling evidence available; A's network requests it | R2 t32–34, pickup t32, receive t34 after A's modeled strawberry distribution by t31. Modeled dairy distribution by t40 | Trip $400; retailer offers $150, requests $250 from shared fund. Receiving resources separately pre-funded |
| Restaurant meals | 150 meals, assumed measured total 180 lb; ingredient/allergen and holding records required; S requests all meals | V1 t1–2, receive t2, modeled serving t3. An approved meal-handling profile is required | Trip $100 requested from shared fund. Existing preparation is sunk; serving resources pre-funded |

R2's intervals do not overlap: strawberry t23–27.5 (or through t28), lettuce first leg t29–31, dairy t32–34, lettuce onward t35–38. Each occupied interval includes its assumed preparation, route, unloading, and return; one-hour gaps remain even after the late strawberry alternative. Validate product handling, cleaning, loading, route duration, and driver availability before treating these as real appointments. No mixed load is assumed. Simulation hours describe fixture logistics, not a development deadline; the user manages time and staffing.

Optional delay variant: delay the late strawberry run by 90 minutes, moving its end from t28 to t29.5 and conflicting with the t29 lettuce reservation. A 30-minute delay is absorbed by the declared slack and must not be presented as a cascade. The provider checks revised pickup and dock deadlines, then renegotiates affected agreements; it does not blindly shift every run. Preserve any completed meal transfer and incurred expenses. A refusal is a valid outcome when the DC deadline cannot be met.

R1's failure invalidates the farm's reserved or proposed service and the distributor's uncommitted early service quote. If both had already obtained overlapping holds on R1, that is a reservation defect, not a successful demo. Show the failed overlapping hold attempt as well as the disruption.

The cross-dock exists to bridge the DC's t30 collection deadline and Y's t36 receiving opening. Holding lettuce on R2 until then would occupy the truck through its dairy job and requires its own cost and handling assessment; it is not a free direct route. Secure onward transport and Y's commitment before collection. Track X occupancy over time. A's dairy must not arrive if strawberry distribution has not freed enough space.

### Combined finance check

For the early 3,000/4,000 candidate, grants requested total $3,100: $2,400 strawberries + $350 lettuce + $250 dairy + $100 meals. Transfer expenses total $6,350: $5,400 + $450 + $400 + $100. Pledges total $6,350 if accepted: $3,100 fund + $1,500 A + $1,500 B + $100 DC + $150 retailer. The separate 1,000 lb processor agreement adds $750, totaling $7,100 across five bundles. This fits the nominal pool exactly; every award still needs a valid reservation.

For 3,800/3,200, strawberry grant $2,300 + other grants $700 = $3,000. A $1,900 + B $1,200 + DC $100 + retailer $150 + fund $3,000 = $6,350 transfer funding, with $300 additional late receiving expense paid by A. A $2,800 pool leaves this candidate $200 short if all other requests remain unchanged, versus $300 short for the early candidate. Compare recipient preferences and grant opportunity cost together. Internal pre-funded operations still consume resources; this is not complete real-world cost accounting.

## Pathways, output, and comparisons

Keep destination classification separate from agreement state, grade, and custody. EPA's environmental tiers are: prevention; donation/upcycling; animal feed/leave unharvested; compost/digestion with beneficial outputs; land application/digestion with disposed outputs; landfill/incineration/down the drain. This does not prescribe social priority or validate a destination's eligibility. [EPA's underlying report, section 5.3](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P101CBWV.TXT).

FDA's donation guidance calls for appropriate handling, records, and applicable local or state requirements. Prepared meals, dairy, and processing need their actual role-specific profiles; this simulation supplies no blanket safety authorization. [FDA donation guidance](https://www.fda.gov/food/retail-food-industryregulatory-assistance-training/key-steps-donating-food-retail-food-establishments).

Feed and compost operators are proposed optional outlet profiles, not executed pathways in this candidate. Prevention remains an upstream capability to assess later; do not label existing-lot donation as prevented production.

Run methods against the entire shared-resource scenario, with identical inputs and eligibility rules. Count each source pound once at its final recorded pathway; DC→X→Y is one 3,000 lb lot. Report receipt, projected distribution, and simulated completed distribution separately. Prioritize full and partial feasible baseline plans, contribution-rule and budget-cap sensitivity, event order, shared-pool scarcity, fixed funding condition with advocacy on/off, and LLM versus rules-based negotiation. Processor competition and transport delay are separate variants, not mandatory additions to one live sequence. No benchmark results have been produced.
