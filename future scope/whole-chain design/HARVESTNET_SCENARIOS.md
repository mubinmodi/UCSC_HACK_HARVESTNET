# HarvestNet — scenarios and evaluation catalog

**v1 framework baseline, frozen October 10, 2026.** This document freezes the evidence contract for testing the [framework](CURRENT_DESIGN.md); scenario inputs and outcomes remain variable. Live evidence, food profiles, organization policies, and available resources determine each outcome. No integration, evaluation, or operational transfer has been executed by this review.

The [historical numerical fixture](archive/2026-10-10-numerical-fixture.md) preserves earlier arithmetic. Its quantities, costs, clocks, and desired endings are synthetic examples, not current product requirements.

## One harness, three input modes

| Mode | Inputs | What it can establish |
|---|---|---|
| Live shadow | Current source responses and confirmed declarations; proposals only, without operational commitments | Whether adapters and assessments work with present evidence |
| Replay | Recorded responses and events, released at their original availability times | Reproducible comparisons and diagnosis of failures |
| Synthetic | Explicitly invented lots, resources, policies, approvals, and injected faults | Whether declared constraints and recovery behavior hold under controlled conditions |

All modes use the same assessment, negotiation, validation, hold, and approval path. The coordinator can see the mode and the provenance of each consequential input. A cached response is identified separately from both a current observation and an invented value. Offline success does not prove sponsor integration.

Replaying a negotiation requires its incoming information and timing, not just its final transcript. Methods must not see future requests or observations earlier than they became available. Exact language-model reproduction is not guaranteed; retain model settings and repeat runs to measure variation.

## What each run records

A run manifest identifies the scenario, food-profile and organization-policy versions, initial resources and private-data permissions, lot and request identities, observation window, and methods being compared. It also records:

- Original and normalized source records, units, product/geographic scope, observation/retrieval/availability times, freshness limits, and live/cached/synthetic labels.
- Resource capacities, quotes, occupied intervals, costs, existing commitments, and who owns each approval.
- Approval behavior, negotiation stopping rules, deadlines, fault schedule, message delays, tool permissions, and declared API/model budgets.
- Model, prompt, tool and adapter versions where applicable; seeds for controllable randomness; calculator and validator results.
- Every draft, attributed amendment, reason card, hold, release, approval, commitment, acknowledgment, receipt, and measured outcome.
- The evaluation cohort and metric definitions, declared before viewing results.

Private organization records remain within their authorized boundary. An evaluator with permission to inspect a private record does not grant negotiators access to it. Missing evidence is retained as missing, rather than backfilled after the outcome.

## Initial food-profile families

These are profile requirements for the four planned demonstration events. They are not completed operational profiles. Each needs a reviewed version plus evidence about the actual lot. Published storage guidance, safety requirements, actual condition, and simulation assumptions remain distinct.

| Event and profile family | Properties and evidence to assess | Source and current status |
|---|---|---|
| Farm strawberries | Harvested or still in field; maturity/condition; picking, packing and prompt cooling needs; packaging; exposure history; storage and transport compatibility; receiving or processor specifications | [UC Davis strawberry guidance](https://postharvest.ucdavis.edu/produce-facts-sheets/strawberry) and [USDA Agriculture Handbook 66](https://www.ars.usda.gov/is/np/CommercialStorage/CommercialStorage.pdf) provide produce guidance. Lot condition, crew throughput, cooling capacity, usable life, and quotes need local records or labeled test assumptions |
| Distributor lettuce | Variety and whole versus processed state; packaging; cooling and exposure history; freezing and ethylene sensitivity; compatible storage; receiving windows; documented reason for commercial rejection | [UC Davis crisphead](https://postharvest.ucdavis.edu/produce-facts-sheets/lettuce-crisphead), [romaine](https://postharvest.ucdavis.edu/produce-facts-sheets/lettuce-romaine), and Handbook 66 support the relevant produce profile. A whole-head profile cannot automatically authorize fresh-cut product; actual handling and eligibility remain to be established |
| Grocery dairy | Exact product and package state; label and lot identity; applicable holding requirements; exposure and date records; packaging integrity; recipient acceptance; supported pathways | Product/operator specifications and [FDA donation guidance](https://www.fda.gov/food/retail-food-industryregulatory-assistance-training/key-steps-donating-food-retail-food-establishments) are inputs. A generic dairy label cannot establish one shelf life or handling rule for every product |
| Restaurant prepared meals | Recipe, ingredients and allergens; preparation and holding records; hot or cold handling path; packaging; portions and measured weight where needed; serving capability and deadline | Operator records and FDA donation guidance are inputs. Meals need a recipe/process-specific profile; produce storage references do not authorize them |

Profile fields record a reference or an explicit assumption, applicability, review status, and version. Test assumptions permit simulated assessments; they do not become evidence for live eligibility.

A farm's preparation ceiling is its resource observation, not a strawberry property. A soft sublot does not automatically qualify for upcycling. A refrigerated vehicle does not automatically fit every crop. A temperature reading requires exposure duration, lot location, and the relevant profile before it can establish a handling problem.

Generality tests change maturity, processing state, temperature/exposure requirements, packaging units, and compatible resources. Include a chilling-sensitive product using [UC Davis tomato guidance](https://postharvest.ucdavis.edu/produce-facts-sheets/tomato). Changing only the crop name is insufficient; neither a universal refrigerated setting nor a predetermined truck choice is a valid result. Unsupported assessment requirements must yield an explicit unsupported outcome.

## Scenario families

Each family defines a condition to exercise and an observable requirement. Its quantities, quotes, arrival times, policy settings, and approvals are supplied by the run manifest.

| Family | Conditions to vary | Required evidence |
|---|---|---|
| Feasible independent agreement | Compatible lot, resources, requests, and funding; different organization preferences | A useful, valid draft can become a commitment through matching approvals; every number has a source and calculation |
| Market signal and interpretation | Comparable or mismatched price basis, grades, packaging, geography, age, and local cost | The specialist explains comparability or rejects it. A current USDA observation may support a different conclusion than the old below-cost story |
| Replacement discovery | Withdrawn service, changed capacity, route/window limits, quotes, and multiple candidates | Every candidate has a reason card; owners release or reconcile affected resources; no invented replacement or forced selection |
| Handling disruption | Injected or observed telemetry with different food profiles, exposure histories, and missing records | The assessment follows evidence and the profile. A synthetic fault stays labeled; uncertain condition reaches the responsible reviewer |
| Shared-resource contention | Overlapping transport, storage, preparation, or fund requests across events | Owners cannot promise the same resource twice; feasible alternatives or preserved disagreement are recorded |
| Cross-dock and onward movement | Collection deadline precedes recipient availability; onward transport changes or fails | Storage, both legs, receiving, funding, and handling form a complete feasible agreement; food is not counted twice in transit |
| Shared rescue fund | Scarcity, changing requests, known-request earmarks, partial awards, reserves, and participant refusal | Versioned policy is applied consistently; refusal releases provisional funds; downstream opportunities are reassessed |
| Binding non-agreement | Unsupported handling, no valid recipient, incomplete funding, unavailable capacity, or missed approvals | No commitment is fabricated. Reasons distinguish infeasibility, missing evidence, and voluntary refusal |
| Evidence failure | Outages, old observations returned by a fresh call, conflicting records, wrong units, or expired cache | Consequential uncertainty blocks the affected commitment; optional information has a declared degraded path |
| Changed or replayed approval | Revised terms, delayed approval of an old version, duplicated messages, or identity mismatch | Current obligations require current authorized approval; an old or duplicated message cannot create another commitment |
| Uncertain execution | Missing acknowledgment, partial pickup/delivery, expired provisional holds, or delayed receipt | Reconcile before reuse; retain completed actions and incurred costs; do not equate missing acknowledgment with failure |
| Untrusted or private input | Instructions inside API text or transcripts; requests for another organization's private records | Tool scope, disclosure rules, and authority remain intact; adversarial text becomes evidence to handle, never permission |
| Generality and unit changes | Several foods, maturity states, packaging conversions, unfamiliar organizations, and unsupported profiles | Common procedures respond to properties and capabilities; no crop-name rule or silent unit conversion determines the result |
| Timing and policy sensitivity | Request order, observation delays, stopping limits, deadline derivation, and alternative fund policies | Sensitivity and arrival-order effects are visible rather than attributed automatically to negotiation quality |

The demonstration selects from these families and shows whatever occurs. It may illustrate a cross-event funding disagreement; it does not require the strawberry split, fund pool, or dairy refusal from an earlier script.

## Round 10 fund-policy checks

The rescue fund's general mandate is confirmed. Claude's urgency bands, day-level aggregation, earmarks, and decision times are a candidate organization policy to evaluate.

Check these mechanical requirements before comparing it:

- Use recipient conditional acceptance of current terms for funding eligibility. Requiring final commitment first would make funding-dependent agreements circular.
- Derive funding-needed-by from remaining approvals and preparation dependencies once. Do not subtract preparation again if the commitment deadline already includes it.
- State the coverage cohort, observation window, included requests, treatment of zeros, and tie-breaks. Preserve request identity so splitting a request cannot quietly increase its influence.
- Earmarks and partial offers are provisional holds with a current agreement version, expiry, and explicit release or conversion. They cannot also appear as spendable cash.
- A partial grant counts as accepted spending only after participants approve a feasible amendment. Declined money becomes available for reconsideration.
- Test unknown later arrivals and delayed information. Waiting until the latest responsible time does not remove every arrival-order effect.

The historical arithmetic exposes why the ending must remain variable:

| Synthetic case | Cash after meals and strawberries | Conditional continuation |
|---|---|---|
| $3,100 pool; $2,400 strawberry grant | $600 | Can cover the assumed $350 lettuce and $250 dairy grants if both agreements are feasible and approved |
| $3,100 pool; $2,300 strawberry grant | $700 | The same assumed grants leave $100 |
| $2,800 pool; $2,400 strawberry grant | $300 | A $300 lettuce offer is short of its assumed $350 need. If declined and released, the assumed $250 dairy grant can fit, leaving $50 |
| $2,800 pool; $2,300 strawberry grant | $400 | An accepted $350 lettuce grant leaves $50, short of dairy's assumed $250 need |

These rows are accounting examples, not approvals or simulated outcomes. Extra funds, changed terms, released earmarks, timing, or refusal can change the result. The old walkthrough's guaranteed dairy refusal does not follow from arithmetic alone. The approximate funding times and assumed approval leads also need explicit dependencies; they are not validated appointments.

## Fair comparisons

First-come-first-served, rules-based negotiation, and LLM-assisted negotiation receive the same available observations at the same times, organization policies, profiles, calculators, validators, resources, and approval behavior. Each can consider the declared feasible partial-load options. State how failed claims are released and how later opportunities are reconsidered.

A full-information central reference is a separately labeled comparison with privileged information. It cannot silently supply private data to the independent negotiators or be presented as operating under the same information boundary.

Keep development cases separate from held-out evaluation cases. Vary one assumption at a time when diagnosing a result, then test combinations. Report repeated runs, variation, losses, and unsuccessful agreements. Do not edit inputs until HarvestNet beats the baseline.

## Metrics and acceptance evidence

Worst-served coverage is the headline: the lowest received share among the declared recipient/request cohort, including zero receipts. Report food-specific coverage. If using a multi-food or day-level aggregate, publish the aggregation and observation window before the run; a late or split request must not silently change the comparison.

Track separately:

- Offered, proposed, committed, received, projected distributable, and actually distributed quantities.
- Source-lot quantity by final pathway and residual unharvested/unclaimed food; no repeated counting across custody changes.
- Food weight, prepared-meal portions, and request shares without pretending they are interchangeable nutrition measures.
- Quoted, reserved, authorized, and incurred costs; released funds, uncovered expenses, and commitments across all events.
- Valid proposal and agreement rates, refusals, missed requests/deadlines, rejected invalid proposals, human interventions, and disclosure.
- Negotiation time/rounds, API and model failures, retries, service usage, and model variation.

Passing the evaluated suite requires zero invalid or unauthorized commitments, duplicated resources, duplicated source volume, or silently overwritten completed actions. The evaluator checks the full trace for violations, even when the final allocation looks acceptable. Commitment numbers must be traceable, uncertain actions reconciled, and runs must terminate with reasons under the declared stop policy. A system that rejects everything may pass some safety checks and still fail the usefulness evaluation.

Progress through input-contract checks, deterministic checks, replay and fault/concurrency cases, generality tests, paired held-out comparisons, sponsor adapter checks, and live shadow review. A failure returns to the affected layer and becomes a retained regression case.

The framework baseline freezes this evidence contract. It does not certify performance, food eligibility, sponsor entitlements, or universal correctness. Any pilot claim needs actual evaluation and operator review; the coordinator questionnaire is still a draft.
