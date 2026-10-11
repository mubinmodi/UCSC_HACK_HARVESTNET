# Front-desk fixtures

Synthetic. Each file is one recorded intake used by `tests/test_front_desk.py`:

- `transcript`: the language and turns of a synthetic voice-line call (no real household).
- `extractor_output`: a hand-written stand-in for what the Claude extractor returns, in its
  schema (`EXTRACTION_SCHEMA`). It was **not** captured from a live Claude call, so tests spend
  no credit. Some outputs are deliberately wrong (invented or uncounted values) to test that
  the deterministic layer drops them.
- `expected_draft`: the draft request the deterministic layer must produce.
