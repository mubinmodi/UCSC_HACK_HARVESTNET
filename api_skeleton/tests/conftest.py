import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONTRACTS = REPO / "docs" / "contracts"
EXAMPLES = CONTRACTS / "examples"
API_EXAMPLES = EXAMPLES / "public-api"
EVENTS = Path(__file__).parent / "events"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def api_example_files():
    return sorted(API_EXAMPLES.glob("*.json"))


@pytest.fixture
def api_examples():
    return [load(p) for p in api_example_files()]
