"""Plain-data helpers shared by the agents, the core and the flows."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any


def jsonable(value: Any, *, timespec: str = "auto") -> Any:
    """Dataclasses, enums, tuples, mappings and times as plain JSON-ready data.

    ``timespec`` is passed to ``datetime.isoformat`` (``"minutes"`` keeps prompts short)."""
    if is_dataclass(value) and not isinstance(value, type):
        return {k: jsonable(v, timespec=timespec) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): jsonable(v, timespec=timespec) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v, timespec=timespec) for v in value]
    if isinstance(value, (datetime, time)):
        return value.isoformat(timespec=timespec)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def utc_iso(value: str | datetime) -> str:
    """An aware time (or its ISO string) in UTC, written with a trailing ``Z``."""
    when = datetime.fromisoformat(value) if isinstance(value, str) else value
    if when.tzinfo is None:
        raise ValueError("timestamps must include a UTC offset")
    return when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
