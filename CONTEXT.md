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

**Staff approver**:
A person at a donor or food bank who approves or declines that organization's commitments, always for one exact version. Nobody approves for another organization.
_Avoid_: Manager, admin, operator, reviewer

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
A specific batch of surplus produce that must move soon, followed from its first offer to its final outcome, such as one farmers market's apples, romaine and potatoes at closing time.
_Avoid_: Event, load, donation, shipment, inventory

**Produce profile**:
A reviewed, versioned description of one produce item: whether it needs a fridge or cold transport, how long it stays usable cold and at room temperature, condition grades and units. Each field cites a source or is labeled an assumption, and a lot's actual condition is separate evidence.
_Avoid_: Food profile, crop type, product config, handling rules (when meaning the whole profile)

**Request**:
A household's statement of what it needs: household size, when it can pick up, whether its fridge space is limited, rough area, anything it can't eat, optionally whether it receives SNAP/CalFresh, and the food banks it chose. It carries no name.
_Avoid_: Order, application, demand

**Pickup confirmation**:
A household's reply that it will collect, or has collected, produce at a food bank. It is how HarvestNet counts households actually reached.
_Avoid_: Delivery receipt, check-in

**Pathway**:
Where each pound of a surplus lot ends up: collected by a household, committed to a food bank that can store it and hand it out before it stops being usable, or wasted (no pathway). Each pound is counted once (ADR 0011).
_Avoid_: Destination tier, disposition, outlet

**Coverage**:
The share of its weekly fair share a household has received. Worst-served coverage is the lowest average across food banks, declared before comparison and including zero receipts.
_Avoid_: Fairness score, fulfillment rate, equity

**First-come-first-served baseline**:
The simple comparison method: the first food bank to claim an item gets all of it, under the same trucks, storage, and rules as HarvestNet.
_Avoid_: Greedy, naive matching

## Agreements

**Draft agreement**:
The one shared, numbered plan for a surplus lot. Organizations edit it until everyone accepts the same version.
_Avoid_: Bundle, deal proposal, contract

**Hold**:
A temporary, expiring reservation of a resource (truck time, cold or dry storage space), placed by the resource's owner.
_Avoid_: Lock, booking, claim

**Commitment**:
The final state of a draft agreement: every named organization has approved the exact same version.
_Avoid_: Deal, consensus, approval

**Contest**:
A food bank's counter that moves pounds of one item from another food bank's share to its own, citing its own households' fair-share gap. The other food bank answers for itself, and no pounds move in a commitment without its staff approver (ADR 0013).
_Avoid_: Claim (a hold is not a claim either), steal, override, bump

**Reason card**:
A short explanation, built only from recorded facts, of why one candidate food bank was chosen or rejected, for example after a cooler failure.
_Avoid_: Justification, score, ranking

**Preserved disagreement**:
The outcome when no version wins every named organization's approval. The dashboards of the organizations involved show the competing options and each organization's reasons. Nobody picks for them.
_Avoid_: Deadlock, failure, escalation (when meaning the outcome itself)
