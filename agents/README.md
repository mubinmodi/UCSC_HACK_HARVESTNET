# Lane B: agents

Python package `harvestnet_agents` for Lane B tickets (#11–#15). Interfaces are **proposed** until ticket #1 (contract day) agrees them; each module says which shapes it assumes.

```bash
cd agents
uv run pytest              # all tests
uv run pytest tests/test_profiles.py::test_name   # one test
```

## Module map

- `profiles.py`: produce profiles (#12). `load_profiles()` reads `data/produce_profiles.json` and rejects any field that is neither sourced nor labeled an assumption. `to_pounds()` converts units, using a donor-stated pack weight where the profile holds none.
- `fair_share.py`: the fair-share table (#12). `fair_share(household_size)` reads `data/fair_share_table.json`, a versioned **placeholder** (synthetic numbers from the design).
