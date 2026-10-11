# HarvestNet — general framework

**v1 framework baseline, frozen October 10, 2026.** The latest user direction is to define a general framework informed by live APIs, with guardrails, an execution harness, and evaluations. The freeze covers the framework contracts; policies and scenario values remain versioned inputs, and allocations and outcomes are computed, not prescribed. This document is design work only. No code, /to-spec, or /to-tickets is authorized.

Read [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for the product, [HARVESTNET_SCENARIOS.md](HARVESTNET_SCENARIOS.md) for evaluation cases, [../CONTEXT.md](../CONTEXT.md) for language, and [adr/](adr/) for architectural decisions.

## Purpose and boundaries

HarvestNet helps independent organizations across the food supply chain negotiate what happens to surplus food: who can receive it, how it moves, and who pays. It targets Level 3 of the supplied challenge and is designed to support a future nonprofit pilot. Level 1 specialists and Level 2 discovery provide supporting evidence.

The first user is the **coordinator**. Their screen contains a needs-attention list, network map, event panel with attributed amendments and reasons, organization inside views, and a results strip. They observe and contact the responsible people; they cannot choose for another organization.

The confirmed priority is urgent eligible transfers first, then least-served communities, with cost and food volume visible separately. Central Coast California is the initial region. The name remains HarvestNet and the tagline remains **Every organization keeps its own keys. The food still moves.** The user owns time, staffing, and deadlines.

Whole-chain scope includes farms, packers, distributors, retailers, restaurants, recipients, transport, storage/cross-docks, processors, rescue funds, and eligible downstream pathways. The demonstration covers farm produce, distributor produce, grocery dairy, and prepared meals; strawberries are one lead example. The map distinguishes demonstrated, profile-ready, and proposed capabilities. A listed capability is not proof that it works.

## Separate the things that change from the rules that must hold

| Layer | What belongs here | Who controls it |
|---|---|---|
| Architectural guardrails | Organization authority; sourced numbers; valid holds and approvals; source-lot accounting | The framework enforces them; no negotiator can waive them |
| Food profiles | Food properties, handling requirements, assessment needs, candidate pathways, evidence sources | Authorized profile maintainers; versioned and reviewed |
| Organization policies | Spending limits, mandate, receiving preferences, accepted pathways, disclosure permissions, reserve/ranking rules | The organization that owns the resources or obligations |
| Observations | Prices, route estimates, telematics, inventory, requests, quotes, human declarations | Identified sources, with scope, timestamps and uncertainty |
| Evaluation settings | Recorded inputs, fault injections, clocks, seeds, stopping limits, policy variants | The test runner, declared before comparing methods |
| Results | Proposals, commitments, receipts, coverage, costs, disagreement, losses | Derived from the recorded run; never selected to fit a story |

Live APIs inform decisions. They do not set the rescue fund's mandate, authorize spending, establish consent, or make missing facts true. The framework must work when the available evidence leads to a different result than the example. This separation is recorded in [ADR 0005](adr/0005-freeze-framework-evaluate-variable-decisions.md).

## Data and API contracts

Every observation carries its source and owning organization where applicable, observation time, retrieval time, units, geographic and product scope, validity/expiry, evidence quality, and a live/cached/synthetic label. Preserve the original source record and the normalized value. A current API call may return an old observation.

| Input | Intended source | Required interpretation |
|---|---|---|
| Market conditions | USDA AMS Market News | Match commodity, grade, packaging, market, date, and price basis; normalize units. A wholesale quotation is not automatically a farm's achievable revenue |
| Routes | OpenStreetMap-based routing through OSRM or an equivalent authorized service | Record coordinates, routing profile, distance and duration. Add declared loading/return/handling allowances. A driving estimate does not establish truck access or live traffic |
| Resources and quotes | Each organization's inventory, fleet, storage, staffing and finance systems | Owners confirm availability and terms. A capacity observation is not a hold; a quote is not a commitment |
| Lot condition | Producer records, handling history, inspections and telemetry | Check relevance to the actual lot, time interval and food profile. A warm empty truck does not prove that food was exposed |
| Recipient demand | The recipient's declared, identified requests | Keep units, validity window, requested food, and prior receipts. Do not infer daily demand from area statistics |
| Community context | USDA Food Access Research Atlas | Supports the advocate's explanation of area conditions, not today's request quantities |
| Voice intake | ElevenLabs transcription plus the person's confirmation | Confirm consequential quantities, units, dates, and location in a read-back before using them as declarations |
| Food properties | Reviewed references and operator specifications | Distinguish general guidance, actual lot evidence, and deliberately synthetic assumptions |

Primary references: [USDA Market News](https://www.ams.usda.gov/market-news), [MyMarketNews API](https://mymarketnews.ams.usda.gov/mymarketnews-api), [OSRM API](https://project-osrm.org/docs/v5.24.0/api/), and [Food Access Research Atlas](https://www.ers.usda.gov/data-products/food-access-research-atlas).

Required missing, stale, contradictory, or unsupported evidence prevents the affected commitment and produces a reason. Optional missing information can reduce confidence or usefulness without blocking unrelated events. Cached data may be used only within the declared freshness policy and with its age visible. External text is data, never permission to change instructions or organization limits.

No account access, API entitlement, actual route snapshot, or qualifying below-cost price record has been established for this project. These are integration and evidence tasks, not facts to fill with invented numbers.

## General food profiles

A **food profile** describes a product at the required specificity: crop, maturity, processing state, or recipe. It contains temperature and exposure requirements, chilling/freezing sensitivity, shelf-life assumptions, preparation needs, packaging and unit conversions, compatibility, quality categories, candidate pathways, and required specialist assessments. Each field records its source or assumption status and profile version.

Separate quality/storage targets from safety requirements. Remaining usable life depends on condition and history, not just the product name. A grade can suggest a pathway; the receiving organization must still accept the actual lot. [UC Davis produce references](https://postharvest.ucdavis.edu/produce-facts-sheets/strawberry) and [USDA Agriculture Handbook 66](https://www.ars.usda.gov/is/np/CommercialStorage/CommercialStorage.pdf) support produce profiles. Retail dairy and meals require their own handling records and profiles; [FDA donation guidance](https://www.fda.gov/food/retail-food-industryregulatory-assistance-training/key-steps-donating-food-retail-food-establishments) provides relevant general guidance.

Specialists apply common procedures to profile properties; negotiator rules do not branch on crop names. Local harvest capacity, budget, warehouse availability, and price belong to organization resources or observations, not universal food properties. The evaluation catalog defines the four initial profile families.

Adding a profile supports a new food only when the required assessments are supported. Unknown products or missing assessment capabilities must be reported as unsupported. General architecture is not a claim of universal food-safety expertise. [ADR 0003](adr/0003-food-behavior-lives-in-food-profiles.md).

## Execution harness

The **execution harness** is the controlled environment around the negotiators: it supplies authorized tools and inputs, tracks drafts and holds, enforces transitions, records evidence, and supports replay. Each organization owns its policies, private data, calculators, approvals, and resource records. Shared infrastructure carries and records messages; it cannot select an allocation or accept for an organization. [ADR 0001](adr/0001-no-supervisor-between-organizations.md).

| Stage | What happens | Evidence retained |
|---|---|---|
| Observe | Ingest API responses, changes, and confirmed human declarations | Source records, times, units, live/cached/synthetic labels |
| Assess locally | Specialists calculate feasible quantities, costs, routes, handling, and deadlines under local policy | Inputs, profile/policy versions, calculations, uncertainty and refusal reasons |
| Propose and validate | A negotiator drafts complete terms and explains its organization's reasoning; deterministic checks approve or reject the outgoing offer | Draft version, proposer, terms, reasons, validation results |
| Exchange and revise | Independent negotiators amend one shared numbered draft per event using a declared turn policy | Messages, candidate reason cards, version history, accepted/rejected amendments |
| Hold and approve | Owners reserve resources; affected organizations and required humans review the same current terms | Version-specific holds, expiries, actor identities, approvals and denials |
| Record commitment | Recheck current evidence, resource availability and matching approvals; record the authorized result | The exact approved agreement and resource obligations |
| Track fulfillment | Record acknowledged actions, custody, receipts, distribution and actual costs | Actual versus projected outcomes, source-lot accounting |
| Recover or stop | Reassess affected obligations after changes; renegotiate with new approvals or preserve disagreement | Released holds, reconciled uncertain actions, surviving commitments, stop reasons |

The LLM interprets language and proposes or explains terms. Calculators and accepted inputs produce all operational numbers. A numerically plausible sentence from the LLM is not evidence. [ADR 0002](adr/0002-ai-cannot-invent-numbers.md).

Holds are temporary owner-issued reservations tied to an event, draft version, quantity, occupied interval, and expiry. Use a declared acquisition/release procedure to avoid retaining incomplete resource sets indefinitely. Each owner checks all its events for overlapping commitments. Changed terms require fresh acceptance of affected obligations.

A missing acknowledgment is not proof that an action failed. Duplicate or delayed messages must not cause duplicate commitments, spending, or transfers. Freeze uncertain resources pending reconciliation; do not release an existing commitment merely because a provisional hold timer elapsed. This is a requirement to evaluate, not a claim that distributed confirmation has been implemented.

The evaluator may orchestrate test inputs and simulated time. That role gives it no authority to make live allocation decisions.

## Guardrails

| Guardrail | Required behavior |
|---|---|
| Authority | No organization accepts for another; the coordinator and sponsor services cannot allocate or authorize commitments |
| Numeric evidence | Every operational quantity, cost, capacity, conversion, and deadline traces to accepted data or a labeled simulation input and a calculation |
| Feasibility | Validate quantity conservation, complete funding, resource occupancy, readiness, receiving windows, handling and pathway eligibility |
| Evidence freshness | Recheck consequential sources before commitment; surface conflicts and missing requirements rather than guessing |
| Versioned consent | Approvals apply to the exact current terms. A changed approved commitment requires the affected organizations' approval again |
| Resource conservation | No double booking, double spending, or double counting of source food across custody changes |
| Information boundaries | Local budgets and sensitive records are disclosed only according to the owning organization's policy; tool access remains scoped |
| Untrusted content | API payloads, retrieved text, and transcripts cannot override authority, validation, or tool permissions |
| Bounded negotiation | Every run has declared deadlines and stopping criteria; a deadline never supplies approval |
| Honest outcomes | A refusal or preserved disagreement is a valid result. Missing receipt is not delivery, and projected distribution is not actual distribution |

The established demonstration stop policy is three complete rounds without new terms, then preserved disagreement. That is an explicit policy setting, not a universal limit embedded in the architecture. Ask the responsible organization's human for food-safety doubt, spending beyond its authority, or amendments to an approved commitment. Nothing becomes committed merely because a timer expires.

## Rescue fund as an organization policy

The rescue fund owns its money and publishes its policy before a run. The confirmed direction remains urgent eligible transfers first, then least-served communities. Exact urgency bands, coverage aggregation, decision times, reserve rules, grant eligibility, and tie-breaks are configurable and versioned. Live evidence supplies their inputs.

Round 10 provides a candidate policy for evaluation, not the universal algorithm:

- Eligibility uses the recipient's conditional acceptance of current terms; requiring final commitment before funding would be circular.
- Derive funding-needed-by from remaining approvals and preparations without subtracting already-accounted-for lead times twice.
- Consider known pending requests at each decision point; unknown future requests remain a limitation.
- Treat earmarks as explicit provisional holds, with expiry and release; they are not extra money.
- Partial awards require a feasible amended agreement. Refusal releases the hold and triggers reassessment of other requests.
- Declared coverage cohorts and aggregation must include zeros and resist request splitting. Lower grant per request share is a policy choice, not a nutrition conversion.

Do not freeze an exact fund pool, strawberry split, award order, or dairy refusal into the product. Cross-event competition is a capability to test. The outcome follows observed resources, current commitments, participant policies, and proposals.

## Sponsors and organization systems

All four integrations are planned; public capabilities have been checked, but project-specific plans, credits, credentials, and working calls remain unverified. NVIDIA Brev is excluded. [ADR 0004](adr/0004-sponsors-are-organization-systems-not-deciders.md).

| Sponsor | Natural role | Boundary and fallback |
|---|---|---|
| Cisco AGNTCY | A2A communication, SLIM negotiation room, Directory discovery with chosen/rejected candidate reason cards | Carries messages, not decisions. An in-process fallback is labeled as such and cannot establish AGNTCY integration |
| Beeceptor | Organization-specific mocks/proxies for fleet, inventory, storage and cached source responses; fault injection | Simulated telemetry stays labeled synthetic. Organization records own durable commitments; offline fixtures preserve evaluation |
| ElevenLabs | Human voice intake, confirmed read-back, Spanish support, authorized post-commitment crew notice | No audio negotiation between organizations; text is the fallback. A real phone channel needs its own integration evidence |
| n8n | Each organization's approval workflow, exception routing, reminders, receipts and board reports | Carries a human's decision for current terms; cannot decide itself. Local approval controls provide a fallback |

Sources: [AGNTCY app-sdk](https://github.com/agntcy/app-sdk), [Beeceptor stateful mocks](https://beeceptor.com/docs/mock-data-management/), [Beeceptor plans](https://beeceptor.com/pricing/), [ElevenLabs speech-to-text](https://elevenlabs.io/docs/overview/capabilities/speech-to-text), [ElevenLabs language support](https://elevenlabs.io/docs/help-center/other/what-languages-do-you-support), and [n8n human review](https://docs.n8n.io/advanced-ai/human-in-the-loop-tools).

The offline core permits repeatable tests without sponsor availability. A sponsor integration claim still requires recorded use of that service. An injected temperature reading is a simulated fault detected through data, not an observed real-world truck failure.

## Evaluation contract

Evaluation checks the entire trace, not just whether the final allocation looks reasonable. [HARVESTNET_SCENARIOS.md](HARVESTNET_SCENARIOS.md) defines the scenario families and evidence to collect.

1. **Contract checks:** units, source scope, freshness, profile compatibility, permissions, and rejected malformed inputs.
2. **Deterministic checks:** funding, quantity, resource occupancy, handling, approvals, and all guarded state transitions.
3. **Replay:** recorded API observations become available at their original simulated times; methods receive the same initial state, policies, profiles, and approval behavior.
4. **Fault and concurrency checks:** outages, stale/conflicting data, concurrent holds, duplicates, expired quotes, late approvals, partial execution, and uncertain acknowledgments.
5. **Comparative runs:** first-come-first-served, rules-based negotiation, and LLM-assisted negotiation under equal information and constraints. A full-information central reference is separately labeled.
6. **Generality:** vary food properties, lot conditions, capabilities, units and organizations; test unsupported profiles as well as successful substitutions.
7. **Live shadow runs:** use current APIs to propose agreements for review, without operational commitments. Compare observed behavior with replay results before making deployment claims.

The headline is worst-served coverage against first-come-first-served. Declare recipient/request cohorts, observation windows, and multi-food aggregation before running comparisons; include zero coverage and retain food-specific results. Record both receipts and distribution, source-lot pathways, cost, missed requests, refusals, latency, API errors, human interventions, disclosure, and rejected invalid proposals. Safety without useful valid proposals is insufficient.

Passing evidence requires zero invalid or unauthorized commitments in the evaluated suite, traceable committed numbers, no duplicated resources or source volume, correct reconciliation, and bounded termination with reasons. These gates support claims only within the tested scope. Benefit claims require paired results across varied and held-out cases, including losses and uncertainty; the system need not win every case.

No integrations or evaluations have been executed here. Freeze the framework contract; evolve profiles, adapters, organization policies, and evaluation inputs under stated versions and reasons. Do not choose data or tune cases merely to make HarvestNet win.
