# Lane B: agents

Python package `harvestnet_agents` for Lane B tickets (#11–#15). Interfaces are **proposed** until ticket #1 (contract day) agrees them; each module says which shapes it assumes.

```bash
cd agents
uv run pytest              # all tests
uv run pytest tests/test_profiles.py::test_name   # one test
uv sync --extra claude     # only for the live ClaudeExtractor in front_desk.py (needs an API key)
```

## Module map

- `profiles.py`: produce profiles (#12). `load_profiles()` reads `data/produce_profiles.json` and rejects any field that is neither sourced nor labeled an assumption. `to_pounds()` converts units, using a donor-stated pack weight where the profile holds none.
- `fair_share.py`: the fair-share table (#12). `fair_share(household_size)` reads `data/fair_share_table.json`, a versioned **placeholder** (synthetic numbers from the design).
- `cooler_failure.py`: cooler-failure decision logic (#15). `assess_cooler_failure(failure, candidates)` marks items to move from their profiles, writes a reason card for every candidate, and proposes a draft version awaiting the receiving food bank's own decision (or a same-day offer or unclaimed outcome). `parse_scenario()` loads recorded scenarios like those in `tests/fixtures/cooler_failure/`.
- `negotiation.py`: the **proposed** agent move interface (#11). A negotiator gets an `AgentInput` (a `DraftVersion`, its own specialists' facts, and its `Turn`) and returns one `Move`: accept, counter with one amendment (`SetPounds`, `ShiftPounds`, or `SetTransport`), reject, request a hold on its own resources, ask its human, or pass. `Move` refuses an advocate accept, reject, hold, or ask-a-human, a counter without exactly one amendment, and any move without a reason; no move ever commits. `Move.to_dict()` matches Lane C's proposed wire shape. `parse_agent_input()` loads recorded inputs.
- `calculators.py`: the **proposed** calculator interface (`Calculators`) and `StandInCalculators`, stand-ins until Lane A's (#8): fair-share gap, gap after a plan, storage over time, capacity fit, pickup-window feasibility, arrival time, and unit conversion. Every call is logged.
- `rules_negotiators.py`: rules-based donor, food bank, and advocate negotiators (#11). `rules_negotiator(role, organization_id)` builds one. Tests replay the recorded inputs in `tests/fixtures/negotiators/`.
- `front_desk.py`: front-desk assistant (#14). Claude only extracts fields from a transcript; deterministic code checks them against the household's own words, marks missing fields, and builds the read-back, consent, and pickup wording (committed produce only), in English and Spanish. Tests replay recorded extractor outputs from `tests/fixtures/front_desk/` and never call the API.
