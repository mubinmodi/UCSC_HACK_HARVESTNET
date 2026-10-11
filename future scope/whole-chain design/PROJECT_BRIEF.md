# HarvestNet — project brief

**v1 framework baseline, frozen October 10, 2026.** This brief describes the product and the evidence needed to establish it. The freeze covers framework contracts; policies, inputs, and outcomes remain variable. Integrations and evaluations are proposed, not completed. See [CURRENT_DESIGN.md](CURRENT_DESIGN.md) for the framework and [HARVESTNET_SCENARIOS.md](HARVESTNET_SCENARIOS.md) for the evaluation catalog.

**Every organization keeps its own keys. The food still moves.**

## The idea

A surplus offer becomes useful only when several independent organizations can agree on quantity, timing, handling, transport, and payment. Their needs differ, and changing availability or market conditions can invalidate an otherwise workable plan.

HarvestNet gives each organization a negotiator supported by specialists and calculators. Live data informs its assessment. Negotiators propose and revise agreements; guardrails check the terms, resource owners place holds, and the responsible organizations approve their own commitments. The system records what happened and can explain a refusal as well as an agreement.

The first user is the **coordinator**, who sees what needs attention, what changed, whose approval is pending, and where each surplus lot stands. The coordinator cannot decide for another organization. The confirmed priority is urgent eligible transfers first, then least-served communities, with cost and food volume visible.

## Scope

HarvestNet targets Level 3 of the challenge, with specialist collaboration and replacement discovery as supporting capabilities. It is a hackathon entry designed to support a future nonprofit pilot in Central Coast California.

The network spans farms, packers, distributors, grocery stores, restaurants, recipients, transport, storage, processors, rescue funds, and eligible downstream pathways. Four planned live events show that breadth: farm produce, distributor produce, dairy, and prepared meals. The network map distinguishes demonstrated stages from profile-ready or proposed ones.

The architecture works from **food profiles**, not crop names embedded in negotiation rules. Profiles describe handling, compatibility, preparation, packaging, and required assessments. Strawberries are an example, not the product boundary. Unsupported foods or incomplete evidence must be identified rather than treated as validated.

## What makes it dependable

The **harness** is the controlled environment that runs the negotiators: authorized tools, current evidence, calculations, draft versions, resource holds, approvals, event records, and recovery after failures.

Guardrails enforce organization authority, source-backed numbers, feasible funding and resource use, current approvals, and honest source-lot accounting. Live APIs can change a proposed plan; they cannot waive a constraint or provide somebody's consent.

Evaluations test those guardrails, replay identical evidence for competing methods, inject failures, and vary food profiles and policies. The headline comparison is worst-served coverage against first-come-first-served. The full-information central reference and rules-based-versus-LLM comparison provide supporting evidence. Present whatever the results show.

## Intended demonstration flow

| Moment | What the audience sees | Evidence to establish |
|---|---|---|
| A person reports surplus | ElevenLabs voice intake, confirmed read-back, and a draft offer; text fallback is explicit | Numbers and consequential details remain attributable to the person and validation |
| Organizations assess it | Specialists compare source-backed market data, local cost/capacity, food profiles, and recipient requests | Calculations and differing objectives, without a predetermined below-cost price |
| Organizations negotiate | AGNTCY carries attributed amendments and reasons; the current agreement is visible | Independent decisions and valid proposals, rather than a fixed winning split |
| New evidence arrives | Organization data or a labeled Beeceptor fault invalidates affected assumptions; Directory discovery explains every candidate | Evidence-driven reassessment, valid holds, and reasons for selection or rejection |
| People approve their obligations | One or two approvals are shown through organization-specific n8n workflows; remaining demo approvals are labeled simulated | Approval of exact terms by the right organization; no coordinator override |
| The agreement proceeds or stalls | Authorized crew notice, receipts and custody records, or preserved disagreement with reasons | Commitments and actual outcomes remain distinct |
| Shared resources reveal a trade-off | The coordinator sees the effects on other events and the organizations' responses | The cross-event dilemma follows the run's evidence; dairy refusal is one possible recorded case, not a required live ending |
| Results are compared | Coverage, food received/distributed, costs, pathways, refusals and baseline results | Reproducible comparisons, including cases where negotiation offers no improvement |

Cisco AGNTCY, Beeceptor, ElevenLabs, and n8n have defined roles around organizations; none decides the allocation. NVIDIA Brev is excluded. Sponsor capabilities, account entitlements, and actual integration evidence are tracked separately.

## What v1 freezes

Freeze the product boundaries, organization authority, data/profile contracts, harness responsibilities, guardrails, and evaluation requirements. Policies, API snapshots, lot quantities, budgets, route estimates, allocation candidates, and outcomes remain variable.

A live run uses current observations. A replay uses captured observations with their timestamps. A synthetic test injects labeled conditions. All three use the same decision and validation path, and the interface identifies which mode is running.

The coordinator questionnaire remains a draft for later validation, not evidence that an operator has been interviewed. No application code, implementation specification, tickets, external messages, integrations, or benchmark results have been produced by this review.
