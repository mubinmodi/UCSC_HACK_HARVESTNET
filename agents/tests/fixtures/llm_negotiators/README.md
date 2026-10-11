# LLM negotiator fixtures

Synthetic. Each file is a hand-written stand-in for the Claude responses to one negotiator
input, replayed by `tests/test_llm_negotiators.py` (#13) through an injected client. **None was
captured from a live Claude call**, so tests spend no credit. Usage numbers are synthetic.

- `input`: the recorded input in `../negotiators/` (the same inputs the rules-based tests use).
  `input_overrides` adds to it, e.g. a message from another organization.
- `responses`: the model's turns in order: content blocks (thinking, calculator `tool_use`, and
  `submit_move`), `stop_reason`, `model`, and `usage`.
- `differs_from_rules`: why this recorded move differs from the rules-based move, when it does.
- `expected`: the expected move or outcome, when it isn't the rules-based fixture's.

Some responses are wrong on purpose (invented numbers, arithmetic, an advocate trying to vote, a
model following an injected message, a refusal) to test that the deterministic checks catch them.
