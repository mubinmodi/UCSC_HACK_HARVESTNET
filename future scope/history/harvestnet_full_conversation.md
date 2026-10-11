# HarvestNet — Full Conversation Context
> Complete transcript for Claude Code session setup. Every question and answer preserved in full.

---

## Message 1 — Challenge Brief (User)

```
When AI Agents Disagree
From collaboration to collective intelligence

The challenge:
Can you build AI agents that work together, adapt to changing conditions, and make decisions even when
they disagree? Individual agents can reason, use tools, and solve complex problems. This challenge asks
what happens when independent agents bring different capabilities, incomplete information, competing
priorities, or conflicting recommendations to the same problem.

Choose one of three levels:

LEVEL 1 · BUILD AN AI TEAM
Build or extend a multi-agent system with specialized agents that collaborate to solve a problem.
Examples: add shipping, quality control, or sustainability agents to a coffee supply chain; a campus
assistant for transportation, scheduling, and events; a research team that gathers, analyzes, and
verifies information.
Success: distinct capabilities, meaningful communication, and a completed shared task.

LEVEL 2 · BUILD AN ADAPTIVE AI TEAM
Agents that dynamically discover collaborators, adapt to changing conditions, and resolve conflicting
recommendations.
Examples: a coffee exchange finds new suppliers after a shipment fails; a disaster response team
reallocates resources; a campus planner adjusts when transportation or facilities become unavailable.
Success: dynamic discovery or capability-based selection; a response to at least one unexpected change
or failure; resolved conflicting recommendations.

LEVEL 3 · BUILD A COLLECTIVE INTELLIGENCE
At least three autonomous agents with competing objectives that deliberate, negotiate, and try to reach
consensus without a central decision-maker.
Examples: energy agents balancing cost, sustainability, and reliability; emergency agents negotiating
scarce resources; research agents weighing conflicting hypotheses.
Success: genuine disagreement, a real deliberation or negotiation mechanism, the effect of new
information, and a comparison against a simpler baseline.

PRIZES:
1st Place: 4x iPad Pros
2nd Place: 4x Nintendo Switches
3rd Place: 4x Razer Viper v3 Pro wireless esports gaming mouse

Resources:
github.com/agntcy/coffeeAgntcy
github.com/agntcy/coffeeAgntcy/blob/main/TUTORIAL.md
docs.agntcy.org/coffee-agntcy/get-started
```

**User:** I want to make something that uses all levels, I'm looking for more social impact

---

## Message 2 — Claude: Initial Concept (FoodBridge)

### Concept: FoodBridge, a food rescue network that negotiates who gets what before it spoils

Every day, grocery stores, restaurants, and farms throw out edible food while shelters, pantries, and senior centers nearby run short. Real food rescue organizations coordinate this by phone and spreadsheet, and the hard calls get made under time pressure: where does the surplus go, and who gets the one refrigerated van?

This idea fits the challenge well for three reasons. The disagreements are real and morally meaningful, not invented for the demo. It maps closely onto coffeeAGNTCY's supply-chain patterns, so you can adapt Lungo instead of starting from scratch. And the impact is easy for judges to grasp: pounds of food saved and people fed.

### How it builds through the three levels

**Level 1, the team.** Start with specialized agents that complete one shared task: getting a donation from a donor to people who need it.
- **Donor agents** (a grocery store, a bakery, a farm) announce surplus with quantity, type, and a spoilage deadline.
- **Recipient agents** (a family shelter, a school pantry, a senior center) know their population size, current stock, and dietary constraints.
- A **logistics agent** manages drivers and vehicles, including which ones have refrigeration.
- A **food safety agent** checks temperature windows and allergens.

Multiple agents make sense here because each party has private information and its own interests. No one agent should know or decide everything.

**Level 2, the adaptive team.** Recipients register their capabilities in the AGNTCY directory, for example "accepts perishables, has a walk-in freezer, serves halal." The system selects partners based on those capabilities rather than a hardcoded list. Then you inject disruptions during the live demo:
- A volunteer driver cancels.
- The refrigerated van breaks down, so dairy suddenly can't go to distant sites.
- A new pop-up pantry comes online after a local apartment fire.

You can show the system rediscovering the new pantry, rerouting around the broken van, and logging why each agent was chosen.

**Level 3, collective intelligence.** Remove the central allocator. Give three or more agents competing objectives and have them negotiate directly:
- An **equity agent** pushes food toward the most underserved communities.
- A **waste agent** wants the fastest, closest delivery before food spoils.
- A **nutrition agent** fights for fresh produce and protein over just moving calories.
- The **recipient agents** advocate for their own populations.

For the deliberation mechanism, one workable approach is rounds of proposals and counterproposals with justifications. Each agent scores proposals against its own objective, and the agents converge using something like fairness credits: a site that gave up food today gets priority tomorrow. New information should visibly shift the outcome. For instance, the shelter reports it just received 200 new families, or the food safety agent revises a spoilage estimate.

### The parts that will win Level 3

**Compare against a simple baseline.** Run the same scripted scenario under first-come-first-served or a greedy "send it to the nearest site" rule, then compare:
- pounds of food wasted
- unmet need per site
- a fairness measure such as the Gini coefficient across recipients
- time to decision

A greedy rule usually wastes less but keeps sending food to the same well-located sites. Showing that tradeoff with numbers covers the "learning and evidence" criterion.

**Define when to stop, keep the disagreement, or escalate.** The system should not always force consensus:
- **Escalate to a human coordinator** when food safety is uncertain or when the equity-versus-waste gap exceeds a set threshold.
- **Preserve the disagreement** and show the coordinator the competing options with each agent's reasoning, rather than presenting a fake unanimous answer.
- **Stop with a default rule** when spoilage time runs out, because a decent decision now beats a perfect one after the milk goes bad.

In real food rescue, a human keeps final authority on safety and ethics, so building that in strengthens the social impact case.

### Keeping it buildable for a hackathon

Use synthetic but realistic data, such as 5 donors, 6 recipients, and 3 drivers in one city. Script a repeatable scenario with timed disruptions so the demo goes the same way every time. Build a simple dashboard that shows a map, the negotiation transcript, and the baseline-versus-system metrics side by side.

---

## Message 3 — User

**User:** I want you to do a web search, find areas that need a solution like this and don't have a system that works for them. Level 3 is supply chain problem, Level 1 can be incorporated in Level 3 (agents working for other agents)

---

## Message 4 — Claude: Research on Problem Areas

*(Based on web searches of ReFED 2026 report, hospital drug shortage surveys, Hurricane Helene disaster donation research, and USAID disruption news.)*

I found four areas with the same pattern: independent organizations share a scarce or perishable supply, nobody has authority over all of them, and today they coordinate by phone, spreadsheet, or first-come-first-served.

### 1. Drug shortages across independent community hospitals (strongest Level 3 fit)

ASHP reported 216 active drug shortages in early 2026, and three-fourths of active shortages originated in 2022 or later. Smaller and community hospitals are hit hardest because they often lack the purchasing volume to get priority access from distributors. One pharmacy leader described the result: when a drug suddenly runs short, it becomes far harder to obtain "because there's no allocation."

A national survey found that 81 percent of hospital pharmacy managers had experienced medication hoarding, and one in three said their hospital had no valid administrative mechanism to respond to a shortage. In a Michigan study, one-fourth of respondents did not know who makes drug allocation decisions, and strategies included hoarding supply, requesting it from local hospitals, and transferring patients.

Tools such as Bluesight's are designed for a single health system. Independent hospitals in the same region have no shared mechanism. Today they just make informal calls to each other.

This makes it a near-perfect Level 3 problem. The hospitals are autonomous with no central decision-maker. Each one's objective conflicts with the others: protect its own patients, which in practice means hoarding. Hoarding is also your baseline, so you can show it leaves everyone worse off. The human-escalation boundary is natural: agents negotiate inventory between hospitals, but any choice about which patient gets a drug goes to a human ethics committee.

### 2. Food rescue between grocers and pantries

A 2026 ReFED report found that only 13% of grocery retailers' surplus food is donated to food banks. A major obstacle is that food banks often don't get reliable estimates of how much surplus will be available for pickup. In Seattle, interviews found that with little to no communication between food banks and donors, the banks get an overflow of the same food category or of unusable food. Alphabet's X team reached the same conclusion: there's no easy way for suppliers to tell food banks what they have, or for pantries to say what they need.

Existing apps mostly work as claim-first marketplaces. That is exactly the first-come-first-served baseline that negotiation can beat.

### 3. Disaster donation logistics

After Hurricane Helene, parts of North Carolina dealt with an overflow of donations that had nowhere to go. A resilience expert noted that after Hurricane Florence, warehouses filled up and couldn't distribute everything in time, so some goods went bad or expired. In Yancey County, donations piled up across schools, fire stations, and churches. The same thing happened in Maui after the fire, so the problem recurs.

### 4. Humanitarian medicine pipelines after funding shocks

When USAID was disrupted, essential medicines expired in the DRC after a contractor had to shut off the air conditioning, and staff scrambled to redirect HIV, malaria and tuberculosis medication to warehouses around the globe.

### My recommendation and how your layering fits

I'd build on **#1 (regional drug-shortage exchange)** for innovation, or **#2 (food rescue)** if you want easier data and a lower-stakes demo.

Your idea of "agents working for agents" fits either one with three tiers:
- **Level 1 (inside each organization):** Each hospital's negotiator agent is supported by its own team. An inventory agent tracks days-on-hand, a clinical demand agent forecasts usage from patient acuity, and a substitution agent knows the therapeutic alternatives.
- **Level 2 (the network):** Hospitals discover each other through the AGNTCY directory by advertising capabilities.
- **Level 3 (between organizations):** The hospital agents negotiate lend/borrow agreements with no central allocator.

---

## Message 5 — User

**User:** has some made something like this??

---

## Message 6 — Claude: Prior Art Research

*(Based on web searches of arXiv papers, hackathon projects, and deployed platforms.)*

Yes, parts of it exist, but nobody has built the full combination you're planning. Existing work falls into three groups.

### 1. Exchanges and marketplaces (deployed, but humans do the negotiating)

**Hospitals:** During COVID, Premier and Resilinc launched an exchange where hospitals could work with vetted peer organizations to identify, locate, and exchange critical medical items. It was built because hospitals looking for items on supplier allocation had to manually find other hospitals with inventory. Saudi Arabia runs a national Medication Exchange and Sharing Network Program (MESNP) for drug shortages. A hackathon team also built MediChain — they found that hospital coordination is mostly done manually through phone calls, spreadsheets, or WhatsApp groups.

**Disasters:** Aidmatrix has been doing donation matching for years. The FEMA-funded network it powers covered 92 percent of the U.S. and was used by over 47,500 organizations, including 200-plus food banks. Even so, Helene relief still ended up with overflowing warehouses. Matching platforms alone haven't solved the problem.

All of these are listing-and-matching tools. They show what's available, but people still make the calls, haggle, and hoard.

### 2. Optimization research (math models, not agents)

Operations researchers have modeled this. One study proposed a proactive inventory sharing approach for critical drugs across hospitals in a health network. Another developed an optimization model for inter-facility medicine sharing ahead of anticipated shortages. These models assume a single network or a single optimizer making the decisions. That is the central decision-maker that Level 3 asks you to remove.

### 3. LLM multi-agent research (the closest to your idea)

**The most similar project:** A 2025 arXiv paper presents a decentralized, LLM-powered multi-agent negotiation system combined with blockchain, where agents representing manufacturers, distributors, and healthcare institutions negotiate allocation of scarce medical resources during crises. It was evaluated in a simulation of pandemic scenarios. You should read it, cite it, and position your project against it (arxiv.org/abs/2507.17134).

**Food:** Food4All is described as the first multi-agent framework for real-time, context-aware free food retrieval. However, it helps individuals find food rather than allocating supply between organizations. At 412 Food Rescue in Pittsburgh, researchers deployed RescueLens, which categorizes volunteer feedback and suggests donors and recipients to follow up with.

### Where your project is still new

No one found combines all of these:
- **Hierarchical agents:** each organization's negotiator is backed by its own Level 1 sub-agent team
- **Dynamic discovery:** AGNTCY directory discovery and a live disruption in the demo
- **No blockchain:** a lightweight reciprocity ledger instead
- **Policies for when not to agree:** preserving disagreement and escalating to humans are explicit features
- **A realistic baseline:** comparing against "every hospital hoards," which the surveys show is what actually happens
- **A specific gap:** regional independent community hospitals, the group the single-system tools don't serve

---

## Message 7 — User

**User:** 1. Exchanges and marketplaces (deployed, but humans do the negotiating) — how is this done in USA??

---

## Message 8 — Claude: How Drug Shortage Allocation Works in the USA

*(Based on web searches of Minnesota health department guidance, Premier Inc. recommendations, ASHP surveys, and IV fluid shortage news.)*

In the U.S., drug-shortage allocation happens at several layers, and only the top one is systematic. Hurricane Helene's IV fluid shortage is a good example to follow through each layer.

### Layer 1: Manufacturers and wholesalers ration by past purchases

When a drug runs short, the manufacturer limits how much each customer gets, and wholesalers pass that limit down. Most hospitals buy through Cencora, Cardinal Health, and McKesson. The method: wholesalers look at each facility's "usual use" numbers, and if every hospital orders more than usual, they fill orders as a percentage of usual use.

Here's how that played out after Helene. Baxter's North Cove plant supplies an estimated 60% of IV solutions in North America. After it flooded, one North Carolina hospital's pharmacy department received only 40% of its usual IV fluid supply, and Baxter said these allocations were necessary to prevent stockpiling. Later, Baxter raised allocations of its highest-demand fluids for direct customers from 40% to 60% and for distributors from 10% to 60%, and set designated children's hospitals to 100%.

Allocating by past purchases is simple and fair in one sense, but it ignores current need. A hospital whose patient load just spiked still gets its historical share.

### Layer 2: Group purchasing organizations negotiate contracts ahead of time

The three leading GPOs are Vizient, Premier, and HealthTrust, and between 96 and 98 percent of hospitals belong to at least one GPO. Their shortage tools are mostly arranged in advance. For example, a "guaranteed supply program" works like insurance: members pay a premium, the GPO holds four months of a drug, and it releases that supply to members during a shortage. These programs help members before a crisis, but they don't move drugs between hospitals once a shortage hits.

### Layer 3: Health systems share inventory internally

Multi-hospital systems can move stock between their own sites using inventory software. Independent hospitals have no equivalent.

### Layer 4: Hospitals borrow from each other, mostly by phone

The law generally allows this. In Washington State, the relevant exemptions cover the sale of a drug for emergency medical reasons, a term that isn't defined but includes transfers between pharmacies to ease temporary shortages. Illinois law says nothing prohibits one hospital pharmacy from buying or receiving a drug in shortage from another hospital pharmacy during a medical emergency. In practice, this is the phone-call, spreadsheet, and WhatsApp layer.

### Layer 5: Regional healthcare coalitions coordinate in emergencies

Some regions have standing coalitions. During the Helene shortage, the Health Collaborative said Greater Cincinnati hospitals were working together to handle the shortage, using plans refined during COVID-19 to share resources. This works where the coalition is strong, but coverage is patchy and it mostly runs on meetings and calls.

### What this means for your project

The U.S. system has a rigid, history-based allocator at the top and improvised negotiation at the bottom. Your agents can fill the middle:
- **Wholesaler allocation as the given constraint.** Each hospital agent starts with its percentage-of-usual-use allocation.
- **Lateral negotiation as your Level 3 mechanism.** Hospital agents trade and lend among themselves based on current need.
- **Two baselines.** Compare against pure historical allocation with no sharing, and against hoarding.
- **Realistic human checkpoints.** Each transfer is a recommendation that a pharmacist approves.

The Helene IV fluid shortage would make a strong demo scenario. It's real, well documented, and connects to the disaster-relief story you might also use.

---

## Message 9 — User

**User:** any other industry other than healthcare??

---

## Message 10 — Claude: Other Industries Research

*(Based on web searches of homeless shelter coordination, farm surplus, and wildfire resource problems.)*

Yes. Outside healthcare, I found three more areas with the same pattern: independent organizations, a scarce or perishable resource, and coordination that still runs on phone calls.

### 1. Farm surplus going to food banks (best supply-chain fit)

Crops get plowed under while food banks run short. In California's Central Valley, a KQED report found no solution in sight for bridging food insecurity and crop overproduction, because harvesting the surplus and hauling it to food banks takes money and labor. Food banks deal with shortages piecemeal, and when they tried getting volunteers to glean produce off farms, it didn't work. The potential for food to be left in fields is increasing because of rising labor costs.

In Canada, an estimated 13 per cent of fruits and vegetables go unharvested or are discarded. Many farmers can't afford to harvest, box, and transport unsold produce for free, especially vegetables that spoil within two weeks.

What makes this a strong Level 3 problem is that each party has its own constraint and nobody controls the whole chain:
- **Growers** can't absorb more cost
- **Food banks** have limited capacity for perishables
- **Labor and logistics** are the middle bottleneck

Nonprofits like Farmlink do this work by hand. There's also a practical bonus: coffeeAGNTCY is already a farm-to-buyer supply chain with farm agents. You'd be reusing its structure almost directly. Coffee farms become produce growers, and the exchange becomes a negotiation between food banks, harvest crews, and truckers.

### 2. Homeless shelter beds (an allocation problem, but not quite a supply chain)

Los Angeles shows how badly this can fail. A city audit found LAHSA was tracking available beds through emails and phone calls, and about 50% of those calls went unanswered. In August 2025, data showed only two of 88 beds occupied at one East Hollywood shelter, in a county where about 47,000 people sleep on the streets. Even LAHSA's replacement system ran into problems — its interim CEO said the software behaved in unexpected ways, and staff still had to call shelter operators to confirm beds were available.

In Toronto, one person told city council they made 107 calls in January and didn't get a single bed.

San Diego's Shelter Ready app replaces paper waitlists and phone calls with real-time bed inventory, and providers say the time it takes to place a client has been cut by more than half. However, Shelter Ready is a booking system, not a negotiation.

### 3. Wildfire resource ordering (adaptive, but it has a central allocator)

When fires overlap, crews and engines are fought over. One national coordinator said he arrived at 7 a.m. to 800 orders already waiting, and that no large fire would get every resource it asked for. This fits Level 2 well but fits Level 3 poorly, because the national system in Boise decides which fires get priority when equipment and firefighters run short.

### Comparison table

| | Farm surplus | Shelter beds | Wildfire |
|---|---|---|---|
| Real supply chain? | Yes | Partly | Yes, but equipment/crews |
| No central decision-maker? | Yes, fully decentralized | Mixed | No, national prioritization exists |
| Existing tools | Manual nonprofits like Farmlink | Booking apps like Shelter Ready | Formal dispatch system |
| Reuses coffeeAGNTCY | Very closely (it's farm-based) | Loosely | Loosely |
| Demo data | Easy to simulate | Easy to simulate | Harder |

**My pick is farm surplus to food banks.** It's a genuine supply chain, it has no central coordinator, its competing objectives are built in (grower cost, labor, cold storage, fairness across food banks), and it maps almost one-to-one onto coffeeAGNTCY.

---

## Message 11 — User

**User:** also I should be able to get open source data

---

## Message 12 — Claude: Open Source Data Sources

*(Based on web searches of ReFED Insights Engine, USDA NASS Quick Stats API, Feeding America Map the Meal Gap, and USDA AMS Market News.)*

Yes, the farm surplus version can run mostly on free public data. The one exception is that no public dataset tracks actual farm surplus or food bank capacity, so you'll simulate those using real numbers as calibration.

### Data by agent

| Agent | Data it needs | Source | Access |
|---|---|---|---|
| Grower | What's grown, where, and how much | USDA NASS Quick Stats | Free API key |
| Grower / market | Whether today is a glut (low prices signal surplus) | USDA AMS Market News | Free, has an API |
| Food bank | How much need exists in each service area | Feeding America Map the Meal Gap | Free, by request form |
| Food bank | Locations | OpenStreetMap (`amenity=food_bank`) via the Overpass API | Free, open license |
| Equity / fairness | Low-income, low-access neighborhoods | USDA ERS Food Access Research Atlas, Census ACS | Free download |
| Spoilage / disruption | Heat waves that shorten shelf life | National Weather Service API | Free, no key |
| Logistics | Drive times between farms and food banks | OSRM or OpenRouteService on OpenStreetMap | Free, open source |
| Calibration | How much surplus exists by state and food type | ReFED Insights Engine | Free online |

### USDA NASS Quick Stats
Has county-level data, with download files covering planted and harvested area, yield per acre, and production. Register for a free API key at quickstats.nass.usda.gov/api. One limitation: NASS suppresses some data to protect individual farmers' privacy, so some counties will have gaps.

### USDA AMS Market News
Probably your most useful source. Its reporters collect and validate data on price, volume, quality, and condition, and publish it within hours at no cost. Downloadable data covers terminal markets, shipping points, retail, movement, truck rates, and trends. The Fresno Shipping Point Fruit Prices feed has API query strings for pulling the latest reports or a date range. A sudden price drop for a crop is a realistic trigger for your grower agent to decide that harvesting for market isn't worth it and to offer the crop for donation instead. API base: `https://marsapi.ams.usda.gov/services/v1.2/`

### Map the Meal Gap
Gives your food bank agents a real measure of need. It estimates food insecurity for every county and congressional district, and for each Feeding America food bank's service area. Variation across counties is large: from 3% in Bowman County, North Dakota to nearly 30% in places like Holmes County, Mississippi. The full dataset is available through a data request form — request it early.

### ReFED
Useful for setting realistic surplus volumes. Its Food Waste Monitor is built from more than 50 public and proprietary datasets and estimates how much food goes uneaten in the U.S., why, and where it goes. Includes state-level data.

### What you'll have to simulate

No public data exists for daily surplus at individual farms, food bank cold storage capacity, volunteer or harvest crew availability, or actual donation transactions. Generate these values from the real data: base a farm's surplus on NASS production plus an assumed loss rate, and base a food bank's capacity on its service-area population. State the assumptions clearly.

### Suggested scope

Pick one region such as a handful of Central Valley counties, and one or two crops with strong AMS coverage. Use real farm-region locations from NASS, real food bank locations from OpenStreetMap, real need from Map the Meal Gap, real drive times from OSRM, and a real heat event from NWS history as your scripted disruption.

---

## Message 13 — User

**User:** help me identify the stakeholders in this system

---

## Message 14 — Claude: Stakeholder Identification

Here's a stakeholder map for the farm surplus to food bank system, grouped by the role each would play in your design.

### 1. Core stakeholders (your Level 3 negotiating agents)

These are independent organizations with their own goals. None of them can tell the others what to do.

| Stakeholder | What they want | Main constraint | What they bring to a deal |
|---|---|---|---|
| **Growers** | Recover harvest costs and avoid plowing food under | Harvesting, packing, and hauling unsold crops costs money they won't get back | The produce and a deadline |
| **Regional food banks** | Fresh, nutritious food for their service area | Limited cold storage, staff, and budget for perishables | Distribution reach and partner pantries |
| **Logistics providers** (refrigerated truckers, cold storage operators) | Paid, efficient routes without wasted trips | Truck availability and refrigeration | Moving and holding food |
| **Harvest crews** (labor contractors or gleaning groups) | Fair pay and predictable work | Scarce and expensive, the bottleneck WWF identified | Getting crops out of the field |

The basic conflict is that the grower has food but can't pay to move it, the food bank needs it but can't pay full cost or store unlimited amounts, and labor and trucks are scarce for everyone. Several food banks also compete for the same load.

### 2. Sub-agents inside each organization (your Level 1 layer)

Each core agent is backed by its own team:

- **Inside a grower:** a yield and surplus estimator, a market-price watcher using AMS data, and a cost calculator for harvest, packing, and hauling.
- **Inside a food bank:** a cold storage capacity agent, a demand agent using Map the Meal Gap and pantry requests, a nutrition agent that weighs fresh produce against what's already in stock, and a volunteer and sorting scheduler.
- **Inside a logistics provider:** a routing agent using OSRM and a fleet availability agent that tracks which trucks have working refrigeration.

### 3. Intermediaries (what your system augments)

Organizations that already do this matchmaking by hand: The Farmlink Project, the California Association of Food Banks' Farm to Family program, Second Harvest in Canada, and local gleaning nonprofits. In your pitch, describe the system as a tool that multiplies their capacity rather than replaces them.

### 4. Rule-setters and funders (environment constraints, not agents)

- **USDA** funds food purchases for food banks, and AMS publishes the market data you're using.
- **State agriculture departments** such as CDFA, which partnered with the California Association of Food Banks to fund farm donations to feeding programs.
- **Food safety regulators** including county health departments and federal produce safety rules.
- **Liability and tax law.** The federal Bill Emerson Good Samaritan Act protects good-faith food donors, and some states offer tax credits for donated produce.

### 5. Alternative destinations (the grower's walk-away options)

- Selling imperfect produce to processors (companies like Full Harvest deliver imperfect fruits and vegetables to food processors)
- Animal feed
- Compost
- Tilling it back in

These are the grower agent's best alternatives to a negotiated agreement. The grower agent can turn down a bad deal.

### 6. Stakeholders without a voice

- **Food-insecure people.** They're the reason the system exists, yet they never appear at the negotiating table. This is the strongest argument for an **equity agent** that advocates for underserved areas using Map the Meal Gap and Food Access Atlas data.
- **The environment.** Food left in fields or sent to landfill has a climate cost. A **sustainability agent**, or a waste penalty in the scoring, can represent it.

Pointing out that the people who matter most have no seat at the table, and that you designed an agent to represent them, is the kind of insight that stands out under the "agent intelligence" and "learning" criteria.

### Where humans stay in the loop

Three stakeholders should keep final authority: the **food safety reviewer** for any uncertain or temperature-compromised load, the **food bank operations manager** to approve accepting a large perishable delivery, and the **grower** to approve any agreement that costs them money.

---

## Message 15 — User

**User:** has someone done this??

---

## Message 16 — Claude: Prior Art for Farm Surplus to Food Banks

*(Based on web searches of Farmlink Project, Zest/Nestlé UK consortium, r4 Technologies, and operations research papers.)*

Yes, parts of it exist, but I couldn't find anyone who has built autonomous agents negotiating farm surplus among growers, multiple food banks, and truckers. Existing work falls into three groups.

### 1. Human-run matchmaking (the deployed version)

**The Farmlink Project** is the closest real-world equivalent, reporting moving nearly 500 million pounds of food over five years. Its model is coordination, not owning assets — it doesn't own trucks or warehouses; it works with farms to find surplus and matches it with food banks.

The process is still mostly manual. Fellows send transaction details (origin and destination, produce type and weight, timeline) to leadership, who then get quotes from third-party trucking companies. On the food bank side, Farmlink contacts the food banks closest to a farm to check shelf-life requirements, capacity limits, and what they need.

**Farmlink's internal process (from their own documentation):**
> In the early days, this process involved Google searches for nearby farms and an endless cycle of cold-calling and emailing. Farmlink fellows send the transaction information (including the address of origin and destination, type and mass of produce, and transfer timeline) to our leadership, who then receive quotes from local third party logistic trucking operations.

This is your strongest validation. A successful nonprofit performs, by hand, every step your agents would automate.

### 2. AI matching platforms (mostly for retail and manufacturer surplus, not farms)

- **UK consortium (Zest, FareShare, Nestlé, Google Cloud):** a pilot platform that automatically identifies surplus products and matches them to charity needs based on location, capacity, and dietary requirements. Funded by a $2.5 million Innovate UK grant. Focuses on connecting food manufacturers, logistics providers, and charities — not farms directly.
- **r4 Technologies Smart Food Program:** uses AI to spot retailer surplus in real time and redirect it to food banks and SNAP beneficiaries before it expires. Described as "reframing hunger as a logistics problem rather than a supply issue."
- **Smaller tools** like Food Cowboy and FOODres.ai, which match surplus to the nearest recipient.

All of these use a central matching engine. One platform decides who gets what. Level 3 asks for the opposite: no central decision-maker.

### 3. Operations research on gleaning (optimizing for one food bank)

Cornell researchers built a stochastic optimization model of a gleaning operation for a New York food bank and found that scheduling gleaning trips 3 to 4 times per week maximized the volume of fruits and vegetables gleaned. Another study (Operations Research journal) created a dynamic staffing policy that recovered about 10% of the volume lost under a static policy.

These papers optimize a single food bank's operations. They don't model multiple independent organizations with competing goals.

### Where your project is new

| | Farmlink | AI platforms (Zest, r4) | OR research | **Your project** |
|---|---|---|---|---|
| Farm surplus | Yes | Mostly no | Yes | Yes |
| Multiple independent organizations | Yes, coordinated by people | Yes, through a central matcher | No, one food bank | **Yes** |
| No central decision-maker | No, Farmlink staff decide | No | No | **Yes** |
| Agents negotiate | No | No | No | **Yes** |
| Adapts to disruptions | People improvise | Partly | Modeled statistically | **Yes, live** |
| Represents people without a voice | Implicitly | No | No | **Yes, via an equity agent** |

**One-sentence pitch:** "Farmlink proved this works by phone, the UK pilot proved central AI matching works for packaged surplus, and Cornell modeled gleaning for a single food bank. We're the first to let growers, food banks, and truckers each run their own agents that negotiate surplus allocation, with no coordinator in the middle."

---

## Message 17 — User

**User:** I want to know in detail what each stakeholder will need

---

## Message 18 — Claude: Detailed Stakeholder Needs

*(Based on web searches of food bank donation guidelines from Pittsburgh, Philabundance, Redwood Empire, California Farm to Food Bank tax credit legislation, and gleaning research.)*

### 1. Growers

A grower's decision is simple: donate, sell to a processor, or till the crop under.

| Need | Details |
|---|---|
| **To know** | Today's market price; how much is harvestable and by when; which food banks can take it and how much |
| **To have** | A buyer or recipient committed before harvest starts, because labor is spent before the food moves |
| **To be paid or covered** | Harvest, pack, and haul costs. Some programs pay growers a fee for picking and packing donated produce (called a PPO fee). |
| **Paperwork** | A donation receipt for tax credit. In California, growers can get a credit of 15% of the qualified value of the donation, which can include fresh fruits and vegetables, eggs, meat, dairy, and grains. The farm to food bank tax credit program produced $10.7 million of food donations in 2024 and has been extended to 2032. |
| **Guaranteed** | Liability protection (Good Samaritan Act) and a firm pickup time |
| **Will refuse if** | Total cost minus tax credit is worse than plowing under or selling to a processor, or pickup timing is uncertain |

**Grower agent inputs:** NASS yield, AMS price, harvest cost model, tax credit rate, spoilage deadline.  
**Grower agent outputs:** a surplus offer with quantity, crop, location, ready-by date, minimum cost recovery needed, and packaging available.

### 2. Harvest crews (labor contractors or gleaning volunteers)

| Need | Details |
|---|---|
| **To know** | Field location, crop type, volume, start time, and expected hours |
| **To have** | Transportation to the field, equipment and bins, and heat safety plans for summer harvests |
| **To be paid or covered** | Paid crews need a firm rate. Volunteers need reliable scheduling — no-shows are common. Gleaning depends on two uncertain inputs: the food supply and the labor supply. |
| **Guaranteed** | That a truck will be there when the bins are full, so their work isn't wasted |
| **Will refuse if** | No one confirms who pays, the date changes at the last minute, or heat conditions make work unsafe |

**Labor agent outputs:** crew availability, cost per hour or per bin, confirmed headcount including a no-show probability for volunteer crews.

### 3. Logistics providers (refrigerated truckers and cold storage)

| Need | Details |
|---|---|
| **To know** | Pickup and drop locations, weight, pallet count, required temperature, and time window |
| **To have** | Food on pallets ready to load. The Collaborative for Fresh Produce requires produce to be palletized in cartons, bags, or boxes. |
| **To be paid or covered** | The trip rate including empty return miles. AMS truck-rate data gives realistic numbers. |
| **Paperwork** | Temperature logs — temperatures of refrigerated foods must be taken when they reach the food bank and recorded on a receiving form. |
| **Guaranteed** | Someone at the receiving dock to unload |
| **Will refuse if** | The load isn't palletized, the route is too long for the rate, or no one can unload at the destination |

Different produce needs different temperatures, so trucks can't always carry mixed loads.

**Logistics agent outputs:** a quote with price, earliest pickup, transit time, and reefer availability. Also produces disruption events.

### 4. Regional food banks

These are the most complex agents because they have to balance capacity, quality, and their communities' needs.

| Need | Details |
|---|---|
| **To know** | Exactly what's coming: crop, quantity, condition, and arrival time |
| **Quality thresholds** | For whole produce, at least 80% must be usable for roughly 5 days. The Collaborative for Fresh Produce accepts all edible imperfect and surplus produce without needing a grade, but sets a condition defect limit based on transportation time. |
| **To have** | Cold storage space, dock staff, volunteers to sort, and enough time to distribute before spoilage |
| **Handling rules** | Separate storage by temperature type. Product on mixed pallets is discarded as a safety precaution. |
| **Transport rules** | Refrigerated vehicles or approved passive temperature control devices to transport perishable donations. |
| **To be paid or covered** | Often can only cover part of the logistics cost |
| **Will refuse if** | No cold space, load is too large to distribute before it spoils, already too much of that crop, or quality is below threshold |

A key detail: accepting a load isn't all-or-nothing. A food bank might take half a truckload, which lets agents split loads among food banks.

**Food bank agent inputs:** cold storage capacity, current inventory by category, distribution rate, Map the Meal Gap need for its service area, nutrition gaps.  
**Food bank agent outputs:** an acceptance with quantity, latest arrival time, cost contribution, or a refusal with a reason.

### 5. Partner pantries and meal programs (downstream of food banks)

| Need | Details |
|---|---|
| **Smaller quantities** | Many programs and agencies can't handle full pallets of produce. |
| **Food their clients will use** | Rising demand for no-cook, ready-to-eat food, especially among people in shelters, vehicles, or temporary housing. Persistent gaps in proteins, dairy, shelf-stable goods, and culturally relevant items. |
| **Will refuse if** | The food can't be stored or isn't something their clients can prepare |

Model these as demand signals into the food bank agent's Level 1 sub-team, not as negotiating agents.

### 6. Food safety reviewer (human in the loop)

| Need | Details |
|---|---|
| **To know** | Temperature history during transport, time out of refrigeration, and condition at pickup |
| **Thresholds** | For cut produce, storage at 41°F or below. Whole produce varies by type. |
| **Decision** | Accept, reject, or accept partially after culling |
| **Escalation trigger** | Any temperature excursion, visible quality problem, or uncertain cold chain record |

This is your clearest human escalation point. Agents should never decide on their own whether questionable food is safe to accept.

### 7. Intermediaries (Farmlink, California Association of Food Banks' Farm to Family program)

| Need | Details |
|---|---|
| **Visibility** | Which farms have surplus and which food banks have capacity, without making dozens of phone calls |
| **A record** | Who received what, so they can report impact to funders |
| **Control** | The ability to override or approve deals |

Include them as an optional observer and approver agent, or as the human user of your dashboard.

### 8. Food-insecure people (represented by your equity agent)

| Need | Details |
|---|---|
| **Fair distribution** | Food reaching high-need areas, not just areas near the farm or with the biggest food bank |
| **Usable food** | Food they can cook given their housing situation and culture |
| **Reliability** | Steady supply rather than random large loads |

**Equity agent inputs:** Map the Meal Gap rates, Food Access Research Atlas data, and a record of past distribution. It pushes back when the same areas keep winning loads.

### Information flow between stakeholders

| From | To | Message |
|---|---|---|
| Grower | Food banks, logistics | Surplus offer: crop, volume, location, ready-by date, cost recovery needed |
| Food banks | Grower | Bid: quantity accepted, cost share, latest arrival time |
| Logistics | All | Quote: price, availability, temperature capability |
| Labor | Grower | Crew availability and cost |
| Equity agent | Food banks | Fairness objections or support, with need data |
| Any agent | Food safety reviewer | Escalation for quality or temperature issues |
| Food bank | Grower | Donation receipt for tax credit |

---

## Message 19 — User

**User:** if each stakeholder is a multi agent system, how would each work system work??? and how would they interact with them

---

## Message 20 — Claude: Multi-Agent System Architecture

*(Includes interactive architecture diagram.)*

Every organization runs the same loop. An event arrives, the negotiator asks its specialists for an assessment, the specialists answer with numbers, the negotiator combines them into a position, and a human approves anything binding. This is a supervisor pattern — the same structure coffeeAGNTCY uses — where a supervisor agent directs worker agents. You can build each organization as one LangGraph graph.

### How each internal system works

**Grower system.** When AMS prices drop or a field passes its market window, the *surplus agent* estimates harvestable volume and how many days remain before spoilage. The *market agent* compares today's shipping-point price with the processor's offer. The *cost agent* adds up harvest, packing, and hauling costs and subtracts the 15% tax credit. The negotiator takes the cheapest walk-away option (processor, compost, or tilling under) and sets a minimum cost recovery. It will only accept donation deals that beat that number. The grower approves the final deal.

**Food bank system.** When an offer arrives, the *storage agent* checks free cold space by temperature zone. The *demand agent* checks how fast it's distributing this crop and what partner pantries have requested. The *nutrition agent* scores the offer against current gaps. The negotiator turns that into a bid: "We can take 6,000 of the 20,000 pounds, arriving by Thursday at 2 p.m., and contribute $300." The operations manager approves anything over a set size.

**Logistics system.** The *fleet agent* knows which trucks have working refrigeration. The *routing agent* calculates drive times with OSRM. The *pricing agent* calculates cost per trip, including the empty return. The dispatcher sends quotes and reports disruptions.

**Harvest crew system.** The *crews agent* tracks who's available. The *no-show agent* estimates how many volunteers will actually show up. The *heat risk agent* checks the National Weather Service forecast and can block a shift. The coordinator quotes headcount and cost.

**Shared agents.** The *equity agent* isn't owned by any organization. It reads Map the Meal Gap data and the deal ledger and objects when allocations keep favoring the same areas. *Safety review* is a checker agent with a human reviewer behind it.

### How the systems interact (6-phase negotiation)

1. **Announce.** The grower negotiator publishes a surplus offer to the network. Organizations find each other through the AGNTCY directory by capability tags.
2. **Assess privately.** Each food bank, trucker, and crew runs its internal loop. No private data leaves an organization; only the result does.
3. **Bid and quote.** Food banks send partial-quantity bids, truckers send quotes, and crews send availability. Every message carries a deadline.
4. **Negotiate.** Any negotiator can propose a *deal bundle* — a complete plan saying who takes how much, which truck, which crew, and who pays what. The others accept, reject, or counter. The equity agent can attach an objection backed by need data. A bundle becomes binding only when every party named in it accepts.
5. **Reserve, then confirm.** Two-step commit: first, each party tentatively holds its resource. Then each human approver confirms. If anyone fails to confirm, all holds are released and negotiation reopens.
6. **Execute and monitor.** The truck reports temperatures. On arrival, the food bank sends a receipt to the grower for tax credit. The deal is recorded in the ledger.

### What happens when something breaks (Level 2)

Say the refrigeration unit in the assigned truck fails. The fleet agent detects it, and the dispatcher broadcasts a disruption notice. Only the affected part of the deal reopens. The grower's offer and the food bank's acceptance stay in place, and the transport slot goes back to bidding. Other truckers discovered through the directory can bid. If no refrigerated truck is available before the spoilage deadline, the system recalculates: a closer food bank that doesn't need a long refrigerated trip may now be the better destination.

### When the system stops (Level 3 stopping rules)

- **Deal reached:** every party accepts, and the deal goes to human confirmation.
- **Keep the disagreement:** if the equity agent and the food banks still disagree after a set number of rounds, the system shows the coordinator the top two bundles with each side's reasoning.
- **Ask a human:** for any food safety uncertainty, or when the best bundle doesn't cover the grower's minimum cost.
- **Deadline fallback:** when spoilage time is nearly up, the system takes the best available bundle, or routes the produce to compost or animal feed and records it as a loss.

### Mapping to code

| Piece | Implementation |
|---|---|
| Each organization | Its own service or container with a LangGraph supervisor graph |
| Specialists | Tools or sub-agents calling NASS, AMS, OSRM, NWS, and simulated inventory |
| Negotiator to negotiator | A2A messages over the AGNTCY transport |
| Discovery | Directory records listing each organization's capabilities and region |
| Message types | `SurplusOffer`, `Bid`, `Quote`, `DealProposal`, `Accept`/`Reject`/`Counter`, `Hold`, `Confirm`, `Disruption`, `Objection`, `Receipt` |
| Human approval | A simple approve or reject button in your dashboard |
| Baselines | First-come-first-served and nearest-food-bank rules, run on the same scripted scenario |

---

## Message 21 — User (shared ChatGPT response)

**User shared the following ChatGPT-generated architecture document:**

> # HarvestNet Architecture: Multi-Agent Systems Negotiating With Other Multi-Agent Systems
>
> I would design HarvestNet as a **network of independent multi-agent organizations**, rather than one large multi-agent system controlling everything.
>
> [Full architecture document as shared — covering organization-level MAS design, Farm MAS, Food Bank MAS, Logistics MAS, Community Advocacy MAS, Harvest Crew MAS, communication technology stack (LangGraph + A2A + AGNTCY SLIM + MCP), full negotiation scenario with 10,000 lbs of tomatoes, distributed consensus protocol, commitment mechanism, and implementation structure.]

**User:** Chatgpt gave me this for your answer to "if each stakeholder is a multi agent system, how would each work system work ??? and how would they interact with them"

---

## Message 22 — Claude: Analysis of ChatGPT's Response — What to Keep, Fix, and Add

It's a good critique, and most of it improves the design. Three of its points correct real mistakes in my answer, a few need adjusting, and there's one gap neither of us covered.

### Where ChatGPT is right about my mistakes

**Deadline fallback.** I wrote that when spoilage time runs out, the system "takes the best available bundle." That was wrong, because it would commit organizations without their approval and undermine the whole design. The correct rule: if no approved bundle exists by the deadline, the system recommends an alternative (processor, compost, or another food bank) and escalates to a human. It never commits on anyone's behalf.

**Agreements after a disruption.** I said the grower's offer and the food bank's acceptance "stay in place" when the truck fails. That's only true if the replacement still meets the original terms. A food bank that agreed to 4,000 pounds by noon Thursday hasn't agreed to Friday evening. Every acceptance should include its conditions, and any change that breaks a condition sends that party back to re-approve.

**Hardcoding the tax credit.** I wrote that the cost agent "subtracts the 15% tax credit." It should be a configurable incentive policy with a documented source and eligibility rules.

### Where I'd adjust ChatGPT's suggestions

| Suggestion | My adjustment |
|---|---|
| Tax credit defaults to zero | For a simulated California scenario, default to the documented California rate, marked clearly as an assumption, and include a sensitivity run with zero. |
| Richer negotiation (challenges, withdrawals, conditional concessions) | Yes, but keep it to a small, fixed set of message types. Conditions should be structured fields like `deliver_by` and `max_qty` that the validator can check, not free text. |
| Conditional offers involving third parties | Food Bank A saying "if Logistics B delivers before Thursday and the rest goes to Food Bank C" commits other organizations. That has to be a bundle proposal that B and C must accept, not a unilateral concession. |
| Equity agent can't force anything | Agreed. Treat the fairness charter as an optional configuration and test both versions. |
| Build autonomy first, add AGNTCY later | Risky. Late integration is where hackathon projects break. Put the transport behind a thin interface from day one. |

### ChatGPT's crop choice is wrong: tomatoes are not cold-chain dependent

This matters most for the demo. Tomatoes are chilling-sensitive — storing them at standard refrigerated temperatures damages them. A judge who knows produce could reasonably ask why a broken refrigerated truck matters for tomatoes.

**Fix:** Use strawberries, leafy greens, or broccoli. Strawberries work especially well because they spoil within days, so a refrigeration failure creates real urgency.

### The money in the scenario doesn't add up

- The farm needs $450, transport costs $350, and the food banks offer $300 total — a $500 gap that's never resolved.
- The $350 processor alternative is ruled out because the processor can't pick up in time, so the real fallback is tilling under for $0.
- The harvest crew's $300 quote and the farm's $300 harvest cost appear to be the same money.

### 3,000 pounds disappear

The final agreement allocates 7,000 of the 10,000 pounds. The leftover 3,000 should visibly go somewhere.

### Improvements to the commitment state machine

ChatGPT's states are good. Three additions:

- **Bind acceptances to a specific version.** Each acceptance should reference `proposal_id`, a version number, and a hash of the terms. Changing any term creates a new version, and old acceptances don't apply to it.
- **Set hold expiry to match human response time.** Holds are placed before `PENDING_APPROVAL`, so their time limit must be longer than a realistic human approval window. Add `EXPIRED` and `REJECTED` as terminal states alongside `ABORTED`.
- **Allow partial completion.** If one of two deliveries finishes, record it as done instead of aborting the whole bundle.

Full recommended state machine:

| State | Meaning |
|---|---|
| `PROPOSED` | Bundle submitted for consideration |
| `VALIDATED` | Deterministic checks pass |
| `PREPARED` | Required participants have placed temporary holds |
| `PENDING_APPROVAL` | Awaiting authorized human approval |
| `COMMITTED` | Every required participant has confirmed |
| `EXECUTING` | Simulated delivery is underway |
| `COMPLETED` | Receipt and delivery verification recorded |
| `ABORTED` | Agreement canceled and holds released |
| `EXPIRED` | Hold time limit exceeded |
| `REJECTED` | Human approver declined |

### The gap neither of us covered: concurrent proposals

With no central coordinator, two organizations can propose bundles at the same moment that both use the same truck or cold storage space.

- **Holds work as locks.** A bundle can reach `PREPARED` only if every resource hold succeeds.
- **Limit proposals per party.** Each organization can have one active proposal per surplus event.
- **Order events consistently.** Timestamp every message and process them in a fixed order, so replays produce the same outcome.

### A stronger experiment design

Run the same seeded scenario under:
- A 2×2 grid: equity agent on or off, crossed with disruption on or off.
- Two reference baselines: first-come-first-served and a centralized optimizer as the upper bound.
- Multiple seeds (10–20 random variations), reporting averages with ranges.

### Suggested revised demo scenario

| Stakeholder | Situation (all values simulated) |
|---|---|
| Farm A | 10,000 lb **strawberries**, 48-hour window. Fallback is till-under. Minimum is recovery cost minus the tax credit. |
| Food Bank A | Urban, wants 6,000 lb, cold space for 4,500, volunteer shift fixed Thursday morning |
| Food Bank B | Rural, higher modeled need, cold space for 4,000, smaller budget |
| Logistics A | One reefer, 7,000 lb. Fails mid-negotiation. |
| Logistics B / C | Found through discovery after the failure |
| Harvest crew | 6,000 lb per shift. A second shift costs extra, and the heat forecast limits hours. |
| Community advocate | Enforces the pre-agreed fairness charter and argues with Meal Gap data |

### The codebase

ChatGPT's structure is sensible. Two changes would help:
- Make each organization runnable as its own process, so autonomy is real and not just separate folders.
- Put all message schemas in one shared package (`protocols/messages.py`, using Pydantic) that every organization imports, so formats can't drift.

### What to build first

Build the message schemas, validator, and commitment state machine first, before any LLM is involved. If you can run a full negotiation with simple rule-based agents — including a truck failure and two conflicting bundles — then adding LLM negotiators, real data, and the dashboard becomes much easier.

---

## Key Decisions Summary

| Decision | Choice | Reason |
|---|---|---|
| Domain | Farm surplus → food banks | Genuine supply chain, no central coordinator, maps to coffeeAGNTCY |
| Demo crop | Strawberries | Actually cold-chain dependent; creates real urgency when reefer fails |
| Architecture | Organizations as separate LangGraph instances, A2A between them | Organizational autonomy is real, not just code folders |
| Communication | AGNTCY SLIM for group, A2A for direct, from day one | Late integration breaks hackathon projects |
| Data | USDA NASS, AMS Market News, Feeding America Meal Gap, OpenStreetMap, OSRM, NWS | All free/open |
| Baselines | First-come-first-served, nearest food bank, centralized optimizer | 2×2 experiment grid to isolate equity agent and disruption effects |
| Stopping rules | Rounds limit, spoilage deadline, human escalation — never auto-commit | System never commits on anyone's behalf |
| Concurrency | Holds as locks, one active proposal per party per event, timestamped messages | Prevents conflicting agreements without a coordinator |
| Build order | Pydantic schemas → state machine → rule-based agents → LLM agents → dashboard | Each step testable before the next |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Internal orchestration | LangGraph |
| Inter-organization messaging | A2A protocol |
| Group communication | AGNTCY SLIM |
| Discovery | AGNTCY Directory |
| External tools | MCP / HTTP APIs |
| Observability | OpenTelemetry / AGNTCY Observe SDK |
| Message validation | Pydantic |
| Routing | OSRM (open source) |
| Weather | National Weather Service API |
| Agricultural data | USDA NASS QuickStats API, USDA AMS Market News API |
| Food need data | Feeding America Map the Meal Gap |
| Food bank locations | OpenStreetMap Overpass API |
| Frontend | React dashboard (two-panel: internal agent view + negotiation timeline) |

---

## Recommended Codebase Structure

```
harvestnet/
│
├── organizations/
│   ├── grower/
│   │   ├── graph.py
│   │   ├── specialists.py      # surplus, market, cost, harvest agents
│   │   ├── negotiator.py
│   │   └── policies.py         # configurable incentive policy (tax credit etc)
│   │
│   ├── food_bank/
│   │   ├── graph.py
│   │   ├── specialists.py      # demand, storage, nutrition, budget, distribution agents
│   │   ├── negotiator.py
│   │   └── policies.py
│   │
│   ├── logistics/
│   │   ├── graph.py
│   │   ├── specialists.py      # routing, fleet, pricing, risk agents
│   │   ├── negotiator.py
│   │   └── policies.py
│   │
│   ├── harvest_crew/
│   │   ├── graph.py
│   │   ├── specialists.py      # crews, no-show prediction, heat risk agents
│   │   ├── negotiator.py
│   │   └── policies.py
│   │
│   └── community_advocate/
│       ├── graph.py
│       ├── specialists.py      # food access, food insecurity, equity, impact agents
│       ├── advocate.py         # proposes alternative bundles, challenges allocations
│       └── charter.py          # configurable fairness constraints
│
├── protocols/
│   ├── messages.py             # ALL Pydantic schemas shared by every organization
│   ├── negotiation.py          # negotiation session management
│   ├── commitments.py          # state machine: PROPOSED → VALIDATED → PREPARED → ...
│   └── validation.py           # deterministic checks on quantities, costs, safety
│
├── network/
│   ├── discovery.py            # AGNTCY Directory capability-based lookup
│   ├── a2a_gateway.py          # external A2A endpoint per organization
│   └── messaging.py            # SLIM group communication
│
├── tools/
│   ├── usda_nass.py            # NASS QuickStats API
│   ├── usda_ams.py             # AMS Market News API
│   ├── routing.py              # OSRM drive time calculations
│   ├── weather.py              # National Weather Service API
│   └── food_access.py          # Feeding America + USDA Food Access Atlas
│
├── simulation/
│   ├── scenarios.py            # seeded, repeatable surplus events
│   ├── disruptions.py          # scripted truck failure, heat wave, new food bank
│   └── environment.py          # synthetic farm/food bank data from real calibration
│
├── evaluation/
│   ├── baselines.py            # first-come-first-served, nearest, centralized optimizer
│   ├── metrics.py              # pounds delivered, unmet demand, cost, fairness (Gini), latency
│   └── experiments.py          # 2×2 grid: equity on/off × disruption on/off, multiple seeds
│
└── frontend/
    ├── views/
    │   ├── InternalView.jsx    # click org → see specialist agents reasoning
    │   └── NegotiationView.jsx # timeline of offers, counteroffers, evidence, status
    └── dashboard/
        └── MetricsPanel.jsx    # live baseline comparison
```

---

## Message Types (Protocol Schemas)

```python
# All Pydantic schemas in protocols/messages.py

class SurplusOffer(BaseModel):
    offer_id: str
    farm_id: str
    crop: str
    quantity_lbs: float
    location: str
    ready_by: datetime
    spoilage_deadline: datetime
    min_cost_recovery_usd: float
    packaging: str            # "palletized_cartons" | "bins" | "loose"
    conditions: dict          # any constraints the farm requires

class Bid(BaseModel):
    bid_id: str
    offer_id: str
    food_bank_id: str
    quantity_lbs: float
    max_arrival_time: datetime
    cost_contribution_usd: float
    conditions: dict

class Quote(BaseModel):
    quote_id: str
    logistics_id: str
    pickup_location: str
    delivery_locations: list[str]
    total_lbs: float
    price_usd: float
    earliest_pickup: datetime
    temperature_capability: str

class DealProposal(BaseModel):
    proposal_id: str
    version: int
    terms_hash: str
    farm_id: str
    deliveries: list[DeliveryLeg]
    cost_allocation: dict[str, float]
    status: str               # PROPOSED | VALIDATED | PREPARED | ...
    required_approvals: list[str]
    hold_expires_at: datetime

class DeliveryLeg(BaseModel):
    recipient_id: str
    quantity_lbs: float
    logistics_id: str
    pickup_time: datetime
    delivery_deadline: datetime

class Acceptance(BaseModel):
    proposal_id: str
    proposal_version: int
    terms_hash: str           # must match — old acceptances don't carry over
    organization_id: str
    conditions_met: bool
    conditions_violated: list[str]

class Disruption(BaseModel):
    disruption_id: str
    affected_resource_id: str
    resource_type: str        # "truck" | "storage" | "crew"
    affected_proposals: list[str]
    available_again_at: datetime | None

class EquityObjection(BaseModel):
    proposal_id: str
    objecting_to: str         # organization or allocation
    need_data: dict           # meal gap rates, historical allocations
    alternative_proposal_id: str | None

class DonationReceipt(BaseModel):
    receipt_id: str
    proposal_id: str
    farm_id: str
    food_bank_id: str
    quantity_lbs: float
    crop: str
    qualified_value_usd: float
    donation_date: date
    authorized_by: str
```

---

## Judging Criteria Mapping

| Criterion | What to demonstrate |
|---|---|
| **Functionality** | End-to-end food rescue with independently confirmed commitments, from surplus announcement to donation receipt |
| **Innovation** | Negotiation between independently operated multi-agent organizations, with equity representation |
| **Agent intelligence** | Internal reasoning (specialists disagree), evidence-based negotiation, conditional concessions, adaptation after disruption |
| **Engineering** | Typed Pydantic messages, state machine with expiring holds, versioned proposals, auditable negotiation log, observable with OpenTelemetry |
| **Demonstration** | Two-panel dashboard: click any org to see internal agents, watch negotiation timeline, see truck failure trigger rediscovery |
| **Learning and evidence** | 2×2 experiment: equity on/off × disruption on/off, across multiple seeds, compared against baselines |

---

## The Strongest Demo Moment

**Truck failure sequence (live in front of judges):**

1. Negotiation is proceeding normally — Food Bank A bids 4,500 lb, Food Bank B bids 3,000 lb, Logistics A quotes for the combined load.
2. Logistics A's fleet agent detects a refrigeration failure and broadcasts a `Disruption` message.
3. Judges watch the logistics organization retract its quote and the deal revert to `PROPOSED`.
4. The AGNTCY directory is queried with `"refrigerated_transport"` capability — Logistics B and C are discovered.
5. Food Bank A's storage agent recalculates: with a different truck, can it still meet Thursday? Yes, but only if pickup is before 2 p.m.
6. A new bundle is assembled, proposed, and approved by all parties in two more rounds.
7. The equity agent notes that the reallocation still satisfies the fairness charter.
8. Dashboard shows: 8,500 lb saved, 1,500 lb to compost, all costs covered, both baselines shown for comparison.

---

*End of conversation transcript*
*Generated: October 2026 for HarvestNet Claude Code session setup*
