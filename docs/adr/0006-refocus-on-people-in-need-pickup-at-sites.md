# Refocus on people in need, with pickup at distribution sites and no money

October 10, 2026, decided by the user. The earlier whole-chain design (farm harvest economics, a rescue fund, cross-dock, processor, and cross-event funding) was judged about a year of work. HarvestNet's purpose is now narrower: get surplus food from any food organization to low-income households and people experiencing homelessness. The general architecture stays: the organization template, food profiles, draft agreements, holds, approvals, stop rules, guardrails, no central decider (ADR 0001), and calculators instead of invented numbers (ADR 0002).

## Decision

- **Participants:** donors (any food organization), distribution sites (shelters, pantries, community fridges), volunteer drivers, an advocate agent for people's combined requests, and people in need.
- **People interact directly** through a simple mobile web page and an ElevenLabs voice line, for people without smartphones or data. Text alerts go out through n8n. No app, no account, no name.
- **Food reaches people by pickup at distribution sites.** No home delivery, so no home addresses are collected.
- **No money in the current scope.** Food is donated and drivers are volunteers. The rescue fund is deferred.

## Consequences

- The headline measure becomes people actually served (pickup confirmations), plus worst-served coverage, compared against first-come-first-served.
- Food profiles must record whether food is ready to eat or needs a kitchen, matched against each request.
- Data from people in need stays minimal: rough area, household size, kitchen access, and dietary needs, with consent. Prepared food needs food-safety checks before it's offered.
- The farm, cross-dock, processor, and fund remain profile-ready roles on the network map, not built features.
