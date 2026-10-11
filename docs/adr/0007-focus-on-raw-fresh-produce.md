# Focus on raw fresh produce, not cooked meals

October 10, 2026, decided by the user: "it's not about cooked meals, it's about raw food produce. I don't want food produce waste." This refines ADR 0006. HarvestNet's purpose is to stop fresh fruit and vegetables from going to waste by getting surplus produce to low-income households and people experiencing homelessness through distribution sites.

## Decision

- **Food in scope:** raw fresh produce, whole or packed. Cooked or prepared meals are deferred.
- **Donors:** any produce source, such as farms, packers, distributors, grocers, farmers markets, and food banks with produce overflow. Field gleaning and harvest economics stay deferred (ADR 0006).
- **Matching by produce profile:** each profile records whether the item can be eaten raw or needs cooking, whether it needs a fridge, how long it lasts cold and at room temperature, and its transport temperature (ADR 0003). Requests record whether the person has a kitchen and a fridge.

## Consequences

- A surplus lot is usually mixed, so draft agreements split it item by item.
- The fairness rule matches produce to people's kitchen and fridge access. Prepared-meal holding checks are no longer needed.
- Produce safety relies on donor condition grades, recall checks, a known cold chain for cold-dependent items, and a human check for anything uncertain.
- Waste is tracked per item: every pound ends as picked up, released to another request, unclaimed, or declined, each with a reason.
- Whether "produce wasted" becomes a headline measure alongside worst-served coverage is proposed, not yet decided.
