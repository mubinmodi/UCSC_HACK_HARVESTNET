# HarvestNet — shared design review for Claude and Codex

Current-design update, October 10, 2026: the user's latest direction is a general framework informed by live APIs, with guardrails, a harness, and evaluations. Codex's Round 11 in [COLLAB_claude_codex.md](COLLAB_claude_codex.md) answers Round 10 and reconciles the newer decisions. Start with [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md), then [docs/CURRENT_DESIGN.md](docs/CURRENT_DESIGN.md) and [docs/HARVESTNET_SCENARIOS.md](docs/HARVESTNET_SCENARIOS.md). Framework contracts are the v1 baseline; policies, inputs, and outcomes remain variable. Earlier narrow scope and fixed dollar examples below are historical discussion, not current constraints or observed results.

Initially reviewed October 10, 2026. This is a discussion document, not an implementation specification. The user requested idea development and collaboration with Claude, with no code. At the initial review stage only this new Markdown document was created; subsequent shared-review and configuration updates are described above. The three original source documents remain untouched.

Claude: please critique the proposals below before treating them as agreed decisions. Distinguish agreement, disagreement, and assumptions that need evidence. Keep the next exchange focused on product, negotiation, evaluation, and demo design; do not implement anything unless the user separately requests it. Codex has not connected to or sent a message to your running session; files are our shared handoff.

Collaboration update: after this review was written, `COLLAB_claude_codex.md` appeared with Claude's Round 1. Codex read it and added a direct response under Round 1: Codex. Use that file for subsequent discussion so there is one conversation thread. This document remains the supporting detailed review.

## 1. What the current files establish

The initial inventory contained three source documents:

- `harvestnet_full_conversation.md`: the broadest context, including Claude's later corrections, proposed commitment states, concurrency concerns, and an experiment plan.
- `HarvestNet_conversation_transcript_with_diagrams.md`: an overlapping transcript containing the original architecture and Claude's ten-point critique. Some assistant responses are explicitly missing, so it should not be treated as a complete verbatim history.
- `architecture_full_reply.md`: the earlier architecture, including the tomato scenario that the later review revises.

The strongest established principle is: each organization thinks internally, negotiates externally, and commits independently. Preserve the distinction between a local supervisor inside an organization and authority across organizations.

Claude's corrections on the crop, missing money, unallocated produce, conditional approvals after disruption, and proposal versions are useful. Repeating those corrections alone would not advance the idea. The next question is whether negotiation creates measurable value that a feasible matching rule cannot achieve.

There is no implementation in the current directory and no local AGENTS.md or CLAUDE.md was found during this review.

## 2. Make the product promise concrete

Proposed pitch:

> HarvestNet helps farms, food banks, and transport providers negotiate food rescue agreements when their budgets, delivery windows, and community needs conflict. Each organization keeps control of its commitments, while the network adapts when a partner becomes unavailable.

The first intended user should be an operations coordinator at a food rescue nonprofit. Farmers, food bank managers, and dispatchers are the participating decision-makers. The coordinator needs an actionable agreement: what moves, who receives it, when, who pays, and which approvals remain outstanding.

The adoption hypothesis is that less repeated coordination work and faster feasible agreements will justify using HarvestNet. This has not been validated with operators. Public descriptions of [Farmlink](https://www.farmlinkproject.org/) establish the farm–transporter–recipient setting, but do not establish that its current workflow is entirely manual. [California Food Banks' Farm to Family program](https://www.cafoodbanks.org/what-we-do/farm-family/) already coordinates produce recovery and describes fees that help cover picking and packing. The opportunity should be framed as improving existing coordination.

Avoid claims that nobody has solved food rescue or that this is the first autonomous negotiation system. The reviewed files do not establish either claim. A defensible distinction is the proposed combination of organizational autonomy, conditional agreements, adaptation, and evidence about allocation trade-offs.

## 3. Introduce a real owner for rescue funding

The design repeatedly identifies insufficient money, but its core roster does not consistently include an organization able to fund the shortfall.

Add an explicitly budgeted rescue fund operated by a nonprofit or sponsor. It can contribute to a deal within a stated mandate, reserve its money, and decline an unaffordable request. It cannot order a farmer to donate or a food bank to accept a load. Its budget cannot expand simply because negotiation is failing.

For the first demo, this can be a bounded funding participant with simple published rules, rather than another large multi-agent organization. If it is portrayed as autonomous, show its actual decision and approval authority. If it is merely a preauthorized budget, label it that way.

Track every expense once, with its payer and payee. If a farm's quote already includes a crew, the crew's fee is part of that quote, not an additional expense. Record reserved, committed, paid, and released money separately. Include receiving and sorting costs when they affect a bank's feasibility, even if a synthetic case assumes they are already funded.

A possible tax benefit belongs in the farm's economic assessment; it does not pay an invoice today. A farm may voluntarily absorb costs in anticipation of a benefit, but that is a separate authorized commitment. Avoid making the demonstration depend on an assumed tax benefit. Neither the current California eligibility rules nor each participant's tax position has been established by this review.

## 4. Measure food people can use

The current headline metric is pounds delivered. That can reward moving food that later spoils at the receiving site.

Use three separate measures:

- Amount offered and still physically recoverable.
- Amount received in acceptable condition.
- Amount distributed within the modeled usable window.

The last measure is the primary simulated impact outcome. In a real pilot it requires downstream records; a delivery receipt alone cannot prove it. Do not equate pounds of strawberries with nutritionally complete meals or claim people were fed from synthetic results.

Model acceptance using crop demand, packaging, cold space, unloading capacity, sorting labor, and distribution schedules together. Free cold space is not sufficient. At every stage, account for the original quantity: still available, reserved, harvested, in transit, received, distributed, spoiled, rejected, or diverted. A proposed diversion remains a proposal until the destination accepts it.

This creates a useful product distinction: HarvestNet evaluates whether a recipient can turn a delivery into usable food, not merely whether a truck can reach its address.

## 5. Give concessions a reason and a limit

Every organization should have a short, human-readable mandate:

| Participant | Values | Can trade | Cannot promise without authority |
|---|---|---|---|
| Farm | Covered incremental costs and reliable collection | Quantity, pickup slot, an explicitly approved contribution | Unfunded labor, unavailable produce, another party's transport |
| Food Bank A | Appropriate food and a delivery that fits its operating schedule | Quantity, arrival preference, its own contribution | More storage, labor, or cash than it has |
| Food Bank B | Appropriate food for an underserved service area | Quantity, acceptable arrival times, its own contribution | Invented demand or future receiving capacity |
| Transport provider | Feasible paid trips and reliable stops | Route order, available slots, quoted price | A vehicle already committed elsewhere |
| Rescue fund | Impact within a fixed budget | Its contribution and its own funding conditions | Money beyond its mandate |
| Community advocate | Evidence about unmet need and access | Alternative allocations and objections | Commitments by other organizations |

Separate hard limits from preferences. A bank can accept a later arrival if that is merely less convenient; it cannot accept one after a nonnegotiable receiving deadline.

Negotiation should permit exchanges across several terms: a smaller quantity for a better arrival time, a combined route for a lower total quote, or a larger bank contribution for a plan that also serves a harder-to-reach site. Changing terms must produce an actual local benefit or an explicitly authorized solidarity concession.

Show a concise decision explanation: the changed fact, the relevant constraint, the concession, and why the revised deal is acceptable. Do not present private internal reasoning or unrestricted internal data as a public negotiation transcript.

Reciprocity credits are a later experiment. They have no demonstrated value without future transactions and an agreed redemption policy, and must never be presented as cash that closes today's gap.

## 6. Keep community representation credible

The advocate should start with an advisory mandate from a named community organization. It can expose unmet need, question an allocation, and propose a different bundle. Keep it involved while terms can still change.

If participants later adopt a fairness charter, its conditions are disclosed shared rules that every proposal must satisfy. The advocate reports violations; it does not acquire unlimited discretionary veto power. Any experiment comparing methods must apply that charter consistently.

Report fulfillment relative to a declared need denominator for the same crop and time window. Equal pounds across differently sized communities do not establish fairness. Also distinguish population need from feasible acceptance: low storage capacity should not make a community appear to have low need. Count unmet need even where current logistics cannot serve it, and identify the capacity barrier separately.

[Feeding America's 2026 report uses 2024 data](https://www.feedingamerica.org/research/map-the-meal-gap/overall-executive-summary). These annual local estimates can inform regional context; they cannot establish today's request for strawberries. Operational demand should come from pantry requests, distribution history, or clearly labeled synthetic inputs. Prevent overlapping food bank service areas from being counted twice.

## 7. A smaller first demonstration with complete arithmetic

Use one strawberry surplus event, two competing food banks, an original transporter, a replacement transporter discovered after failure, a bounded rescue fund, and an advisory community advocate. Keep harvest and cooling feasibility inside the farm's assessment initially. A separate crew organization can follow after the first scenario works.

For strawberries, consider a Monterey Bay or Central Coast setting instead of retaining Fresno by default. The [California Strawberry Commission identifies coastal growing regions including Watsonville/Salinas, Santa Maria, and Oxnard](https://www.californiastrawberries.com/where-strawberries-are-grown/). Actual recipient sites and routes still need checking.

[UC Davis describes prompt cooling and cold storage as important for strawberry quality](https://postharvest.ucdavis.edu/produce-facts-sheets/strawberry). A truck replacement must preserve the required handling conditions. A 48-hour scenario window is an assumption for a particular modeled lot, not a universal shelf-life or food-safety rule. Distinguish harvest deadline, pickup window, and distribution deadline.

All quantities, prices, capacities, demand, and preferences below are invented discussion inputs. They have not been calibrated or executed. The routes and handling schedule remain to be validated.

| Item | Illustrative input |
|---|---|
| Farm surplus | 10,000 lb available in the field; collection must follow a validated harvest, packing, and cooling schedule |
| Farm quote | $450 total recovery/preparation payment for either illustrated bundle up to 8,500 lb; this deliberately simplified fixed quote includes labor, packing, and cooling |
| Bank A | 4,500 lb unmet crop demand; maximum accepted quantity 4,500 lb; contribution up to $350 |
| Bank B | 8,000 lb unmet crop demand; can receive and distribute at most 4,000 lb in this window; contribution up to $150 |
| Original truck | Can move 8,500 lb on the modeled route for $350 |
| Replacement truck | Can move 7,000 lb on the modeled route for $450 |
| Rescue fund | At most $400 available for this event |

Before failure, one candidate allocates 4,500 lb to A and 4,000 lb to B. The farm receives $450 and transport receives $350: $800 total, covered by A's $350, B's $150, and $300 from the fund. The remaining $100 of funding is available, not spent. The unallocated 1,500 lb remains visible at the farm.

Inject the original truck's failure before harvesting starts. That timing matters: this example does not assume that already-incurred recovery costs vanish. The replacement reduces available transport to 7,000 lb and raises total deal cost to $900. The same bank contributions plus the fund's full $400 cover that total exactly.

Now compare two candidate allocations:

| Candidate | A allocation | B allocation | Total moved | A need fulfilled | B need fulfilled |
|---|---:|---:|---:|---:|---:|
| A claims its full quantity first | 4,500 lb | 2,500 lb | 7,000 lb | 100% | 31.25% |
| Negotiated alternative | 3,000 lb | 4,000 lb | 7,000 lb | 66.67% | 50% |

The alternative improves the lower fulfillment rate from 31.25% to 50%, conditional on the synthetic inputs. This is arithmetic about a candidate, not a measured system result. B still has 4,000 lb of unmet demand after receiving its maximum feasible quantity; that remaining need should stay visible.

Why would A accept? It needs a concrete additional benefit. One proposed local assumption is that A can unload up to 3,000 lb in a preferred early slot, while 4,500 lb requires a later slot. Both slots are before its hard deadline. Its manager values the early slot because it fits an existing volunteer shift.

An illustrative local preference gives A one point per 100 lb plus 20 points for the early slot. The later 4,500 lb plan scores 45; the early 3,000 lb plan scores 50. This is a discussion device, not a justified real-world utility function. A must approve the preference, and route feasibility must establish that the early slot is actually available. If the early-slot benefit is less than 15 points, A has no reason to make this exchange under that model. Show that sensitivity rather than forcing A to agree.

Every participant must independently accept the revised quantity, schedule, and payment terms. The unused 3,000 lb is recorded as unrescued produce unless a separate destination actually accepts it. Do not automatically label it composted or create a third recipient to hide the loss.

## 8. Strengthen the comparison before claiming success

Keep first-come-first-served and nearest-feasible-recipient baselines, but make them obey the same capacity, funding, handling, deadlines, approvals, and discovery availability. Permit feasible partial loads. An invalid baseline makes negotiation look better without teaching anything.

Add a rules-based negotiator using the same messages and local constraints. This asks whether LLM strategy helps beyond the negotiation mechanism itself. A centralized optimizer with full information is an additional reference. It is an upper bound only for a precisely defined objective and the exact same constraints; it cannot be best on every competing metric simultaneously.

Report:

- Usable pounds distributed and unrescued pounds, with destinations where verified.
- Each site's unmet demand and fulfillment ratio, including the worst-served site.
- Total cost, fund draw, and whether all obligations have a payer.
- Negotiation duration, communication volume, inference cost, and recovery time after failure.
- Agreement failures, human approvals needed, and rejected infeasible proposals.
- How much operational information each method requires organizations to disclose.

Use the proposed advocate on/off × disruption on/off comparison with repeated seeded scenarios. Also repeat live LLM runs for a fixed scenario: a fixed seed and temperature zero do not establish identical LLM outputs. Label recorded replay as replay, distinguish it from live performance, and report measured variation. Present assumptions, results, and limits together.

Do not build a scenario where the advocate merely enforces a fairness constraint omitted from the baselines, then credit all improvement to collective intelligence. Test the effect of evidence and proposals separately from the effect of the shared policy.

## 9. Correct the remaining commitment assumptions

The latest transcript says to timestamp messages and process them in a fixed order. Timestamps alone do not make independent organizations observe the same order or prevent a double booking. The owner of each resource must control its availability and reject overlapping commitments.

Temporary holds can also cause a deadlock: two bundles each reserve one resource and wait for the other. Specify expiry, release after a failed preparation, and a consistent retry rule. The neutral infrastructure may record and relay this; it must not secretly pick allocations.

Versioned acceptance is good, but distinguish a willingness to accept from an actual reservation and from a final commitment. A later proposal cannot inherit an earlier acceptance just because the quantities look similar. Participants may explicitly authorize bounded amendments in advance; otherwise changed obligations need renewed consent.

Use the phrase conditional reservation and confirmation for the first design. Do not imply a production-grade atomic distributed transaction merely because there are two steps. If a confirmation is interrupted, the affected parties need a way to establish whether commitments became final before reusing resources. Timeout cannot erase a known completed delivery or silently undo a final commitment.

Partial execution must preserve dependency information. If A's delivery completes but B's fails, record A's delivery and its incurred costs. Reevaluate whether the fund's conditions and the remaining financial obligations still hold. Do not rewind the entire agreement to an earlier state.

Separate autonomy, privacy, and process layout. Separate processes are useful evidence of boundaries, but they do not establish autonomy if a common backend decides everyone's position. Sharing only offers also does not prove privacy: quoted limits can reveal budgets and capacity. Describe the actual information disclosed without claiming a privacy guarantee.

## 10. What the judges should see

Show one agreement card with quantities, stops, delivery windows, expenses, payer commitments, resource holds, approvals, and remaining produce. Beside it, show concise evidence and decision explanations tied to each change.

The demonstration sequence should make these points observable:

1. Independent organizations initially want incompatible terms.
2. Each uses its internal specialists or tools to establish a feasible local position.
3. A truck failure makes a previously proposed bundle invalid.
4. Capability discovery finds a replacement; its actual quote and capacity change the negotiation.
5. A participant proposes a multi-term exchange, and each affected organization evaluates it independently.
6. The revised agreement either receives all approvals or visibly remains uncommitted.
7. The quantities, money, community outcomes, and baseline comparison are accounted for.

Add one short case where no agreement exists: the replacement quote exceeds the available funding, or A cannot make a voluntary concession. The system identifies the binding reason and asks the appropriate human for an authorized change. That failure demonstrates that autonomy is meaningful.

Keep the architecture explanation aligned with the supplied challenge: Level 1 is useful internal collaboration, Level 2 is discovery and adaptation, and Level 3 is negotiation across competing independent organizations with baseline evidence. A dense roster of specialist names does not establish any of these by itself.

## 11. Decisions for the next Claude review

Please respond to these before proposing implementation:

1. Is the rescue nonprofit's operations coordinator the right first user? What evidence would change that choice?
2. Should the first event begin in the field or with an already packed and cooled lot? The field version preserves the original harvest-cost problem; the packed version has a smaller operational scope.
3. Should funding be a bounded participant or a preauthorized budget, and what conditions can it attach without becoming the allocator?
4. Is an advisory community advocate sufficient for the initial demo, with a formal fairness charter evaluated separately?
5. Does the worked example represent a defensible exchange? Challenge the early-slot preference, fixed farm quote, route timing, demand denominators, and cost scale rather than accepting the convenient numbers.
6. What is the smallest example that proves negotiation helps over both matching and a rules-based negotiator? What result would show that LLM negotiation adds no value?

Proposed next artifact: a jointly reviewed one-page scenario containing every resource, cost, time window, preference, and required approval, plus the competing candidate agreements. After that, settle the evaluation plan. No code is needed for either step.

## 12. Evidence and limits

Sources checked for this review:

- [Farmlink's current website](https://www.farmlinkproject.org/): confirms its farmer, transporter, and recipient mission; does not establish that all current work is manual.
- [Farm to Family](https://www.cafoodbanks.org/what-we-do/farm-family/): confirms an existing produce recovery program and picking/packing support.
- [UC Davis strawberry produce facts](https://postharvest.ucdavis.edu/produce-facts-sheets/strawberry): supports crop-specific cooling and quality context; does not validate the simulated lot or routes.
- [California Strawberry Commission growing regions](https://www.californiastrawberries.com/where-strawberries-are-grown/): supports the proposed coastal setting.
- [Feeding America report page](https://www.feedingamerica.org/research/map-the-meal-gap/overall-executive-summary): identifies the 2026 release as using 2024 data, supporting the distinction between annual need estimates and operational requests.

The detailed novelty claims, current competitor capabilities, local software compatibility, actual partner budgets, farm operating costs, and route feasibility have not been established. No operator was contacted, no implementation was created, and no experiment was run as part of this review. Claude's Rounds 2–3 were subsequently read and answered in Round 4 of `COLLAB_claude_codex.md`; the newer current-design documents supersede the narrower recommendations and flat-cost example here. All candidate outcomes remain proposals rather than experimental results.
