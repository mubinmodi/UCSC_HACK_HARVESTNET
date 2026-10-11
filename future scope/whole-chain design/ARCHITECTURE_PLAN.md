# HarvestNet architecture and project plan

**Status: Phase 1 complete; detailed logical architecture drafted; concrete deployment and build plan remain open.** October 10, 2026. The user's subsequent request for a full diagram explicitly advances the logical architecture beyond the original question checkpoint. See [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md) for every organization, internal specialist, sponsor boundary, and workflow. Model access, API budget, and runtime remain open configuration choices. This is Markdown design work, not implementation authorization.

## Summary

HarvestNet lets independent organizations assess a surplus lot, negotiate a draft agreement, place their own holds, and approve the same version to create a commitment—or preserve their disagreement. Specialists use calculators, food profiles, and sourced observations; negotiators propose and explain. The coordinator sees pending approvals, changes, reasons, and outcomes without deciding for organizations. A shared harness enforces authority, evidence, resource conservation, and replay. Evaluations compare coverage and useful outcomes across foods, policies, and disruptions, with first-come-first-served as the headline baseline. Sources: [CONTEXT](../CONTEXT.md), [current framework](CURRENT_DESIGN.md), and [evaluation catalog](HARVESTNET_SCENARIOS.md).

## Decision inventory

“User-confirmed, recorded” identifies decisions recorded in the shared review; “agent-agreed” does not imply separate user approval of every mechanism.

| Decision | Source | Status |
|---|---|---|
| Organizations own decisions and approvals; no supervisor between them; coordinator observes | [ADR 0001](adr/0001-no-supervisor-between-organizations.md) | User-confirmed, recorded |
| Calculators and data supply operational numbers; validate outgoing offers | [ADR 0002](adr/0002-ai-cannot-invent-numbers.md) | User-confirmed, recorded |
| Common procedures use food profiles and actual lot evidence; identify unsupported assessments | [ADR 0003](adr/0003-food-behavior-lives-in-food-profiles.md) | User-confirmed generality; agent-agreed evidence clarification |
| AGNTCY, Beeceptor, ElevenLabs, n8n have organization-serving roles; Brev excluded | [ADR 0004](adr/0004-sponsors-are-organization-systems-not-deciders.md) | User-confirmed, recorded; integrations unverified |
| General framework, live evidence, guardrails, harness, and evals; variable policies and outcomes | [ADR 0005](adr/0005-freeze-framework-evaluate-variable-decisions.md) | User-confirmed direction; agent-agreed framework baseline |
| Level 3; coordinator first; Central Coast California; four demonstration events and a broader network map | [Shared review: grilling decisions and Round 11](../COLLAB_claude_codex.md), [brief](PROJECT_BRIEF.md) | User-confirmed, recorded |
| Urgent eligible transfers first, then least-served communities; cost and volume separate | [Shared review: Round 9 and current decision index](../COLLAB_claude_codex.md) | User-confirmed |
| AMS market observations, OSM/OSRM routes, Atlas area context; labeled synthetic operational inputs | [Framework: data contracts](CURRENT_DESIGN.md#data-and-api-contracts) | User-confirmed source direction; agent-agreed contracts |
| AGNTCY app-sdk, A2A, SLIM, Directory; LangGraph only inside organizations | [Architecture prompt](prompts/architecture_plan_prompt.md), [shared review](../COLLAB_claude_codex.md) | Reported framework preference; concrete versions/setup open |
| Observe/OpenTelemetry for tracing | [Architecture prompt](prompts/architecture_plan_prompt.md) | Proposed integration; compatibility unverified |
| Versioned drafts, owner-issued holds, current approvals, reconciliation, bounded stopping | [Framework: harness and guardrails](CURRENT_DESIGN.md#execution-harness) | Agent-agreed requirements implementing confirmed authority |
| Round 10 urgency bands, earmarks, coverage aggregation, and decision timing | [Shared review: Round 11](../COLLAB_claude_codex.md), [fund-policy checks](HARVESTNET_SCENARIOS.md#round-10-fund-policy-checks) | Proposed policy, accepted for evaluation with amendments |
| Shared scoring, walk-away rules, time concessions, and numeric approval thresholds | [Claude's behavior draft](AGENT_BEHAVIOR.md) | Proposed; not agreed framework requirements |
| Worst-served coverage versus first-come-first-served; rules-based comparison and privileged central reference | [Brief](PROJECT_BRIEF.md), [evaluation catalog](HARVESTNET_SCENARIOS.md) | User-confirmed direction; agent-agreed comparison contract |
| Nearest feasible recipient as an additional comparator | [Architecture prompt](prompts/architecture_plan_prompt.md) | Proposed addition; does not replace the headline baseline |
| LLM API/model access, spending cap, deployment location | [Architecture prompt: unknown resources](prompts/architecture_plan_prompt.md) | Open; user input needed |

## Conflicts and source precedence

The latest direct user instruction takes precedence. ADR 0005 and Round 11 record that instruction; older passages in the prompt and collaboration history do not reopen the fixed numerical scenario. The framework documents are current. Historical transcripts and the archived numerical fixture remain examples. Sources: [ADR 0005](adr/0005-freeze-framework-evaluate-variable-decisions.md), [Round 11](../COLLAB_claude_codex.md).

| Conflict or ambiguity | Resolution for architecture |
|---|---|
| Prompt reads ADRs 0001–0004 and assumes design docs may lag | Include ADR 0005 and Round 11; use the three updated framework documents |
| Prompt flow (c) requires the $2,800 pool to end in disagreement | Design a general scarcity flow with agreement or preserved disagreement; retain $2,800 only as a labeled test input |
| Prompt treats acceptance of fund rule v1 as unanswered | Round 11 answered it: a candidate policy with conditional recipient acceptance, correct lead-time accounting, and release/reconsideration of refused partial awards |
| Behavior draft makes fixed farm limits and fund rule v1 universal | Treat them as example organization policies/resources; ADR 0005 wins |
| Behavior draft stops after the same terms return three times | Current demonstration policy is three complete rounds without new terms; the framework requires a declared stopping policy, not a universal count |
| Behavior draft assumes a 2,000 lb approval threshold and time-based concessions | These are unapproved policy examples. Every commitment still needs the required current approvals; a deadline grants no consent |
| Behavior draft says a limited rules menu versus creative LLM amendments is inherently fair | Evaluate shared feasible actions, evidence, validators, and budgets; report differences in search capability separately. This is a review finding, not a measured result |
| Required sponsor use versus an offline core | Offline evaluation remains available; each sponsor claim requires evidence of actual integration |

Sources for the table: [architecture prompt](prompts/architecture_plan_prompt.md), [behavior draft](AGENT_BEHAVIOR.md), [framework](CURRENT_DESIGN.md), [evaluation catalog](HARVESTNET_SCENARIOS.md), and [Round 11](../COLLAB_claude_codex.md). No frozen framework decision needs reopening for these resolutions.

## Architecture inputs still needed

Only three resource answers are missing from the [requested workflow](prompts/architecture_plan_prompt.md):

1. **LLM access:** which providers/models the application may call. Provider/model names are sufficient; no credentials are requested. “Just Sol” governs this design conversation and does not establish application API access.
2. **API budget:** the approximate total cap for development, rehearsals, and evaluations. This determines model allocation, usage guards, and evaluation breadth.
3. **Runtime:** one laptop, multiple laptops, or cloud; whether Docker is available. This determines service boundaries, persistence, networking, and webhook exposure.

These affect concrete deployment and model binding; the detailed logical diagrams can proceed under explicit placeholders. Exact policy weights, food quantities, and the fund pool do not block architecture: their ownership and versioned interfaces are already defined in [CURRENT_DESIGN](CURRENT_DESIGN.md). Preference weights belong to organizations; synthetic evaluations declare and vary them. The [coordinator questionnaire](COORDINATOR_QUESTIONNAIRE.md) remains unsent and is future product validation, not a missing architecture decision.

## External verification queue

Public documentation reviewed earlier is not proof of project access or compatibility. The following remain **unverified for the planned deployment**; Phase 1 lists them without guessing versions or purchasing services. Sources: [framework: sponsor status](CURRENT_DESIGN.md#sponsors-and-organization-systems), [architecture prompt](prompts/architecture_plan_prompt.md).

| Resource | Evidence to obtain before concrete integration choices |
|---|---|
| AGNTCY app-sdk, A2A, SLIM, Directory, Observe | Supported versions and compatibility; service setup, authentication, discovery registration, group communication, and trace propagation |
| LangGraph and selected LLM provider | Compatible runtime/tool interfaces, structured output support, rate limits, model access, and current pricing |
| Beeceptor | Actual project plan/credits, request limits, persistence behavior, endpoint isolation, and fault/replay support |
| ElevenLabs | Actual credits, transcription/read-back capabilities, Spanish support for selected models, and whether a phone channel is separately needed |
| n8n | Hosting/plan entitlement, authenticated approval callbacks, retries, and reachability from the selected runtime |
| AMS, OSM/OSRM, Atlas | Access/authentication, usage conditions and limits, coverage, freshness, comparable price units, routing profile, and replay/caching permissions |
| Food-profile references | Applicability and review of actual profile fields; published guidance does not establish the condition of a live lot |

## Continuation after the answers

The [diagram atlas](ARCHITECTURE_DIAGRAMS.md) now covers components, the organization roster, three flows, state ownership, logical records, and evaluation/observability. After resource answers, complete concrete deployment/model choices, adapter contracts, dependency-ordered work, risks, and the first tasks. Link to existing guardrails and metrics instead of duplicating them. Assess the behavior proposal as configurable policy rather than silently adopting it. Keep evaluations available from the first deterministic slice, as required by the [framework baseline](CURRENT_DESIGN.md#evaluation-contract).

The [prompt](prompts/architecture_plan_prompt.md) requests a project plan, but application-code tasks must remain labeled **needs user go-ahead**. No `/to-spec`, `/to-tickets`, or issue creation is implied. If later requested, local tracking follows [issue-tracker.md](agents/issue-tracker.md) and [triage-labels.md](agents/triage-labels.md).
