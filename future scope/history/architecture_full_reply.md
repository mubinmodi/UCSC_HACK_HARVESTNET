# HarvestNet Architecture: Multi-Agent Systems Negotiating With Other Multi-Agent Systems

I would design HarvestNet as a **network of independent multi-agent organizations**, rather than one large multi-agent system controlling everything.

This gives us two distinct levels of intelligence:

1. **Internal intelligence:** Specialized agents collaborate within each stakeholder's organization to understand its situation, evaluate options, and determine what it can offer.
2. **Collective intelligence:** Organizations negotiate with one another, exchange evidence, make concessions, and reach agreements without a central decision-maker.

This architecture is particularly relevant to Cisco's challenge because it combines all three levels naturally.

## 1. Overall architecture

Imagine five organizations:

- A farm with surplus produce.
- Food Bank A, serving a large urban population.
- Food Bank B, serving an underserved rural community.
- A transportation company.
- A community advocacy organization representing regional food-access needs.

Each organization runs its own multi-agent system (MAS).

```text
                     HARVESTNET NETWORK

   FARM ORGANIZATION                  FOOD BANK A
   ┌─────────────────────┐           ┌─────────────────────┐
   │ Surplus Agent       │           │ Demand Agent        │
   │ Market Price Agent  │           │ Storage Agent       │
   │ Cost Agent          │           │ Nutrition Agent     │
   │                     │           │                     │
   │ Farm Negotiator     │           │ Food Bank Negotiator│
   └──────────┬──────────┘           └──────────┬──────────┘
              │                                 │
              │                                 │
   ┌──────────┴─────────────────────────────────┴──────────┐
   │                                                       │
   │             DECENTRALIZED COMMUNICATION               │
   │                 AND NEGOTIATION                       │
   │                                                       │
   │         AGNTCY / A2A / SLIM Messaging                 │
   │                                                       │
   │      Offers • Counteroffers • Evidence • Votes        │
   │                                                       │
   └─────────┬────────────────────┬─────────────┬──────────┘
             │                    │             │
             │                    │             │
   ┌─────────┴─────────┐ ┌────────┴────────┐ ┌──┴────────────────┐
   │ FOOD BANK B       │ │ LOGISTICS MAS   │ │ COMMUNITY MAS     │
   │                   │ │                 │ │                   │
   │ Demand Agent      │ │ Routing Agent   │ │ Food Access Agent │
   │ Storage Agent     │ │ Fleet Agent     │ │ Equity Agent      │
   │ Budget Agent      │ │ Pricing Agent   │ │ Impact Agent      │
   │                   │ │                 │ │                   │
   │ Negotiator        │ │ Negotiator      │ │ Advocate          │
   └───────────────────┘ └─────────────────┘ └───────────────────┘
```

**The critical distinction:** The communication layer routes messages. It does not determine who receives the food.

Each organization decides independently whether to accept a proposed agreement.

You can run five separate LangGraph instances, one for each organization, with an A2A-facing negotiation agent exposing that organization's capabilities.

This also creates a natural architecture for adding more farms, food banks, and transportation providers dynamically.

---

# 2. How each stakeholder's multi-agent system works

## A. Farm MAS — Producer Intelligence System

**Objective:** Recover surplus produce while minimizing financial losses and respecting harvesting deadlines.

The farm doesn't simply announce that it has tomatoes available. It needs to determine whether donating them is economically and operationally feasible.

### Internal agents

| Agent | Responsibility | Data/tools |
|---|---|---|
| Surplus Detection Agent | Estimate recoverable produce | Farm inventory, USDA NASS |
| Market Intelligence Agent | Evaluate alternative sales opportunities | USDA AMS |
| Recovery Cost Agent | Calculate harvesting, packing, and loading costs | Cost data |
| Harvest Scheduling Agent | Determine whether crews can recover produce before expiration | Crew availability, weather |
| Farm Negotiator | Develop offers, negotiate concessions, accept feasible proposals | Outputs from other agents |

### Internal workflow

```text
Farm receives surplus event
            │
            ▼
    Surplus Detection
            │
            ▼
    Market Intelligence
            │
            ▼
    Recovery Cost Agent
            │
            ▼
    Harvest Scheduling
            │
            ▼
      Farm Negotiator
            │
            ▼
 Publish available produce
```

Suppose the farm has:

- 10,000 pounds of surplus tomatoes.
- 36 hours to harvest them.
- $300 in harvesting costs.
- $150 in packing costs.
- An alternative opportunity worth $350.

The internal agents collectively conclude that donating requires at least $450 in cost recovery, assuming those costs cannot be avoided.

The Farm Negotiator publishes an offer:

> **Farm Agent:** We have 10,000 pounds of tomatoes available. Harvesting must begin within 36 hours. We require $450 in recovery costs. Transportation must be arranged by the receiving organizations.

Other organizations can now respond.

### What makes it genuinely multi-agent?

The specialized agents can disagree internally.

For example:

**Market Agent:** Selling the tomatoes to a processor may recover $350.

**Recovery Cost Agent:** Donating requires $450 in harvesting and packing expenditures.

**Harvest Agent:** The processing buyer cannot collect the tomatoes before the deadline.

The negotiator must weigh those findings before making an offer.

An important engineering choice: calculations should be performed by deterministic tools, while the LLM agents interpret the results and evaluate strategies.

---

## B. Food Bank MAS — Distribution Intelligence System

**Objective:** Maximize the amount of appropriate, usable food delivered to the communities it serves.

Each food bank operates its own MAS.

This is important because Food Bank A and Food Bank B are independent organizations with different demands, funding, and resources.

### Internal agents

| Agent | Responsibility | Data/tools |
|---|---|---|
| Demand Forecasting Agent | Estimate demand for different foods | Pantry requests, historical demand |
| Storage Agent | Evaluate cold-storage availability | Inventory database |
| Nutrition Agent | Assess whether produce meets nutritional priorities | USDA FoodData Central |
| Budget Agent | Determine affordable transportation and handling costs | Budget data |
| Distribution Planning Agent | Estimate how quickly accepted food can reach recipients | Distribution schedules |
| Food Bank Negotiator | Determine acceptable quantities, costs, and delivery conditions | Internal agent recommendations |

### Internal workflow

```text
     Receive farm offer
              │
              ▼
       Demand Agent
              │
      ┌───────┴────────┐
      ▼                ▼
 Storage Agent    Nutrition Agent
      │                │
      └───────┬────────┘
              ▼
         Budget Agent
              │
              ▼
     Distribution Agent
              │
              ▼
     Food Bank Negotiator
              │
              ▼
       Submit proposal
```

Imagine Food Bank A receives an offer for 10,000 pounds of tomatoes.

Its internal agents return:

| Internal agent | Finding |
|---|---|
| Demand Agent | Could distribute 7,000 pounds |
| Storage Agent | Only 4,500 pounds of available capacity |
| Budget Agent | Can contribute $200 |
| Nutrition Agent | Tomatoes are appropriate for current distribution plans |
| Distribution Agent | Delivery must arrive before tomorrow evening |

Its negotiator now understands that requesting 7,000 pounds would exceed storage constraints.

Instead, it proposes:

> **Food Bank A:** We can accept 4,500 pounds and contribute $200 toward recovery or transport costs, provided delivery occurs before 6 PM tomorrow.

Food Bank B may make a competing offer based on entirely different internal constraints.

### An interesting Level 3 detail

Food banks shouldn't be artificially programmed to cooperate.

Food Bank A might prefer to receive as much food as possible, even if doing so reduces Food Bank B's allocation.

That creates authentic conflict.

But the negotiators can also discover mutually beneficial arrangements, such as sharing transportation costs or accepting deliveries on different days.

---

## C. Logistics MAS — Transportation Intelligence System

**Objective:** Deliver produce reliably while maintaining economically feasible operations.

Transportation is especially interesting because it connects multiple stakeholders.

### Internal agents

| Agent | Responsibility | Data/tools |
|---|---|---|
| Route Optimization Agent | Calculate available delivery routes | OSRM |
| Fleet Management Agent | Check vehicle availability and capacity | Fleet database |
| Cost Estimation Agent | Calculate transportation costs | Distance, labor, refrigeration |
| Risk Assessment Agent | Evaluate potential delivery disruptions | Weather, simulated incidents |
| Logistics Negotiator | Offer services and negotiate prices and delivery conditions | Internal recommendations |

### Example

The logistics MAS receives a request:

> Transport 10,000 pounds of tomatoes from Farm A to Food Banks A and B within 24 hours.

Its Fleet Agent reports:

- Truck 1: Capacity 7,000 pounds.
- Truck 2: Unavailable.
- Truck 3: Capacity 4,000 pounds, but not refrigerated.

The Risk Agent determines whether refrigeration is necessary for the specific load and delivery conditions. That requirement should come from validated food-handling rules or an authorized human decision, not an LLM guess.

The Route Agent calculates distances.

The Cost Agent calculates feasible prices.

The Logistics Negotiator responds:

> We can transport 7,000 pounds on one refrigerated truck. A second delivery requires another provider. Our proposed cost is $350.

This introduces a new conflict.

The farm has 10,000 pounds available, but the logistics provider can only handle 7,000.

A solution now requires negotiation rather than simple task delegation.

---

## D. Community Advocacy MAS — Equity Intelligence System

**Objective:** Represent the needs of food-insecure communities that otherwise have little or no direct negotiating power.

This would be one of HarvestNet's most distinctive components.

Instead of letting food banks negotiate exclusively according to their own operational priorities, the Community Advocacy MAS provides regional evidence about unmet need.

### Internal agents

| Agent | Responsibility | Data/tools |
|---|---|---|
| Food Access Agent | Identify communities with limited food access | USDA Food Access Atlas |
| Food Insecurity Agent | Analyze estimated food insecurity | Feeding America |
| Allocation Equity Agent | Evaluate how proposed allocations distribute benefits | Verified demand and allocation data |
| Social Impact Agent | Estimate the likely effects of alternative allocations | Scenario model |
| Community Advocate | Challenge allocations, propose alternatives, and negotiate equity conditions | Internal analyses |

### Example

Food Bank A requests 4,500 pounds.

Food Bank B requests 3,000 pounds.

The Community Advocacy MAS evaluates the proposed distribution and finds that Food Bank B serves a modeled population with substantially higher unmet need relative to its available supply.

The Equity Agent recommends increasing Food Bank B's allocation.

The Community Advocate sends:

> Food Bank B serves an area with higher estimated unmet need. Could Food Bank A accept 3,500 pounds instead of 4,500, allowing an additional 1,000 pounds to reach Food Bank B?

The advocate cannot simply override Food Bank A.

Instead, it presents evidence, proposes concessions, and attempts to persuade the other organizations.

This is what makes its participation a real negotiation mechanism.

**One nuance:** A statistical equity agent doesn't automatically represent what people in a community actually want. Its mandate, priorities, and data limitations should be visible, with community organizations or human representatives able to review them.

---

## E. Harvest Crew MAS — Labor and Recovery System

I would include this as a smaller, independently operated organization because labor availability creates another meaningful constraint.

| Agent | Responsibility |
|---|---|
| Crew Availability Agent | Determine available harvesting teams |
| Harvest Capacity Agent | Calculate how much produce crews can collect |
| Cost Agent | Calculate compensation and operational costs |
| Scheduling Agent | Evaluate timing and travel requirements |
| Crew Negotiator | Offer feasible harvesting schedules and prices |

For example:

> We can harvest 6,000 pounds tomorrow morning for $300. Recovering the remaining 4,000 pounds would require an additional crew.

The farm now has to negotiate with both the harvest crew and food banks.

You don't necessarily need to build this organization during the first implementation. Three or four independent negotiating organizations already satisfy the minimum Level 3 requirement.

---

# 3. How the multi-agent organizations communicate

This is the most important architectural decision.

**Internal specialists should generally communicate through their own organization's workflow. External organizations should communicate through a defined negotiation interface.**

For example:

```text
           FARM MAS
    ┌─────────────────────┐
    │ Surplus Agent       │
    │ Market Agent        │
    │ Cost Agent          │
    │ Scheduling Agent    │
    └──────────┬──────────┘
               │
               ▼
       Farm Negotiator
               │
               │ A2A message
               ▼
       Food Bank Negotiator
               │
               ▼
        ┌───────────────┐
        │ Demand Agent  │
        │ Storage Agent │
        │ Budget Agent  │
        └───────────────┘
```

This prevents one organization from reaching directly into another organization's private databases or internal reasoning.

For example, the Farm Negotiator may know that Food Bank A can contribute $200, but it shouldn't automatically gain access to Food Bank A's entire budget.

### Communication technology

I'd use:

| Communication | Technology | Purpose |
|---|---|---|
| Within each organization | LangGraph | Internal collaboration and state management |
| Between organizations | A2A protocol | Standardized communication between independent agents |
| Group negotiations | AGNTCY SLIM | Multi-party messaging |
| Discovering collaborators | AGNTCY Directory | Capability-based selection |
| External data and tools | MCP / HTTP APIs | Access to routing, agricultural, and other services |
| Observability | OpenTelemetry / AGNTCY Observe | Trace decisions and interactions |

These choices align with CoffeeAGNTCY, which already demonstrates LangGraph orchestration, A2A messaging, SLIM group communication, identity, and observability. Its Lungo application also provides a discovery-based recruitment pattern you can study. ([github.com](https://github.com/agntcy/coffeeAgntcy?utm_source=chatgpt.com))

Importantly, **an organization's negotiator is a gateway and local decision authority, not the central decision-maker for the entire network**.

---

# 4. How an actual negotiation would work

Let's walk through a complete scenario.

### Scenario: 10,000 pounds of surplus tomatoes

The system contains:

| Stakeholder | Situation |
|---|---|
| Farm A | 10,000 pounds of tomatoes, 36-hour harvesting deadline |
| Food Bank A | Wants 6,000 pounds, can store 4,500 |
| Food Bank B | Wants 5,000 pounds, can store 4,000 |
| Logistics A | One refrigerated truck, 7,000-pound capacity |
| Logistics B | Available 4,000-pound refrigerated truck |
| Community Advocate | Prioritizes underserved communities |

All numbers are simulated.

### Stage 1: Agent discovery

Farm A's negotiator publishes a surplus offer.

Food banks discover the opportunity based on the crop, location, and delivery window.

The farmer also discovers transportation providers based on their capabilities.

For example, the discovery request might be:

```json
{
  "required_capability": "refrigerated_transport",
  "pickup_region": "Fresno County",
  "minimum_capacity_lbs": 4000,
  "required_within_hours": 24
}
```

The discovery service returns potential providers.

**Crucially, discovering an agent doesn't mean assigning it a task.** The organizations still decide whether they want to transact.

This is your Level 2 capability-based discovery.

### Stage 2: Internal deliberation

Each organization independently evaluates the opportunity.

Farm A determines its required cost recovery.

Food Bank A evaluates capacity and demand.

Food Bank B evaluates capacity and demand.

The logistics companies calculate feasible transportation offers.

The Community Advocate analyzes the allocation implications.

None of these agents needs access to another organization's private internal state.

### Stage 3: Initial negotiation

The organizations join a negotiation session.

```text
FARM A:
I have 10,000 lbs available.
I need $450 in recovery costs.

FOOD BANK A:
I request 4,500 lbs.
I can contribute $200.

FOOD BANK B:
I request 4,000 lbs.
I can contribute $100.

LOGISTICS A:
I can transport 7,000 lbs for $350.

COMMUNITY ADVOCATE:
Food Bank B serves a higher-need area.
I recommend prioritizing its allocation.
```

They now have incomplete financial coverage and competing allocation requests.

### Stage 4: Counteroffers

The negotiators try alternative arrangements.

For example:

Food Bank A agrees to reduce its allocation to 3,000 pounds if it receives an earlier delivery.

Food Bank B maintains its request for 4,000 pounds.

Logistics A proposes a combined 7,000-pound delivery route.

The farmer agrees to provide 7,000 pounds in the first shipment, but only if the other organizations collectively cover the required recovery costs.

There is still a funding gap.

**The system should not manufacture consensus.** It must either find a financially feasible deal, negotiate a permitted concession, discover another funding participant, or acknowledge that agreement is impossible.

### Stage 5: Unexpected disruption

Before the participants finalize the agreement, Logistics A reports a refrigeration failure.

Its previously proposed service is no longer feasible.

This triggers:

1. Withdrawal of the affected transportation offer.
2. Discovery of alternative logistics providers.
3. Recalculation of transportation costs and delivery times.
4. New proposals from the farm and food banks.
5. Another negotiation round.

Logistics B may offer to transport 4,000 pounds.

Another newly discovered provider may offer to transport the remaining 3,000 pounds.

The organizations evaluate these offers and renegotiate.

This demonstrates Level 2 adaptation inside a Level 3 collective decision.

### Stage 6: Conditional agreement

Suppose the agents eventually identify a feasible arrangement.

They create a shared agreement containing:

```json
{
  "agreement_id": "AGR_001",
  "farm": "FARM_A",
  "deliveries": [
    {
      "recipient": "FOOD_BANK_A",
      "quantity_lbs": 3000,
      "logistics_provider": "LOGISTICS_C"
    },
    {
      "recipient": "FOOD_BANK_B",
      "quantity_lbs": 4000,
      "logistics_provider": "LOGISTICS_B"
    }
  ],
  "status": "pending_commitments",
  "required_approvals": [
    "FARM_A",
    "FOOD_BANK_A",
    "FOOD_BANK_B",
    "LOGISTICS_B",
    "LOGISTICS_C"
  ]
}
```

Notice that this is not automatically a completed agreement.

Each participating organization must approve its commitments, the financial terms must be covered, and all hard constraints must pass validation.

For a real-world implementation, required human approvals and food-safety checks would also have to be completed.

---

# 5. How do agents reach consensus without a supervisor?

I recommend a **distributed, constraint-based negotiation protocol**.

Each organization maintains its own utility function.

For instance, the farmer values cost recovery, the food banks value usable food received, and the logistics providers value economic feasibility.

The system doesn't need to force them onto one universal scoring scale.

Instead, it follows this protocol:

| Phase | What happens |
|---|---|
| Discovery | Agents identify potential collaborators |
| Proposal | An organization submits a structured offer |
| Evaluation | Every affected organization checks the proposal using its internal MAS |
| Counteroffer | Unsatisfied organizations propose alternatives |
| Deliberation | Agents exchange evidence and explain trade-offs |
| Commitment | Every required organization independently accepts the terms |
| Verification | Deterministic checks confirm quantities, costs, schedules, and safety constraints |
| Completion | Agreement is recorded, or negotiation ends with an explanation |

### A key distinction: Consensus is not majority voting

Suppose four organizations agree, but the farmer rejects the proposal because it cannot afford the harvesting costs.

The other four cannot simply vote to force the farmer to donate.

For each transaction, all organizations whose resources or obligations are included must accept their own commitments.

The Community Advocate can challenge the agreement and propose alternatives, but its authority must be defined explicitly. It might have a formal role in approving fairness requirements agreed upon before negotiation, without having unlimited power over private organizations.

### Preventing infinite negotiation

Set explicit stopping conditions:

- A maximum number of rounds.
- A deadline determined by produce perishability.
- A limit on repeated or unchanged proposals.
- Immediate termination of infeasible or unsafe options when they cannot be corrected.

When the negotiation fails, agents preserve their disagreement and explain why.

That outcome can actually strengthen your Level 3 demonstration.

---

# 6. Internal collaboration versus external negotiation

This difference should be reflected in the implementation.

| Attribute | Internal MAS | Interorganizational network |
|---|---|---|
| Participants | Specialized agents within an organization | Independent organizations |
| Primary purpose | Develop organizational recommendations | Reach mutually acceptable agreements |
| Shared information | Internal inventory, costs, and operational data | Offers, evidence, constraints, commitments |
| Coordination | Local LangGraph workflow | A2A communication and SLIM sessions |
| Decision authority | Organization's negotiator, within its mandate | All affected organizations approve their commitments |
| Conflict | Differences in analysis or recommendations | Competing objectives and scarce resources |
| Outcome | An organizational position or offer | Agreement, rejection, or escalation |

A single system-wide LangGraph supervisor that controls every negotiation would weaken the Level 3 claim.

Instead, I would use **local orchestration inside organizations and decentralized agreement between organizations**.

A neutral session service can validate message formats, manage timeouts, and store events. That's infrastructure, not an authority that selects the winning proposal.

---

# 7. How I would actually implement it

You don't need to deploy 25 separate LLM-backed services.

For a hackathon, I'd distinguish *logical agents* from *deployed services*.

### Deployment architecture

```text
                    React Dashboard
                          │
                          ▼
                  FastAPI Backend
                          │
                 Scenario Simulator
                          │
              ┌───────────┴───────────┐
              │                       │
       Agent Discovery          Negotiation Log
              │                       │
              ▼                       ▼
         AGNTCY Directory          PostgreSQL
              │
              ▼
      AGNTCY / A2A / SLIM
              │
    ┌─────────┼──────────┬────────────┐
    ▼         ▼          ▼            ▼
 Farm MAS  Bank A MAS  Bank B MAS  Logistics MAS
    │         │          │            │
 LangGraph LangGraph  LangGraph    LangGraph
    │         │          │            │
  Tools     Tools       Tools        Tools
```

The Community Advocate would be another independent MAS connected to the same messaging network.

Each organization can expose a single external A2A endpoint while using several specialized LangGraph nodes internally.

This approach reduces engineering overhead without removing organizational autonomy.

### Example: Farm MAS in LangGraph

```python
from langgraph.graph import StateGraph

workflow = StateGraph(FarmState)

workflow.add_node("surplus", surplus_agent)
workflow.add_node("market", market_agent)
workflow.add_node("cost", cost_agent)
workflow.add_node("harvest", harvest_agent)
workflow.add_node("negotiator", negotiation_agent)

workflow.add_edge("surplus", "market")
workflow.add_edge("market", "cost")
workflow.add_edge("cost", "harvest")
workflow.add_edge("harvest", "negotiator")
```

This is just a simplified illustration. In the actual system, the negotiator should be able to re-enter the workflow when an external counteroffer arrives.

For example:

```text
Receive counteroffer
        │
        ▼
 Farm Negotiator
        │
        ▼
 Does the offer change
 costs or deadlines?
        │
    ┌───┴───┐
    │       │
   Yes      No
    │       │
    ▼       ▼
Recalculate Evaluate
    │       │
    └───┬───┘
        ▼
 Accept / Counter / Reject
```

That re-evaluation loop is important because negotiations aren't linear.

---

# 8. How this architecture addresses the judging criteria

| Criterion | What we demonstrate |
|---|---|
| **Functionality** | Internal MAS teams complete analysis, and independent organizations produce an actionable agreement |
| **Innovation** | Multi-level collective intelligence with community representation and independent economic objectives |
| **Agent intelligence** | Internal reasoning, external negotiation, evidence exchange, counteroffers, concessions, and adaptation |
| **Engineering** | Modular LangGraph organizations, A2A interfaces, validated structured messages, and observable negotiation state |
| **Demonstration** | A live view showing each organization's internal analysis and the external negotiation |
| **Learning and evidence** | Compare independent negotiation, negotiation without community advocacy, and centralized matching |

## The demonstration I'd emphasize

In the frontend, show **two synchronized views**.

**View 1: Inside an organization**

Click on Farm A to see its specialized agents evaluating surplus, costs, and harvesting deadlines.

Click on Food Bank B to see its demand, storage, and budget analyses.

**View 2: Between organizations**

Show the negotiation timeline, with offers, counteroffers, supporting evidence, and agreement status.

When the refrigerated truck fails, judges should see the logistics agents detect the problem, new providers being discovered, and every affected organization independently reconsidering the deal.

This makes both kinds of intelligence observable.

---

## My recommended MVP

I would start with **four independent organizations**, each represented by a small MAS.

| Organization | Internal components |
|---|---|
| Farm | Surplus Agent, Cost Agent, Negotiator |
| Food Bank A | Demand Agent, Storage Agent, Negotiator |
| Food Bank B | Demand Agent, Storage Agent, Negotiator |
| Logistics | Routing Agent, Fleet Agent, Negotiator |

Add the Community Advocacy MAS as the fifth organization once this works.

Not every specialist must be an LLM. A storage-capacity checker or route calculator can be a deterministic tool operated by an agent. Reserve LLM reasoning for interpreting evidence, making proposals, selecting collaborators, and negotiating trade-offs.

**One especially important point:** The Community Advocate shouldn't be merely a final fairness checker. It should participate in negotiation while allocations are still being considered. Otherwise, it risks becoming another centralized validator rather than an independent voice.

### The architectural principle I'd follow

**Each organization thinks internally, negotiates externally, and commits independently.**

That's how HarvestNet can demonstrate Level 1 collaboration within organizations, Level 2 adaptation across organizations, and Level 3 collective intelligence across the entire network.

And it gives you a compelling question for the judges: **Can independently motivated organizations reach socially beneficial agreements without surrendering their autonomy to a central AI?**
