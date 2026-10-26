"""Produce profiles (ticket #12).

A produce profile is the reviewed description of one produce item that agents read
instead of crop names (ADR 0003, docs/MVP_DESIGN.md section 5). The packaged data is
``data/produce_profiles.json``. Every field there either cites sources (with a basis
explaining how the value was read) or carries an explicit assumption (ADR 0002);
loading rejects any field that has neither, both, or an unknown source.

The data shape here is **proposed**, pending ticket #1 (contract day). A profile is a
general reference. The condition of an actual lot is separate evidence from the donor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Iterator, Mapping

__all__ = [
    "PROFILE_FIELDS",
    "DayRange",
    "ProduceProfile",
    "ProfileDataError",
    "ProfileSet",
    "Provenance",
    "Source",
    "TransportTemperature",
    "UnitConversionError",
    "load_profiles",
    "to_pounds",
]

_DATA_FILE = "produce_profiles.json"

PROFILE_FIELDS = (
    "needs_fridge",
    "days_usable_cold",
    "days_usable_room",
    "transport_temperature",
    "condition_grade",
    "units",
)


STORAGE_COLD = "storage_cold"  # hold resources a food bank reserves, by what the profile says the item needs
STORAGE_DRY = "storage_dry"


class ProfileDataError(ValueError):
    """Profile data is malformed or a field is neither sourced nor labeled an assumption."""


class UnitConversionError(ValueError):
    """A quantity can't be converted to pounds from the facts given."""


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    publisher: str
    url: str
    accessed: str
    authors: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Provenance:
    """Where one profile field's value comes from: cited sources, or an assumption."""

    sources: tuple[str, ...] = ()
    basis: str | None = None
    assumption: str | None = None

    @property
    def is_assumption(self) -> bool:
        return self.assumption is not None


@dataclass(frozen=True)
class DayRange:
    min: float
    max: float


@dataclass(frozen=True)
class TransportTemperature:
    target_min_c: float
    target_max_c: float
    cold_required: bool
    chilling_injury_below_c: float | None
    freezing_injury_at_c: float | None


@dataclass(frozen=True)
class ProduceProfile:
    id: str
    name: str
    specificity: str
    needs_fridge: bool
    days_usable_cold: DayRange | None  # None: cold storage not recommended
    days_usable_room: DayRange | None
    transport: TransportTemperature
    condition_grades: tuple[str, ...]
    units: Mapping[str, float | None]  # pounds per unit; None means the donor must state it
    provenance: Mapping[str, Provenance]
    profile_set_version: str
    name_es: str | None = None  # the reviewed Spanish name households see (ticket #6)

    def display_name(self, language: str = "en") -> str:
        """The name a household sees, in ``"en"`` or ``"es"``. A Spanish name comes only from
        the data (``name_es``); it is never machine-translated. ``KeyError`` when it's missing."""
        if language == "en":
            return self.name
        if language == "es" and self.name_es:
            return self.name_es
        raise KeyError(f"no {language} name for {self.id}")

    @property
    def needs_cold(self) -> bool:
        """True when the profile says the item depends on cold storage or a cold chain."""
        return self.needs_fridge or self.transport.cold_required

    @property
    def storage_resource(self) -> str:
        """The hold resource this item sits in at a food bank: ``storage_cold`` or ``storage_dry``."""
        return STORAGE_COLD if self.needs_cold else STORAGE_DRY

    @property
    def moves_when_cooler_fails(self) -> bool:
        """After a cooler failure only cold-dependent produce has to move; the rest keeps (ADR 0003)."""
        return self.needs_cold


@dataclass(frozen=True)
class ProfileSet:
    version: str
    status: str
    sources: Mapping[str, Source]
    profiles: Mapping[str, ProduceProfile]

    def get(self, produce_id: str) -> ProduceProfile:
        """The profile for ``produce_id``. Raises ``KeyError`` for an item with no profile."""
        return self.profiles[produce_id]

    def __contains__(self, produce_id: object) -> bool:
        return produce_id in self.profiles

    def must_move(self, produce_id: str) -> bool:
        """A known item the profile says must leave a failed cooler. An unknown item is neither
        this nor ``can_stay``: a human decides."""
        return produce_id in self.profiles and self.profiles[produce_id].moves_when_cooler_fails

    def can_stay(self, produce_id: str) -> bool:
        """A known item the profile says keeps in a failed cooler's food bank."""
        return produce_id in self.profiles and not self.profiles[produce_id].moves_when_cooler_fails

    def __iter__(self) -> Iterator[ProduceProfile]:
        return iter(self.profiles.values())


def load_profiles(data: Mapping[str, Any] | None = None) -> ProfileSet:
    """Load the packaged profiles, or validate and load ``data`` with the same shape."""
    if data is None:
        data = json.loads(resources.files(__package__).joinpath("data", _DATA_FILE).read_text())
    if data.get("kind") != "produce_profiles":
        raise ProfileDataError("not a produce profile set")
    version = data.get("version")
    if not version:
        raise ProfileDataError("profile set has no version")

    sources = {sid: _source(sid, raw) for sid, raw in data.get("sources", {}).items()}
    profiles: dict[str, ProduceProfile] = {}
    for raw in data.get("profiles", []):
        profile = _profile(raw, sources, str(version))
        if profile.id in profiles:
            raise ProfileDataError(f"duplicate profile {profile.id!r}")
        profiles[profile.id] = profile
    return ProfileSet(version=str(version), status=str(data.get("status", "")), sources=sources, profiles=profiles)


def to_pounds(profile: ProduceProfile, quantity: float, unit: str, lb_per_unit: float | None = None) -> float:
    """Convert ``quantity`` of ``unit`` to pounds.

    ``lb_per_unit`` is the pack weight stated by the donor. It's needed for any unit
    whose weight the profile doesn't hold, so no pack weight is ever guessed.
    """
    if quantity < 0:
        raise UnitConversionError("quantity can't be negative")
    if unit not in profile.units:
        raise UnitConversionError(f"{profile.name} isn't offered in {unit!r}; accepted: {sorted(profile.units)}")
    weight = lb_per_unit if lb_per_unit is not None else profile.units[unit]
    if weight is None:
        raise UnitConversionError(f"no stated pounds per {unit} for {profile.name}; the donor must give it")
    if weight <= 0:
        raise UnitConversionError("pounds per unit must be positive")
    return quantity * weight


def _source(source_id: str, raw: Mapping[str, Any]) -> Source:
    for key in ("title", "publisher", "url", "accessed"):
        if not raw.get(key):
            raise ProfileDataError(f"source {source_id!r} is missing {key!r}")
    return Source(
        id=source_id,
        title=raw["title"],
        publisher=raw["publisher"],
        url=raw["url"],
        accessed=raw["accessed"],
        authors=raw.get("authors"),
        note=raw.get("note"),
    )


def _provenance(profile_id: str, field: str, raw: Mapping[str, Any], sources: Mapping[str, Source]) -> Provenance:
    cited = tuple(raw.get("sources") or ())
    assumption = raw.get("assumption") or None
    where = f"{profile_id}.{field}"
    if bool(cited) == bool(assumption):
        raise ProfileDataError(f"{where} must cite sources or state an assumption, not neither or both")
    unknown = [sid for sid in cited if sid not in sources]
    if unknown:
        raise ProfileDataError(f"{where} cites unknown sources {unknown}")
    if cited and not raw.get("basis"):
        raise ProfileDataError(f"{where} cites sources but gives no basis")
    return Provenance(sources=cited, basis=raw.get("basis"), assumption=assumption)


def _day_range(value: Any) -> DayRange | None:
    if value is None:
        return None
    low, high = float(value["min"]), float(value["max"])
    if low < 0 or high < low:
        raise ProfileDataError(f"bad day range {value}")
    return DayRange(min=low, max=high)


def _profile(raw: Mapping[str, Any], sources: Mapping[str, Source], version: str) -> ProduceProfile:
    profile_id = raw.get("id")
    if not profile_id or not raw.get("name"):
        raise ProfileDataError("profile needs an id and a name")
    provenance = {}
    for field in PROFILE_FIELDS:
        if field not in raw or "value" not in raw[field]:
            raise ProfileDataError(f"{profile_id} is missing field {field!r}")
        provenance[field] = _provenance(profile_id, field, raw[field], sources)

    transport = raw["transport_temperature"]["value"]
    units = {unit: (None if weight is None else float(weight)) for unit, weight in raw["units"]["value"].items()}
    if units.get("lb") != 1:
        raise ProfileDataError(f"{profile_id} must accept pounds as the base unit")

    return ProduceProfile(
        id=profile_id,
        name=raw["name"],
        specificity=raw.get("specificity", ""),
        needs_fridge=bool(raw["needs_fridge"]["value"]),
        days_usable_cold=_day_range(raw["days_usable_cold"]["value"]),
        days_usable_room=_day_range(raw["days_usable_room"]["value"]),
        transport=TransportTemperature(
            target_min_c=float(transport["target_min_c"]),
            target_max_c=float(transport["target_max_c"]),
            cold_required=bool(transport["cold_required"]),
            chilling_injury_below_c=transport.get("chilling_injury_below_c"),
            freezing_injury_at_c=transport.get("freezing_injury_at_c"),
        ),
        condition_grades=tuple(raw["condition_grade"]["value"]),
        units=units,
        provenance=provenance,
        profile_set_version=version,
        name_es=raw.get("name_es") or None,
    )
