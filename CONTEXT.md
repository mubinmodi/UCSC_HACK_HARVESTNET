# HarvestNet

A network that stops fresh fruit and vegetables from going to waste by getting surplus produce from any food organization to low-income households, who collect it at food banks they choose. Donors and food banks each have their own agent and negotiate how each surplus lot is shared. No one in the middle decides for anyone else.

## Participants

**Organization**:
An independent participant that controls its own resources and approves its own commitments. Examples: a produce donor or a food bank.
_Avoid_: Agent (when meaning the whole participant), node, party, stakeholder

**Specialist**:
A helper inside one organization that checks one thing, such as cost, storage, route, or harvest capacity. Numbers come from calculators, not from guesses.
_Avoid_: Sub-agent, worker

**Negotiator**:
An organization's representative that talks to other organizations, proposes changes to deals, and explains its organization's decisions.
_Avoid_: Supervisor, gateway, dispatcher

**Coordinator**:
Removed from the MVP (ADR 0009). Disagreements and approvals appear on the dashboards of the donors and food banks involved.
_Avoid_: Admin, operator, manager, allocator

**Person in need**:
A member of a low-income household who asks for produce for the household and picks it up at a food bank. Identified only by a request, never by name.
_Avoid_: Client, beneficiary, end user, recipient (when meaning a person)

**Donor**:
An organization with surplus produce to give, such as a farm, packer, distributor, grocer, farmers market, or food bank with produce overflow.
_Avoid_: Supplier, source, vendor

**Food bank**:
The only kind of pickup site in the MVP: a place where households collect produce, with its own storage, pickup hours, truck, and agent. Households choose which food banks they use.
_Avoid_: Distribution site, pantry (when meaning the HarvestNet role), outlet, drop point

**Fair share**:
A household's weekly produce amount, set by household size from a table the participating food banks publish, like a SNAP benefit. It's the yardstick for fairness, not an allocation.
_Avoid_: Ration, quota, allowance, entitlement

**Rescue fund**:
Deferred, not in the current scope (decided October 10, 2026). An organization that owns grant money and spends it by a published rule.
_Avoid_: Funder pot, budget, sponsor

**Advocate**:
A participant that speaks for least-served communities with evidence and proposals. It has no veto.
_Avoid_: Equity agent, fairness checker, validator

## Food and outcomes

**Surplus lot**:
A specific batch of at-risk food, such as 10,000 lb of strawberries in one field.
_Avoid_: Load, donation, shipment, inventory

**Food profile**:
A reviewed description of a food at the required specificity, including maturity or processing state: handling requirements, quality/storage targets, chilling sensitivity, usable-life assumptions, packaging units, compatibility, quality categories, candidate pathways, and required assessments. Each field has a source or an explicit assumption and a version. Actual lot condition is separate evidence; a profile alone does not establish eligibility. The framework applies common procedures to these properties and identifies unsupported assessments.
_Avoid_: Crop type, product config, handling rules (when meaning the whole profile)

**Request**:
A household's statement of what it needs: household size, when it can pick up, whether its fridge space is limited, rough area, anything it can't eat, optionally whether it receives SNAP/CalFresh, and the food banks it chose. It carries no name.
_Avoid_: Order, application, demand

**Pickup confirmation**:
A household's reply that it will collect, or has collected, produce at a food bank. It is how HarvestNet counts households actually reached.
_Avoid_: Delivery receipt, check-in

**Event**:
One surplus lot's journey from first offer to final outcome.
_Avoid_: Transaction, order, case

**Pathway**:
Where a surplus lot's food finally ends up: donated, upcycled, animal feed, compost, or left unharvested. Each pound is counted once.
_Avoid_: Destination tier, disposition, outlet

**Coverage**:
The share of its weekly fair share a household has received. Worst-served coverage is the lowest average across food banks, declared before comparison and including zero receipts.
_Avoid_: Fairness score, fulfillment rate, equity

**First-come-first-served baseline**:
The simple comparison method: whoever claims first gets served, under the same trucks, money, and rules as HarvestNet.
_Avoid_: Greedy, naive matching

## Agreements

**Draft agreement**:
The one shared, numbered plan for an event. Organizations edit it until everyone accepts the same version.
_Avoid_: Bundle, deal proposal, contract

**Hold**:
A temporary, expiring reservation of a resource (truck time, cold-storage space, grant money), placed by the resource's owner.
_Avoid_: Lock, booking, claim

**Commitment**:
The final state of a draft agreement: every named organization has approved the exact same version.
_Avoid_: Deal, consensus, approval

**Preserved disagreement**:
The outcome when no version wins every named organization's approval. The coordinator sees the competing options and each organization's reasons. Nobody picks for them.
_Avoid_: Deadlock, failure, escalation (when meaning the outcome itself)
