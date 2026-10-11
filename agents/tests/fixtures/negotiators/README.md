# Negotiator fixtures

Synthetic. Each file is one recorded negotiator input with its expected move, used by
`tests/test_rules_negotiators.py` (#11) and, later, the LLM negotiator tests (#13). They
stand in for contract day's example input/output pairs, since ticket #1 isn't done.

- `role`: `donor`, `food_bank`, or `advocate`.
- `draft`: one draft-agreement version for a farmers market's mixed lot (300 lb apples,
  200 lb romaine, 400 lb potatoes, gone by 3 pm), following Workflow 2 in
  `docs/MVP_DESIGN.md`.
- `facts`: that organization's own specialists' facts, nobody else's.
- `turn`: whose turn it is, the time, and who has accepted this version so far.
- `expected`: the move kind, the exact amendment or holds, and words its reason must
  contain.

All numbers, times, and organizations are synthetic. The file name says what it checks.
