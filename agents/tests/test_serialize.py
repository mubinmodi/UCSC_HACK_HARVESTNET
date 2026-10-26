"""The shared JSON-ready and UTC time helpers."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum

import pytest

from harvestnet_agents.serialize import jsonable, utc_iso


class Color(Enum):
    RED = "red"


@dataclass(frozen=True)
class Box:
    when: datetime
    color: Color
    sizes: tuple[int, ...]


PACIFIC = timezone(timedelta(hours=-7))


def test_jsonable_turns_dataclasses_enums_tuples_and_times_into_plain_data():
    box = Box(datetime(2026, 10, 13, 15, 0, 30, tzinfo=PACIFIC), Color.RED, (1, 2))
    assert jsonable({"box": box, 3: (date(2026, 10, 13), time(9, 5, 7))}) == {
        "box": {"when": "2026-10-13T15:00:30-07:00", "color": "red", "sizes": [1, 2]},
        "3": ["2026-10-13", "09:05:07"],
    }


def test_jsonable_can_shorten_times_to_minutes_for_prompts():
    assert jsonable([datetime(2026, 10, 13, 15, 0, 30, tzinfo=PACIFIC)], timespec="minutes") == ["2026-10-13T15:00-07:00"]


def test_utc_iso_writes_utc_with_z_from_a_string_or_a_datetime_and_refuses_a_missing_offset():
    assert utc_iso("2026-10-13T15:30:00-07:00") == "2026-10-13T22:30:00Z"
    assert utc_iso(datetime(2026, 10, 13, 15, 30, tzinfo=PACIFIC)) == "2026-10-13T22:30:00Z"
    with pytest.raises(ValueError):
        utc_iso("2026-10-13T15:30:00")
