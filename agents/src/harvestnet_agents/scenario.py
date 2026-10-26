"""Loading a scenario fixture and building each organization's own facts (ticket #20).

Follows the agreed scenario fixture format (``docs/contracts/scenario-fixtures.md``,
``contract-v0.1``). Lane A (#7) owns the format and the real harness; this loader is
the Lane B side, so the real negotiators can run a fixture now and plug into Lane A's
harness later.

What it does:

- ``load_scenario()`` reads and checks a fixture: the kind and contract version, the
  policy versions (they must match the packaged fair-share table and produce profiles),
  one entry per organization in the turn order, and consent on every request.
- ``facts_for()`` builds **one organization's own specialists' facts** at a moment on
  the harness clock, in the agent move interface's shapes (``negotiation.py``). No
  organization ever gets another's private facts. Food banks and the advocate see
  households only as counts; the fair-share gap comes from the calculator (ADR 0002).
  A fault (the cooler failure) changes a food bank's facts only from its own time on.
- ``initial_draft()`` is version 1 of the draft agreement: the donor's surplus offer,
  converted to pounds by the unit calculator, with no allocations yet.

Readings of the contract that it had to make, listed as contract gaps in the PR for
#20, are marked **Gap** below.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from .calculators import CalculatorError, Calculators, HouseholdBalance
from .fair_share import load_fair_share_table
from .negotiation import (
    AdvocateFacts,
    DemandCounts,
    DonorFacts,
    DraftVersion,
    DropOff,
    Facts,
    FoodBankFacts,
    FoodBankGap,
    LotItem,
    Role,
    StorageSlot,
    TimeWindow,
    Truck,
)
from .profiles import load_profiles
from .serialize import jsonable
from .rules_negotiators import _clock, _join, _lb  # wording helpers: they format facts, never add any

__all__ = [
    "CONTRACT_VERSION",
    "EVENING_STARTS_AT",
    "Fault",
    "HumanScript",
    "NotOffered",
    "Organization",
    "Request",
    "Scenario",
    "ScenarioError",
    "SurplusOffer",
    "draft_to_dict",
    "facts_for",
    "initial_draft",
    "load_scenario",
    "offer_draft",
]

CONTRACT_VERSION = "contract-v0.1"

# **Gap:** the contract asks for an ``evening_only`` count but doesn't define it. Here a
# household is evening-only when every one of its pickup windows starts at or after
# 6 pm local time (the design's "can only pick up after 6 pm", docs/MVP_DESIGN.md §8).
EVENING_STARTS_AT = time(18, 0)


class ScenarioError(ValueError):
    """The fixture doesn't follow the scenario fixture contract."""


@dataclass(frozen=True)
class Organization:
    organization_id: str
    role: Role
    name: str


@dataclass(frozen=True)
class WeeklyWindow:
    days: tuple[str, ...]
    start: time
    end: time | None  # None: open-ended ("after 6 pm")


@dataclass(frozen=True)
class Request:
    """One household's request. A short code, never a name; agents never see this list."""

    request_code: str
    submitted_at: datetime
    household_size: int
    received_this_week_lb: float
    pickup_windows: tuple[WeeklyWindow, ...]
    limited_fridge: bool
    chosen_food_bank_ids: tuple[str, ...]

    @property
    def evening_only(self) -> bool:
        return bool(self.pickup_windows) and all(w.start >= EVENING_STARTS_AT for w in self.pickup_windows)


@dataclass(frozen=True)
class OfferItem:
    produce_id: str
    quantity: float
    unit: str
    lb_per_unit: float | None
    condition_grade: str
    usable_until: datetime
    condition_doubt: str | None


@dataclass(frozen=True)
class SurplusOffer:
    lot_id: str
    donor_id: str
    reported_at: datetime
    deadline: datetime
    recall_notice: bool
    items: tuple[OfferItem, ...]


@dataclass(frozen=True)
class Fault:
    at: datetime
    kind: str
    food_bank_id: str
    reading: Mapping[str, Any]
    source: str
    synthetic: bool


@dataclass(frozen=True)
class HumanScript:
    """What an organization's human does when asked to approve: a script, labeled as one."""

    organization_id: str
    decision: str  # approve or decline
    after_minutes: float


@dataclass(frozen=True)
class Scenario:
    raw: Mapping[str, Any]
    scenario_id: str
    title: str
    mode: str
    synthetic: bool
    note: str
    start: datetime
    end: datetime
    rounds_without_new_terms: int
    request_expiry_days: float
    organizations: tuple[Organization, ...]
    turn_order: tuple[str, ...]
    donors: Mapping[str, Mapping[str, Any]]
    food_banks: Mapping[str, Mapping[str, Any]]
    travel_minutes_between_food_banks: Mapping[str, Mapping[str, float]]
    requests: tuple[Request, ...]
    offers: tuple[SurplusOffer, ...]
    faults: tuple[Fault, ...]
    humans: Mapping[str, HumanScript]
    household_replies: Mapping[str, str]
    rule_checks: tuple[str, ...]

    def organization(self, organization_id: str) -> Organization:
        for o in self.organizations:
            if o.organization_id == organization_id:
                return o
        raise KeyError(organization_id)

    def role_of(self, organization_id: str) -> Role:
        return self.organization(organization_id).role

    @property
    def names(self) -> dict[str, str]:
        return {o.organization_id: o.name for o in self.organizations}

    def faults_known_at(self, at: datetime) -> tuple[Fault, ...]:
        return tuple(f for f in self.faults if f.at <= at)


# --- Loading ------------------------------------------------------------------------------


def load_scenario(source: str | Path | Mapping[str, Any]) -> Scenario:
    """Load and check a scenario fixture from a path or already-parsed JSON."""
    data = json.loads(Path(source).read_text()) if isinstance(source, (str, Path)) else source
    if data.get("kind") != "scenario":
        raise ScenarioError(f"not a scenario fixture (kind {data.get('kind')!r})")
    if data.get("contract_version") != CONTRACT_VERSION:
        raise ScenarioError(f"contract_version {data.get('contract_version')!r}; this loader reads {CONTRACT_VERSION!r}")

    policies = data.get("policies", {})
    table, profiles = load_fair_share_table(), load_profiles()
    for key, packaged in (("fair_share_table_version", table.version), ("produce_profile_set_version", profiles.version)):
        if policies.get(key) != packaged:
            raise ScenarioError(f"policies.{key} is {policies.get(key)!r}, but the packaged one is {packaged!r}")

    organizations = tuple(Organization(o["organization_id"], Role(o["role"]), o["name"]) for o in data["organizations"])
    ids = [o.organization_id for o in organizations]
    turn_order = tuple(data["turn_order"])
    if len(set(ids)) != len(ids) or sorted(turn_order) != sorted(ids):
        raise ScenarioError("turn_order must name every organization exactly once")

    requests = []
    for r in data.get("requests", []):
        if r.get("consent") is not True:
            raise ScenarioError(f"request {r.get('request_code')!r} has no consent; a request without consent isn't saved")
        requests.append(Request(
            request_code=r["request_code"],
            submitted_at=_dt(r["submitted_at"]),
            household_size=int(r["household_size"]),
            received_this_week_lb=float(r["received_this_week_lb"]),
            pickup_windows=tuple(
                WeeklyWindow(tuple(w["days"]), time.fromisoformat(w["start"]), None if w.get("end") is None else time.fromisoformat(w["end"]))
                for w in r.get("pickup_windows", [])
            ),
            limited_fridge=bool(r.get("limited_fridge", False)),
            chosen_food_bank_ids=tuple(r.get("chosen_food_bank_ids", [])),
        ))

    offers = tuple(
        SurplusOffer(
            lot_id=o["lot_id"],
            donor_id=o["donor_id"],
            reported_at=_dt(o["reported_at"]),
            deadline=_dt(o["deadline"]),
            recall_notice=bool(o.get("recall_notice", False)),
            items=tuple(
                OfferItem(
                    produce_id=i["produce_id"],
                    quantity=float(i["quantity"]),
                    unit=i["unit"],
                    lb_per_unit=None if i.get("lb_per_unit") is None else float(i["lb_per_unit"]),
                    condition_grade=i["condition_grade"],
                    usable_until=_dt(i["usable_until"]),
                    condition_doubt=i.get("condition_doubt"),
                )
                for i in o["items"]
            ),
        )
        for o in data.get("surplus_offers", [])
    )
    for o in offers:
        if ids and o.donor_id not in ids:
            raise ScenarioError(f"lot {o.lot_id} names donor {o.donor_id!r}, which is not an organization")

    return Scenario(
        raw=data,
        scenario_id=data["scenario_id"],
        title=data.get("title", data["scenario_id"]),
        mode=data["mode"],
        synthetic=bool(data["synthetic"]),
        note=data.get("note", ""),
        start=_dt(data["clock"]["start"]),
        end=_dt(data["clock"]["end"]),
        rounds_without_new_terms=int(policies.get("rounds_without_new_terms_before_disagreement", 3)),
        request_expiry_days=float(policies.get("request_expiry_days", 7)),
        organizations=organizations,
        turn_order=turn_order,
        donors={d["organization_id"]: d for d in data.get("donors", [])},
        food_banks={f["organization_id"]: f for f in data.get("food_banks", [])},
        travel_minutes_between_food_banks={k: {kk: float(vv) for kk, vv in v.items()} for k, v in data.get("travel_minutes_between_food_banks", {}).items()},
        requests=tuple(requests),
        offers=offers,
        faults=tuple(
            Fault(_dt(f["at"]), f["kind"], f["food_bank_id"], dict(f.get("reading", {})), f.get("source", ""), bool(f.get("synthetic", False)))
            for f in data.get("faults", [])
        ),
        humans={h["organization_id"]: HumanScript(h["organization_id"], h["on_approval_request"], float(h["after_minutes"])) for h in data.get("humans", [])},
        household_replies={h["request_code"]: h["on_pickup_notice"] for h in data.get("household_replies", [])},
        rule_checks=tuple(data.get("rule_checks", [])),
    )


# --- Each organization's own facts ---------------------------------------------------------


def facts_for(scenario: Scenario, organization_id: str, at: datetime, calculators: Calculators, *, lot: SurplusOffer) -> Facts:
    """One organization's own specialists' facts at ``at``, for one surplus lot."""
    role = scenario.role_of(organization_id)
    if role is Role.DONOR:
        return _donor_facts(scenario, organization_id)
    if role is Role.FOOD_BANK:
        return _food_bank_facts(scenario, organization_id, at, calculators, lot)
    return AdvocateFacts(gaps=tuple(
        FoodBankGap(fb, scenario.organization(fb).name, d.households, d.below_fair_share_lb, bool(scenario.food_banks[fb].get("low_access", False)))
        for fb in _food_bank_ids(scenario)
        for d in [_demand(scenario, fb, at, calculators)]
    ))


def _donor_facts(scenario: Scenario, donor_id: str) -> DonorFacts:
    raw = scenario.donors[donor_id]
    d = raw.get("drop_off")
    return DonorFacts(
        donor_id=donor_id,
        travel_minutes={k: float(v) for k, v in raw.get("travel_minutes", {}).items()},
        drop_off=None if d is None else DropOff(_window(d["window"]), bool(d["refrigerated"]), float(d["capacity_lb"]), tuple(d["food_bank_ids"])),
    )


def _food_bank_facts(scenario: Scenario, fb: str, at: datetime, calculators: Calculators, lot: SurplusOffer) -> FoodBankFacts:
    raw = scenario.food_banks[fb]
    truck = raw.get("truck")
    storage = tuple(StorageSlot(_window(s["window"]), float(s["cold_free_lb"]), float(s["dry_free_lb"])) for s in raw.get("storage", []))
    for fault in scenario.faults_known_at(at):
        if fault.kind == "cooler_failure" and fault.food_bank_id == fb:
            storage = _cold_fails_from(storage, fault.at)
    # **Gap:** a food bank's ``travel_minutes_from_donor`` has no field of its own in the
    # fixture. It's the same recorded route time the donor holds (``donors[].travel_minutes``),
    # a route fact rather than a private one, so it's read from there.
    minutes = scenario.donors.get(lot.donor_id, {}).get("travel_minutes", {}).get(fb)
    return FoodBankFacts(
        food_bank_id=fb,
        name=scenario.organization(fb).name,
        storage=storage,
        pickup_windows=tuple(_window(w) for w in raw.get("pickup_windows", [])),
        truck=None if truck is None else Truck(_window(truck["window"]), bool(truck["refrigerated"]), float(truck["capacity_lb"])),
        travel_minutes_from_donor=None if minutes is None else float(minutes),
        demand=_demand(scenario, fb, at, calculators),
    )


def _demand(scenario: Scenario, fb: str, at: datetime, calculators: Calculators) -> DemandCounts:
    # **Gap:** a household may choose several food banks. Following the design ("its
    # request is attached to those food banks", docs/MVP_DESIGN.md §8), it counts at each
    # one it chose, so the advocate's gaps can overlap across food banks.
    expiry = timedelta(days=scenario.request_expiry_days)
    mine = [r for r in scenario.requests if fb in r.chosen_food_bank_ids and r.submitted_at <= at < r.submitted_at + expiry]
    gap = calculators.fair_share_gap([HouseholdBalance(r.household_size, r.received_this_week_lb) for r in mine])
    return DemandCounts(
        households=len(mine),
        people=sum(r.household_size for r in mine),
        below_fair_share_lb=gap.gap_lb,
        limited_fridge=sum(r.limited_fridge for r in mine),
        evening_only=sum(r.evening_only for r in mine),
    )


def _food_bank_ids(scenario: Scenario) -> list[str]:
    return [o for o in scenario.turn_order if scenario.role_of(o) is Role.FOOD_BANK]


def _cold_fails_from(storage: Sequence[StorageSlot], failed_at: datetime) -> tuple[StorageSlot, ...]:
    """The cooler failure reading: cold space is zero from that moment on (the contract)."""
    out = []
    for s in storage:
        if s.window.end <= failed_at:
            out.append(s)
        elif s.window.start >= failed_at:
            out.append(StorageSlot(s.window, 0.0, s.dry_free_lb))
        else:
            out.append(StorageSlot(TimeWindow(s.window.start, failed_at), s.cold_free_lb, s.dry_free_lb))
            out.append(StorageSlot(TimeWindow(failed_at, s.window.end), 0.0, s.dry_free_lb))
    return tuple(out)


# --- Version 1: the donor's surplus offer ---------------------------------------------------


@dataclass(frozen=True)
class NotOffered:
    produce_id: str
    reason: str


def initial_draft(scenario: Scenario, offer: SurplusOffer, calculators: Calculators) -> DraftVersion:
    """Version 1: the donor's offer in pounds (unit calculator), with nothing allocated."""
    return offer_draft(scenario, offer, calculators)[0]


def offer_draft(scenario: Scenario, offer: SurplusOffer, calculators: Calculators) -> tuple[DraftVersion, tuple[NotOffered, ...]]:
    """Version 1 plus any item that couldn't be offered (no profile, or no pack weight)."""
    items, skipped = [], []
    for i in offer.items:
        try:
            pounds = calculators.to_pounds(i.produce_id, i.quantity, i.unit, i.lb_per_unit)
        except CalculatorError as exc:
            skipped.append(NotOffered(i.produce_id, f"not offered: {exc}"))
            continue
        items.append(LotItem(i.produce_id, pounds, i.condition_grade, i.usable_until, i.condition_doubt))
    donor = scenario.donors.get(offer.donor_id, {})
    drop = donor.get("drop_off")
    names = scenario.names
    profiles = calculators.profiles
    what = _join([f"{_lb(i.pounds)} lb {profiles.get(i.produce_id).name.lower() if i.produce_id in profiles else i.produce_id}" for i in items])
    reason = f"Surplus offer from {names.get(offer.donor_id, offer.donor_id)}: {what}. It must leave by {_clock(offer.deadline)}."
    if drop is not None:
        reason += (f" We can drop off at {_join([names.get(fb, fb) for fb in drop['food_bank_ids']])}"
                   + ("" if drop["refrigerated"] else ", not refrigerated") + ".")
    else:
        reason += " We can't drop off; food banks collect."
    draft = DraftVersion(
        lot_id=offer.lot_id,
        version=1,
        donor_id=offer.donor_id,
        deadline=offer.deadline,
        items=tuple(items),
        drop_off_to=tuple(drop["food_bank_ids"]) if drop else (),
        drop_off_refrigerated=bool(drop["refrigerated"]) if drop else False,
        proposer_id=offer.donor_id,
        reason=reason,
        names=names,
    )
    return draft, tuple(skipped)


# --- JSON ---------------------------------------------------------------------------------


def draft_to_dict(draft: DraftVersion) -> dict[str, Any]:
    """A draft version in the agent move interface's ``draft`` shape."""
    return jsonable(draft)


def _window(raw: Mapping[str, Any]) -> TimeWindow:
    return TimeWindow(_dt(raw["start"]), _dt(raw["end"]))


def _dt(value: str) -> datetime:
    t = datetime.fromisoformat(value)
    if t.tzinfo is None:
        raise ScenarioError(f"time {value!r} has no UTC offset; the contract needs one")
    return t
