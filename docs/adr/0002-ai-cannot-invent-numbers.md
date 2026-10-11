# The AI cannot invent numbers

Quantities, capacities, costs, prices, and time windows come from each organization's calculators (specialists) and data, never from an LLM. The LLM reads messy input, proposes changes to a draft agreement, and explains decisions in plain English. Every offer it produces is checked against the organization's real limits before it is sent. We chose this over letting LLM agents reason freely about numbers because an invented capacity or budget would make agreements unsafe and the results meaningless. It also makes a fair comparison possible: rule-based negotiators run on the same calculators and validator.

## Consequences

Added October 10, 2026, at the user's request ("I don't want hallucinations"). These apply to every LLM role, starting with the rescue fund's negotiator.

- **Calculators run first.** The harness computes every number a decision or explanation needs before the LLM is called, and passes the results in as labeled facts.
- **Calculator tool for anything extra.** If the LLM needs another number (for example, the pool balance left after an award), it must call a calculator tool with a strict schema. It never does arithmetic in its own text.
- **Number check on every output.** Every number in the LLM's message or explanation must match a calculator result or a sourced fact for this event version. A message with an untraceable number is not sent.
- **Fallback.** If the check fails twice, the organization sends a template sentence built only from calculator results, and the failure is logged and counted in evaluation.
- **The LLM never makes the decision the calculator owns.** The fund's ranking, award amount, and eligibility come from its policy calculation. The LLM only explains them.
