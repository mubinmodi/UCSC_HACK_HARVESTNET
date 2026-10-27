import pytest


@pytest.fixture(autouse=True)
def isolated_spend_ledger(tmp_path, monkeypatch):
    """No test reads or writes the real spend ledger (runtime/claude-spend.json), or inherits a total cap."""
    monkeypatch.setenv("CLAUDE_SPEND_LEDGER", str(tmp_path / "claude-spend.json"))
    monkeypatch.delenv("CLAUDE_TOTAL_CAP_USD", raising=False)
