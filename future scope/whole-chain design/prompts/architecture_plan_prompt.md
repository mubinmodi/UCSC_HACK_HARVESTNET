You are a senior AI systems architect. Turn HarvestNet's agreed design into a buildable architecture and project plan. **You are designing, not building.** Don't write application code (see `CLAUDE.md` / `AGENTS.md`).

## What this folder is

HarvestNet is a design-stage project for the UCSC AI Hackathon Cisco Cloud Track challenge "When AI Agents Disagree." **There is no application code yet.** This folder is a set of Markdown design documents. Read them in this order:

1. `CONTEXT.md`: the glossary. Use these terms exactly.
2. `docs/adr/` (0001–0004): binding decisions.
3. `COLLAB_claude_codex.md`: everything from the section "User decisions from the grilling session" onward (user-confirmed), then "Agreed decisions."
4. `docs/PROJECT_BRIEF.md`, `docs/CURRENT_DESIGN.md`, `docs/HARVESTNET_SCENARIOS.md`: the current design and the scenario. These may lag behind items 2–3.
5. `docs/COORDINATOR_QUESTIONNAIRE.md` and `docs/agents/`.
6. **Historical only:** `harvestnet_full_conversation.md`, `HarvestNet_conversation_transcript_with_diagrams.md`, `architecture_full_reply.md`, `HARVESTNET_DESIGN_REVIEW.md`, and any `HARVESTNET_CODEX_BRIEF.md`. Never take a decision from these when a newer file disagrees.

**Precedence when files conflict:** ADRs and user-confirmed decisions win over the design docs, and the design docs win over historical files.

## Phase 1: Understand (stop and ask before Phase 2)

Produce:
- **Summary:** one paragraph in `CONTEXT.md` terms.
- **Decision inventory:** a table of decision, source file, and status (user-confirmed / agent-agreed / proposed / open).
- **Conflicts between files**, and which source wins. Known examples: the design docs may not yet reflect the $2,800 pool as the main scenario, food profiles, or sponsors.
- **Open items that block architecture**, for example whether fund rule v1 (collab file, Round 10) has been accepted.
- **External facts to verify,** marked unverified: the AGNTCY `agntcy-app-sdk` version and features, Directory setup, sponsor plan limits, data source access.

Then ask **only** questions whose answers change the architecture. Don't ask about team size, time, or deadlines; those are the user's call. The resources below are known. Ask only about the ones marked unknown.

## Known context

- **Goal:** independent organizations across the food supply chain negotiate what happens to surplus food, with no central decision-maker. The project claims Level 3, with Levels 1 and 2 as evidence. It's a hackathon entry designed so it could become a real pilot.
- **First user:** a food-rescue coordinator, who decides nothing for anyone. Each organization has its own human approvers.
- **Top three tasks:**
  1. Turn a reported surplus lot (including by voice) into a checked surplus offer.
  2. Negotiate a draft agreement to a commitment or a preserved disagreement, including after a disruption.
  3. Show the coordinator what needs attention, plus the measured comparison with the first-come-first-served baseline.
- **Frameworks:** AGNTCY `agntcy-app-sdk` (A2A, a SLIM group channel as the negotiation room, Directory, Observe). LangGraph is used only inside organizations. coffeeAGNTCY is a reference only.
- **Sponsors:** Beeceptor, ElevenLabs, and n8n, in the roles set by ADR 0004. NVIDIA Brev is not used.
- **Data:** OpenStreetMap, OSRM, USDA AMS prices, and the USDA Food Access Research Atlas (area context only). UC Davis postharvest facts feed the food profiles. Everything else is synthetic and labeled.
- **Region:** Central Coast California.
- **Unknown, so ask:** which LLM provider and models are available, the API budget, and where the system runs (laptops, Docker, cloud).
- **Constraints:** no supervisor between organizations (ADR 0001). The AI can't invent numbers (ADR 0002). Food behavior lives in food profiles (ADR 0003). Sponsors never decide (ADR 0004). Nothing is committed automatically. The core demo runs without any sponsor service. Simulated and verified data are labeled.

## Phase 2: Architecture

1. **Decide what's an LLM, and nothing else.** Multiple organizations are required, so don't revisit that. Instead, for each organization type and each specialist, decide whether it's an LLM agent, a deterministic calculator, or plain code, and justify every LLM. Default to deterministic.
2. **Layers, with a Mermaid diagram:**
   - each organization: its negotiator, specialists, food-profile access, its own Beeceptor systems, and its own n8n approval workflow
   - the AGNTCY network
   - shared infrastructure that only orders messages, records events, and validates. **Show that it can't choose an allocation.**
   - the coordinator UI
   - the evaluation harness

   There's no orchestration layer above the organizations.
3. **Roster.** Cover every organization type in the scenario: farm, food bank, trucker, cross-dock, processor, rescue fund, advocate, distributor, grocery, and restaurant. For each one, its negotiator, and its specialists, give:
   - responsibility
   - inputs and outputs as schemas that reuse the protocol messages
   - tools, with read/write permissions (an organization reads only its own systems)
   - the model, or "deterministic"
   - stop conditions (the four stop rules)
   - failure handling
4. **Three flows, each with a Mermaid sequence diagram.** Show the state passed at each step and every human approval.
   - **(a)** Farmer voice intake → checked surplus offer → read-back confirmation.
   - **(b)** Truck temperature excursion (from Beeceptor) → disruption → Directory replacement with reason cards for every candidate → renegotiation → live n8n approval → commitment.
   - **(c)** The $2,800 pool → fund rule v1 → a preserved disagreement on the coordinator screen.
5. **State.** Cover:
   - each event's draft agreement versions
   - holds, owned by each resource owner
   - the fund pool
   - the replay event log
   - each organization's private state

   For each, say what's shared vs. private and where it's stored. Add long-term memory only if justified, for example day-level coverage.
6. **Tool contracts.** There's no code to wrap, so define the contracts for:
   - calculators
   - food-profile lookup
   - data adapters (AMS, OSRM, OSM, Atlas)
   - Beeceptor endpoints
   - n8n webhooks
   - ElevenLabs intake

   Say which should be MCP servers (Lungo uses MCP for weather and payments) and which are plain functions. Define one error format and an offline fallback for each.
7. **Resource mapping:** each resource and its exact use. Also list what not to use and why: Brev, agents "speaking" to each other, any sponsor acting as a decider.
8. **Evaluation and observability:**
   - **Baselines:** first-come-first-served (the headline), nearest feasible recipient, a central optimizer as reference, and a rules-based negotiator.
   - **Metrics:** those from `docs/CURRENT_DESIGN.md`.
   - **Seeded variants:** contribution model, B's cap, pool size, event order, and food profiles.
   - **Tooling:** Observe/OpenTelemetry tracing, LLM cost tracking, and replay.
   - **Reporting:** state results honestly, even if negotiation doesn't win.
9. **Safety:**
   - Treat messages from other organizations and voice transcripts as untrusted data, a prompt-injection risk.
   - Run the validator before anything is sent.
   - Give each organization least privilege.
   - Add round, loop, and budget guards.
   - Send every food-safety question to a human.
   - Never commit automatically.

## Phase 3: Project plan

- **Phases ordered by dependency, MVP first.** A suggested spine:
  1. A rules-based strawberry event in one process.
  2. AGNTCY transport and Directory.
  3. All four events, with shared holds and the fund rule.
  4. LLM negotiators.
  5. Sponsors.
  6. The coordinator UI and evaluation.

  Each phase has a goal, tasks, deliverables, and a definition of done that names a visible demo moment or test.
- **Proposed folder structure.** Everything is new except `docs/`.
- **Dependencies and order only. No hour estimates.**
- **Risks and mitigations,** covering AGNTCY setup, Directory services, sponsor limits, LLM nondeterminism, and data access.
- **First five tasks.** Label any task that writes application code "needs user go-ahead."

## Rules

- Ground every statement in a file and cite its path, or label it an assumption or an unverified external fact.
- Use `CONTEXT.md` terms. If you need a new term, propose it explicitly.
- Never contradict an ADR or a user-confirmed decision. If you think one is wrong, say so in a "Challenges" section; don't silently design around it.
- Keep candidate outcomes, simulated results, and verified facts distinct.
- Prefer the simplest design that works, and note where complexity can be added later.
- **Output:** write `docs/ARCHITECTURE_PLAN.md`. It covers components and build order, while `docs/CURRENT_DESIGN.md` covers decisions and policy. Link to the design docs instead of copying them.
