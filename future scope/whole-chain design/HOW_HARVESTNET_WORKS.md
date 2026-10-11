# How HarvestNet works: the whole flow in simple words

Written by Claude on October 10, 2026, as a plain-language guide. It explains Codex's [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md) and the frozen v1 design. It adds nothing new and changes nothing. If this guide and the design documents ever disagree, the design documents win: [CURRENT_DESIGN.md](CURRENT_DESIGN.md), [PROJECT_BRIEF.md](PROJECT_BRIEF.md), [CONTEXT.md](../CONTEXT.md), and [the ADRs](adr/).

Words in **bold** are defined in [CONTEXT.md](../CONTEXT.md).

---

## 1. The problem

Every day, good food is wasted even though people nearby need it. Often the reason isn't a shortage of food. It's that **several separate organizations all have to say yes at once**:

- The **farm** won't pay to pick food unless someone covers the cost.
- The **food bank** only has so much cold space and so many volunteers.
- The **truck** has to be the right kind (some foods need cold, and some are *damaged* by cold), and it has to be free at the right time.
- **Someone has to pay**, and money is limited.

Today, people arrange this by phone and email. When one piece changes (a truck breaks down, say), the whole plan can fall apart.

## 2. The challenge we're entering

Cisco's challenge, "When AI Agents Disagree," asks for AI agents that work together, adapt when things change, and reach decisions even when they disagree. HarvestNet targets **Level 3**: at least three independent agents with competing goals negotiate with **no central decision-maker**. Level 1 (teams inside each organization) and Level 2 (finding a replacement when something fails) show up as parts of it.

## 3. The big idea

> **Every organization keeps its own keys. The food still moves.**

Each real-world **organization** (farm, food bank, trucker, fund, and so on) gets its own AI representative, called a **negotiator**. It's backed by a small team of **specialists**. The negotiators talk to each other and work out a deal. **Nobody sits above them giving orders.** Not the software, not the **coordinator**, and not any sponsor tool. Each organization decides only for itself, and its own people approve its commitments ([ADR 0001](adr/0001-no-supervisor-between-organizations.md)).

## 4. Who takes part

| Group | Who | What they care about |
|---|---|---|
| **Food sources** | Farm, distributor, grocery store, restaurant | Getting surplus used instead of wasted, without losing money |
| **Recipients** | Food banks, pantries, shelters | Food their community can actually use, within their space and budget |
| **Movers and holders** | Truckers, cross-dock (a temporary cold warehouse) | Trips and storage they can really do, and get paid for |
| **Processor** | For example a jam maker | Food that meets its needs, at a fair price |
| **Rescue fund** | A grant program | Spending limited money well: urgent transfers first, then the least-served communities |
| **Advocate** | Speaks for underserved communities | Raising **coverage** for those who've received the least. It can propose changes but has **no veto** |
| **Coordinator** (a person) | The first user, for example at a food-rescue nonprofit | Seeing what needs attention. They **decide nothing** for anyone |

The architecture isn't tied to strawberries. Every food has a **food profile**: how cold it must be, whether cold damages it, how long it lasts, what it can share a truck with, and where each quality grade can go. Change the food, and the agents' decisions change, because they read the profile, not crop names ([ADR 0003](adr/0003-food-behavior-lives-in-food-profiles.md)).

## 5. Inside one organization

*This matches Codex's diagram 2. Diagrams 3–5 show the specialists for each organization type.*

Every organization runs the same internal process. Codex's diagrams use four letters to label each piece:

- **D, deterministic:** calculators. They give the same answer every time, with no guessing.
- **L, LLM:** the AI. It reads messy language, suggests deal changes, and explains reasons.
- **W, workflow:** ordinary software that moves information, stores records, or checks formats.
- **H, human:** a real person who approves.

When a message arrives, for example "here's a new version of the deal":

1. **Front-door checks (W).** Is this message really from who it claims? Is it the latest version of the deal? Have we seen it before?
2. **Specialists check the facts (D).** Each one checks one thing using the organization's *own* data and the food profile. For example: "We have 1,200 lb of cold space free on Thursday." "Picking costs $0.40 per pound." "This truck can carry 7,000 lb."
3. **The negotiator thinks (L).** Using only those checked facts, it suggests what to do: accept, reject with a reason, or propose a change. It explains why in plain English.
4. **The validator double-checks (D).** Every number in the negotiator's suggestion is recalculated. **The AI can't invent a quantity, a price, or a capacity** ([ADR 0002](adr/0002-ai-cannot-invent-numbers.md)). If something's wrong, the suggestion goes back to be fixed or turned into a refusal.
5. **A hold on its own resources (W).** If the deal would use the organization's truck time, cold space, or money, the organization itself places a temporary **hold** that expires. Nobody else can reserve your truck for you.
6. **Its own human approves (H).** Through the organization's own approval workflow (n8n), a real person approves or denies the *exact* terms.
7. **Re-check, then send.** Before sending, it confirms the deal hasn't changed in the meantime. Then the decision goes out with its reason.

Each organization has its own private notebook (budget, preferences, records). Other organizations only see what it chooses to share.

## 6. How organizations talk to each other

*This matches Codex's diagram 1.*

- **Cisco AGNTCY is the network.** Messages travel between organizations through it, in a shared **negotiation room** for each **event**.
- **AGNTCY Directory works like a phone book of abilities.** Organizations search it for, say, "a refrigerated truck near Watsonville that can carry 7,000 lb."
- **Message ordering** makes sure everyone sees messages in the same order. It **can't choose a winner**.
- **Shared records** keep each numbered version of the **draft agreement**, who said what, and the outcome. The coordinator's screen and the evaluation tools read from these records.

**How a deal becomes final:** every organization named in the deal must approve **the same version**, and every hold must still be valid. That makes it a **commitment**. If they never all agree, the result is a **preserved disagreement**: the coordinator sees the options and each organization's reasons, and nobody picks for them. **Nothing is ever committed automatically**, not even at a deadline.

## 7. Where the sponsors fit

Each sponsor plays a role a real organization already has. None of them makes decisions ([ADR 0004](adr/0004-sponsors-are-organization-systems-not-deciders.md)).

| Sponsor | Its real-world role | Example |
|---|---|---|
| **Cisco AGNTCY** | The phone network and phone book between organizations | Negotiation messages, finding a replacement truck |
| **Beeceptor** | Each organization's own computer systems (mocked for the demo) | The trucker's temperature sensors, the food bank's inventory system |
| **ElevenLabs** | A voice line for people in the field | A farmer phones in surplus, possibly in Spanish; the crew hears a shift notice |
| **n8n** | Each organization's back office for approvals | A food bank manager approves the exact terms |

NVIDIA Brev isn't used. The core system still works if a sponsor service is down, using recorded data, typed text, and a local approve button. A fallback isn't the same as using the sponsor, though, so the demo should say clearly which one it's using.

## 8. The whole story, step by step

*This matches Codex's workflows A, B, and C (diagrams 6–8).* The numbers below are examples. ADR 0005 says the real split, grant amounts, and ending **come from each run**, not from a script.

### Step 1: a farmer reports surplus (Workflow A)

1. A farmer on the Central Coast calls in: "About four pallets of strawberries, some soft, need them gone by Thursday."
2. ElevenLabs turns the speech into text.
3. The AI drafts the facts with units, and **marks anything missing as missing** instead of guessing.
4. The farm's specialists check the draft.
5. ElevenLabs reads it back: "I heard 10,000 lb, about 1,000 lb soft, pickup by Thursday. Correct?"
6. The farmer confirms or corrects. **Confirming the facts isn't agreeing to a deal.** That approval comes later.
7. The farm's specialists then assess the lot. The market specialist checks the real USDA price, the cost specialist checks harvest costs, and the harvest specialist checks crew and cooling capacity. The farm publishes a checked **surplus offer**.

### Step 2: organizations assess it and start negotiating

1. Food banks, truckers, the fund, and the advocate each look at the offer **using their own specialists and their own private data**.
2. They want different things. Two food banks both want the strawberries. The fund has limited money. The advocate pushes for the food bank whose community has received the least.
3. Organizations take turns proposing changes to the draft agreement, each with a reason. For example: "We'll take 3,000 lb if it arrives early, because it fits our volunteer shift." Everyone affected re-checks each new version.

### Step 3: something goes wrong (Workflow B)

1. The trucker's temperature feed (a labeled Beeceptor test reading) shows the cargo area is too warm for the strawberry food profile.
2. The trucker's specialist checks it. **If the evidence is unclear, a human inspects it** before anything else happens.
3. If the truck really can't do the job, the trucker reports a **disruption**. Every deal and hold that depended on that truck is flagged.
4. Completed work is kept. Nothing is pretended away.
5. The affected organization searches the Directory for replacements, then asks each candidate for its own current availability and price.
6. It writes a **reason card for every candidate**, including the rejected ones. For example: "Truck C: refrigerated, but booked until Friday."
7. A new version of the deal is proposed with the replacement truck. **Everyone affected re-checks it, places fresh holds, and their humans approve again** through their own n8n workflows. Old approvals don't carry over to a changed deal.
8. **If everything lines up:** it's a commitment. The crew may get a voice shift notice, and receipts follow only after the food is actually delivered.
9. **If not:** they amend again, or stop and record a preserved disagreement.

### Step 4: one deal affects another (Workflow C)

1. Other events are happening the same day: rejected lettuce at a distributor, near-date dairy at a grocery store, restaurant meals for a shelter. They all compete for the **same trucks and the same rescue fund**.
2. The fund decides each request by its published rule (urgent first, then least-served). It places an expiring hold on the money for its offer, and can offer a partial grant. It never spends the same dollar twice.
3. If a larger strawberry grant means less money for dairy, the coordinator sees that trade-off and each organization's response. **The coordinator can't move the money.** The organizations involved decide. The dairy might get funded, or it might end as a preserved disagreement, depending on what happens in the run.

### Step 5: the results are measured

The same situation is run through simpler methods. The headline compares against **first-come-first-served** on **worst-served coverage**, meaning how well the least-served recipient did. Supporting comparisons: a central optimizer that sees everyone's private data, and fixed-rule negotiators vs. AI negotiators. **We report whatever the numbers show**, including results where negotiation doesn't help.

## 9. What keeps it trustworthy

*Codex's diagram 9 and [CURRENT_DESIGN.md](CURRENT_DESIGN.md) have the details.*

- **The harness:** the controlled environment the agents run in. It gives them only their authorized tools, records every event, and recovers from failures.
- **Guardrails:** rules that can't be argued away. No organization acts for another. Every number has a source. Money and space can't be double-booked. Approvals must match the current version. Every pound of food is counted once.
- **Three ways to run:**
  - **live:** today's real data
  - **replay:** recorded data, run again exactly
  - **synthetic:** labeled made-up test conditions

  All three use the **same decision path**, and the screen shows which mode is running.
- **Safety:** messages from other organizations and voice transcripts are treated as information, never as instructions the AI must obey. Every food-safety doubt goes to a human.

## 10. Frozen vs. still open

**Frozen (v1, [ADR 0005](adr/0005-freeze-framework-evaluate-variable-decisions.md)):** who has authority, how data and food profiles work, what the harness does, the guardrails, and what evidence evaluations need.

**Allowed to change per run:** each organization's policies and preferences, food profiles, live data values, quantities, budgets, and the outcome itself.

**Still to decide** (from Codex's [ARCHITECTURE_PLAN.md](ARCHITECTURE_PLAN.md)):
1. Which AI model or provider the system will use.
2. The API budget for development, rehearsals, and evaluations.
3. Where it runs: one laptop, several laptops, or the cloud, and whether Docker is available.

Also proposed but not agreed: my [AGENT_BEHAVIOR.md](AGENT_BEHAVIOR.md) (how each negotiator scores options and handles deadline pressure). Codex treats it as example policy, not a rule.

## 11. How to read Codex's diagrams

| Codex diagram | What it shows | Section here |
|---|---|---|
| 1. Full network | All organizations, the AGNTCY room, shared records, the coordinator | 4, 6 |
| 2. Inside every organization | The front-door → specialists → negotiator → validator → hold → approval loop | 5 |
| 3–5. Specialists by organization type | Which calculators each organization has | 4, 5 |
| 6. Workflow A | Voice intake to a checked offer | 8, step 1 |
| 7. Workflow B | Disruption, replacement search, re-approval | 8, step 3 |
| 8. Workflow C | Shared funding and preserved disagreement | 8, step 4 |
| 9. Records and evaluations | What's private, what's shared, how runs are compared | 8 step 5, 9 |
| 10. Interfaces | The records passed between pieces, and sponsor status | 6, 7 |
