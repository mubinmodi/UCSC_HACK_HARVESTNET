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
- `front_desk.py`: front-desk assistant (#14). Claude only extracts fields from a transcript; deterministic code checks them against the household's own words, marks missing fields, and builds the read-back, consent, and pickup wording (committed produce only), in English and Spanish. Tests replay recorded extractor outputs from `tests/fixtures/front_desk/` and never call the API.
