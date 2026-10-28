# Claim-to-evidence matrix

| Claim | Evidence | Classification | Limitation |
|---|---|---|---|
| The rules-based Organizations contest shares and negotiate versioned terms | `rules-evaluation.json`, `rules-replays/` | Synthetic, measured locally | Deterministic policies on five fixtures |
| Claude negotiators execute against the real calculators | `claude-run-evidence.json`, `claude-replays/` | Synthetic, measured locally, paid | One repetition; four of five method results are partial |
| Claude agents can preserve a disagreement without an automatic commitment | `claude-replays/condition-doubt-llm-0.json` | Synthetic, measured locally, paid | One scenario; no deployed A2A transport |
| The run stayed inside the approved Claude caps | `claude-spend-ledger.json`, `SHA256SUMS` | Locally verified ledger evidence | Ledger started at zero for this candidate run; not an AWS ledger |
| Rules improve fairness under scarcity | `rules-summary.json`, scenario `more-households-than-produce` | Synthetic, measured locally | Small curated fixture set |
| Rules beat FCFS on waste in the normal scenario | `rules-summary.json`, scenario `normal-afternoon` | Synthetic, measured locally | Rules tie the nearest-food-bank method |
| Every evaluated method produced zero invalid commitments | Both evaluation summaries and per-run rule checks | Synthetic, measured locally | Does not prove production availability |
| Live moves come from each Organization host over signed A2A | Merged code and automated tests | Candidate code evidence | A deployed Surplus lot has not yet been captured |
| The AGNTCY Directory supports cooler-failure discovery | Automated tests and replay | Synthetic local integration | AWS Directory evidence pending |
| Staff approvals bind to the exact version | Automated core and platform tests | Synthetic local integration | Live approval and stale-link capture pending |
| The complete demo works in under three minutes | None yet | Unverified | Requires deployed rehearsal and continuous recording |

## Claims this bundle does not support

- Claude beats the rules-based or nearest-food-bank methods.
- Food was distributed to real households.
- The AWS deployment is currently healthy.
- Every paid run will reproduce the same negotiation.
- A fallback-heavy result is equivalent to a completed Claude result.
