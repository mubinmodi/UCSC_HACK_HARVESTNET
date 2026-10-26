"""The one terms hash (docs/contracts/README.md decision 8).

A draft version's terms are hashed as canonical JSON (sorted keys, compact separators, no NaN):
``sha256:`` plus the hex digest. Lane A's records, Lane B's flows and logs, and the approvals
all use this function. ``harvestnet_platform`` ships on its own (its image and CI do not carry
this package), so it restates the same two lines in ``transport.terms_hash``; a core test holds
the two equal.
"""
import hashlib
import json
from typing import Any

PREFIX = "sha256:"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def terms_hash(terms: Any) -> str:
    """``sha256:<hex>`` of the canonical JSON of ``terms``."""
    return PREFIX + hashlib.sha256(canonical_json(terms).encode()).hexdigest()
