"""Fair-share table and calculator (ticket #12).

The fair share is a household's weekly produce amount, set only by household size
(docs/MVP_DESIGN.md section 4, ADR 0009). It is a published shared policy that the
participating food banks agree on. It assigns no produce.

The values in ``data/fair_share_table.json`` are a **placeholder** (synthetic, from the
design doc), and the table says so. SNAP participation is deliberately not an input.

The data shape here is **proposed**, pending ticket #1 (contract day).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Mapping

__all__ = ["FairShare", "FairShareError", "FairShareTable", "fair_share", "load_fair_share_table"]

_DATA_FILE = "fair_share_table.json"


class FairShareError(ValueError):
    """Bad table data or a bad household size."""


@dataclass(frozen=True)
class FairShareTable:
    version: str
    status: str
    note: str
    unit: str
    period: str
    pounds_by_household_size: Mapping[int, float]
    each_additional_person_lb: float
    published_by: str | None = None
    published_date: str | None = None

    @property
    def is_placeholder(self) -> bool:
        return self.status == "placeholder"

    @property
    def largest_listed_size(self) -> int:
        return max(self.pounds_by_household_size)


@dataclass(frozen=True)
class FairShare:
    household_size: int
    pounds: float
    unit: str
    period: str
    table_version: str
    is_placeholder: bool


def load_fair_share_table(data: Mapping[str, Any] | None = None) -> FairShareTable:
    """Load the packaged table, or validate and load ``data`` with the same shape."""
    if data is None:
        data = json.loads(resources.files(__package__).joinpath("data", _DATA_FILE).read_text())
    for key in ("version", "status", "note", "unit", "period", "pounds_by_household_size", "each_additional_person_lb"):
        if data.get(key) in (None, "", {}):
            raise FairShareError(f"fair-share table is missing {key!r}")
    if data.get("kind", "fair_share_table") != "fair_share_table":
        raise FairShareError("not a fair-share table")

    sizes = {int(size): float(lb) for size, lb in data["pounds_by_household_size"].items()}
    if sorted(sizes) != list(range(1, len(sizes) + 1)):
        raise FairShareError("household sizes must run 1, 2, 3, ... with no gaps")
    if any(lb <= 0 for lb in sizes.values()) or float(data["each_additional_person_lb"]) < 0:
        raise FairShareError("fair-share pounds must be positive")

    return FairShareTable(
        version=str(data["version"]),
        status=str(data["status"]),
        note=str(data["note"]),
        unit=str(data["unit"]),
        period=str(data["period"]),
        pounds_by_household_size=sizes,
        each_additional_person_lb=float(data["each_additional_person_lb"]),
        published_by=data.get("published_by"),
        published_date=data.get("published_date"),
    )


def fair_share(household_size: int, table: FairShareTable | None = None) -> FairShare:
    """Weekly fair share for a household of ``household_size`` people."""
    if isinstance(household_size, bool) or not isinstance(household_size, int):
        raise FairShareError("household size must be a whole number")
    if household_size < 1:
        raise FairShareError("household size must be at least 1")
    table = table or load_fair_share_table()

    top = table.largest_listed_size
    if household_size <= top:
        pounds = table.pounds_by_household_size[household_size]
    else:
        pounds = table.pounds_by_household_size[top] + (household_size - top) * table.each_additional_person_lb

    return FairShare(
        household_size=household_size,
        pounds=pounds,
        unit=table.unit,
        period=table.period,
        table_version=table.version,
        is_placeholder=table.is_placeholder,
    )
