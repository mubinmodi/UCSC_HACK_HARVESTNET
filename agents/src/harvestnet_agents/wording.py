"""Wording helpers shared by the negotiators, the scenario loader and the cooler-failure logic.

They format facts for a reason or a reason card, and never add a number of their own (ADR 0002).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

__all__ = ["clock", "join", "lb", "window"]


def clock(t: datetime) -> str:
    """A 12-hour clock time: ``3 pm``, ``3:40 pm``."""
    hour = t.hour % 12 or 12
    suffix = "am" if t.hour < 12 else "pm"
    return f"{hour} {suffix}" if t.minute == 0 else f"{hour}:{t.minute:02d} {suffix}"


def window(w: Any) -> str:
    """Anything with ``start`` and ``end`` times, as ``6 pm to 8 pm``."""
    if w.start.date() != w.end.date():
        return f"{clock(w.start)} to {clock(w.end)} the next day"
    return f"{clock(w.start)} to {clock(w.end)}"


def lb(x: float) -> str:
    """A number as written in a reason: ``150``, ``12.5``."""
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def join(words: Iterable[str]) -> str:
    """``a``, ``a and b``, ``a, b and c``; repeated words appear once."""
    words = list(dict.fromkeys(words))
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]
