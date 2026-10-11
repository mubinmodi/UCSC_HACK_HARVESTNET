# Lane B: agents

Python package `harvestnet_agents` for Lane B tickets (#11–#15). Interfaces are **proposed** until ticket #1 (contract day) agrees them; each module says which shapes it assumes.

```bash
cd agents
uv run pytest              # all tests
uv run pytest tests/test_profiles.py::test_name   # one test
uv sync --extra claude     # only for the live ClaudeExtractor in front_desk.py (needs an API key)
```

## Modules

- `front_desk.py` (#14): front-desk assistant. Claude only extracts fields from a transcript; deterministic code checks them against the household's own words, marks missing fields, and builds the read-back, consent, and pickup wording (committed produce only), in English and Spanish. Tests replay recorded extractor outputs from `tests/fixtures/front_desk/` and never call the API.
