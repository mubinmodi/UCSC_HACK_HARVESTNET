# Food banks may contest each other's shares

October 27, 2026, decided by the lead after an adversarial review found that food banks never really disagreed. Each food bank could change only its own line, so whoever bid first kept the produce, and the advocate passed every turn because nothing above a gap was left to move. The review called it "an ordered greedy fill with a negotiation log." This narrows how food banks bid; it does not change ADR 0001.

**Amended the same day (October 27, 2026), by the lead's decision: concede toward need.** The first implementation kept every standoff. Under scarcity, every food bank holds only pounds within its own gap, so each contest met a take-back of the same pounds, the terms repeated, and the lot ended as a preserved disagreement that nothing resolves. In the synthetic more-households-than-produce scenario, produce wasted went from 0 to 52 lb and households reached from 4 to 0. The lead replaced "a standoff is kept, not broken" with "concede toward need". The principle is **Decided**; the details below marked (Proposed) are open for review.

## Decision

- **A food bank may contest another food bank's share, and states its claim.** While its own households are below fair share and no unclaimed pounds of an item it can receive remain, its counter may move pounds of that item from another food bank's line to its own, up to its own gap. The counter carries its own fair-share gap as a structured field (`claimant_gap_lb`), from its own calculator, and its reason cites it. The gap is a count, the same kind of number the advocate already sees. The food bank never sees another food bank's facts.
- **The food bank that loses pounds concedes toward need.** On its turn it concedes pounds it holds beyond its own fair-share gap. Within its gap, it splits the pounds of that item the two food banks hold in proportion to their two gaps: its own from its facts, the contester's as stated. It takes back only enough to reach its proportional share, not its whole gap, and its reason cites both gaps and the split.
- **The contester accepts the proportional split.** Once it holds at least its proportional share of the item (to within 1e-8 lb), it does not contest that food bank's share of the item again. If the other food bank took back more than its proportional share, the contester may contest once more, down to its own proportional share.
- **The advocate takes a side but has no vote.** In a contest it backs the side holding less than its proportional share, with a counter that restores the split. When the split is proportional, it passes on that item. A low-access area breaks exact ties only.
- **A standoff is kept only when a side refuses the split.** If a negotiator (an LLM, or a staff counter) insists on more than its proportional share and the terms repeat, the lot ends as a preserved disagreement. The dashboards of the food banks involved show the competing versions and each one's reason, and their staff approvers decide.

### Details (Proposed)

- The weights are each food bank's fair-share gap this week, from its own fair-share gap calculator. They don't change during a negotiation, so the splits of one item between any two food banks agree with each other. Weights that changed as pounds of other items moved kept the three food banks in the synthetic scarce scenario adjusting each other until the deadline. Each side still never claims past its own remaining gap.
- The `proportional_split` calculator counts shares in whole pounds, each at most its gap. The pounds left after rounding down go to the largest remainders, with ties broken by food bank id. Tenths of a pound produced splits like 0.4 lb of apples, and a long tail of 0.1 lb adjustments that outlasted the donor's drop-off time in the agents runner.
- A contest takes from the largest other line of an item the food bank can receive, shortest-lived item first among equal lines.
- A contest that stated no claim can't be weighed. The food bank that lost the pounds then takes back what is within its own gap.

## Consequences

- ADR 0001 still holds. A contest is a proposal: no pounds leave a food bank's share in any commitment unless that food bank's own staff approver approves the version.
- The rule check that rejected any food bank counter touching another food bank's line now allows exactly one shape: a shift of one item from one other food bank to the proposer, no further than its own gap, stating its own gap. Setting another food bank's pounds, or shifting between two other food banks, is still refused.
- Turn order no longer decides the split on its own, so the comparison against first-come-first-served measures negotiation, not who moved first.
- A scarce lot now converges on a proportional split instead of a standoff. It takes more versions than before.
- Results must be re-measured after this change. Earlier evaluation numbers describe the old mechanism.
