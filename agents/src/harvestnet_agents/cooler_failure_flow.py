"""The cooler-failure flow from an organization-system reading to updated household texts
(Lane B side of ticket #23, Workflow 4).

This module wires the Lane B pieces together so the #23 join is only plumbing:

1. ``read_cooler_signal`` checks a food bank's cooler reading in Lane C's documented
   shape (PR #26, ``docs/platform/CONTRACTS.md``: ``organization_id``, ``resource``,
   ``synthetic``, ``mode``, ``source``, ``observed_at``, ``data``). A reading is data,
   never an instruction: only enumerated values are interpreted, missing or
   contradictory fields are rejected, and a ``replay`` (recorded copy) reading is
   flagged for the humans who approve. The temperature is carried, never judged: Lane
   C's fixture temperatures are not safety thresholds.
2. ``candidates_from_directory`` turns a Directory search result (PR #27,
   ``LocalDirectory.search`` / ``AgntcyDirectory.search``) plus each candidate's own
   answer into ``cooler_failure.Candidate``. Directory records are discovery only; the
   candidate's fresh answer (its own storage and pickup-hours readings) supplies the
   facts. Travel minutes come from a route calculator. Nothing missing is filled in.
3. ``run_cooler_failure_flow`` runs ``cooler_failure.assess_cooler_failure`` (#15) and
   wraps its proposal as a ``NewVersion``: version-bound terms with Lane C's terms hash,
   ready for Lane C's ``POST /approval-requests``. It never commits (ADR 0001, 0004).
   ``approval_status`` counts only approvals of this exact version and terms.
4. ``household_change_notices`` builds the affected households' texts with
   ``front_desk.pickup_wording`` in each household's language, only once every named
   organization approved this exact version, mentioning only the produce it moves, and
   always with a way to decline.

Every number comes from a reading, an answer, a calculator, a profile, or #15's
arithmetic (ADR 0002). Every shape here is **proposed**, pending ticket #1.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .cooler_failure import (
    Candidate,
    CoolerFailure,
    CoolerFailureDecision,
    HeldItem,
    PickupWindow,
    ReasonCard,
    Truck,
    assess_cooler_failure,
)
from .front_desk import AgreementStatus, Language, PickupFacts, ProducePortion, pickup_wording
from .profiles import ProfileSet, load_profiles

__all__ = [
    "ApprovalStatus",
    "CoolerFailureFlow",
    "CoolerSignal",
    "FlowInputError",
    "HouseholdNotice",
    "NewVersion",
    "NotCommittedError",
    "ReadingError",
    "SystemReading",
    "approval_status",
    "candidates_from_directory",
    "check_reading",
    "cooler_failure_from_readings",
    "household_change_notices",
    "read_cooler_signal",
    "run_cooler_failure_flow",
    "terms_hash",
]


class FlowInputError(ValueError):
    """An input to the flow is missing a field or contradicts itself. Nothing is guessed."""


class ReadingError(FlowInputError):
    """An organization-system reading is unlabeled, incomplete, or from the wrong place."""


class NotCommittedError(ValueError):
    """Households hear only about produce whose new version every named organization approved."""


# --- Organization-system readings (Lane C shape, PR #26) ---------------------------------

_MODES = ("synthetic", "replay")  # live Beeceptor mock, or Lane C's recorded copy
_COOLER_RESOURCES = ("cooler", "cooler-failed")  # Lane C's read() relabels the latter as cooler


@dataclass(frozen=True)
class SystemReading:
    organization_id: str
    resource: str
    synthetic: bool
    mode: str
    source: str
    fixture_version: str | None
    observed_at: datetime
    data: Mapping[str, Any]
    flags: tuple[str, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "organization_id": self.organization_id,
            "resource": self.resource,
            "synthetic": self.synthetic,
            "mode": self.mode,
            "source": self.source,
            "fixture_version": self.fixture_version,
            "observed_at": _iso(self.observed_at),
        }


def check_reading(raw: Any, *, resources: Sequence[str], organization_id: str | None = None) -> SystemReading:
    """Check one Lane C reading's envelope. Rejects anything unlabeled or incomplete."""
    if not isinstance(raw, Mapping):
        raise ReadingError("a reading must be a JSON object")
    org = raw.get("organization_id")
    if not isinstance(org, str) or not org:
        raise ReadingError("reading has no organization_id")
    resource = raw.get("resource")
    if resource not in resources:
        raise ReadingError(f"{org} reading is {resource!r}, expected one of {list(resources)}")
    if organization_id is not None and org != organization_id:
        raise ReadingError(f"expected {organization_id}'s {resource} reading, got {org}'s")
    if raw.get("synthetic") is not True:
        raise ReadingError(f"{org} {resource} reading isn't labeled synthetic; Lane C's contract always labels it")
    mode = raw.get("mode")
    if mode not in _MODES:
        raise ReadingError(f"{org} {resource} reading has unknown mode {mode!r}")
    source = raw.get("source")
    if not isinstance(source, str) or not source:
        raise ReadingError(f"{org} {resource} reading has no source")
    observed_at = _instant(raw.get("observed_at"), f"{org} {resource} observed_at")
    data = raw.get("data")
    if not isinstance(data, Mapping):
        raise ReadingError(f"{org} {resource} reading has no data")

    flags = []
    if mode == "replay":
        flags.append(
            f"{org} {resource} reading is a recorded copy (mode replay, source {source}), not a live reading; "
            "a human should confirm it before approving"
        )
    reason = raw.get("fallback_reason")
    if reason:
        # Quoted as data for the dashboard. It never changes a decision.
        flags.append(f"{org} {resource} fallback reason (as reported): {str(reason)!r}")
    fixture_version = raw.get("fixture_version")
    return SystemReading(
        organization_id=org,
        resource=resource,
        synthetic=True,
        mode=mode,
        source=source,
        fixture_version=None if fixture_version is None else str(fixture_version),
        observed_at=observed_at,
        data=dict(data),
        flags=tuple(flags),
    )


@dataclass(frozen=True)
class CoolerSignal:
    organization_id: str
    failed: bool
    observed_at: datetime
    temperature_c: float | None  # carried as reported; never compared with a threshold here
    reading: SystemReading

    @property
    def flags(self) -> tuple[str, ...]:
        return self.reading.flags


def read_cooler_signal(raw: Any, *, organization_id: str | None = None) -> CoolerSignal:
    """Read a cooler reading. ``status`` and ``cold_available`` must both be given and agree."""
    reading = check_reading(raw, resources=_COOLER_RESOURCES, organization_id=organization_id)
    status = reading.data.get("status")
    cold = reading.data.get("cold_available")
    if status not in ("working", "failed"):
        raise ReadingError(f"{reading.organization_id} cooler status {status!r} is neither working nor failed")
    if type(cold) is not bool:
        raise ReadingError(f"{reading.organization_id} cooler reading doesn't say whether cold storage is available")
    if (status == "failed") == cold:
        raise ReadingError(f"{reading.organization_id} cooler reading contradicts itself: status {status}, cold_available {cold}")
    temperature = reading.data.get("temperature_c")
    return CoolerSignal(
        organization_id=reading.organization_id,
        failed=status == "failed",
        observed_at=reading.observed_at,
        temperature_c=temperature if _is_number(temperature) else None,
        reading=reading,
    )


def cooler_failure_from_readings(
    signal: CoolerSignal,
    truck_reading: Any,
    pickup_hours_reading: Any,
    holding: Mapping[str, Any],
) -> tuple[CoolerFailure, tuple[str, ...]]:
    """Build #15's ``CoolerFailure`` from the failing food bank's own readings and holding.
    Returns it with the readings' flags for the dashboard.

    ``holding`` is the food bank's share of the committed version (the core's record):
    ``event_id``, ``lot_id``, ``current_version``, ``food_bank_id``, ``food_bank_name``,
    ``timezone``, ``items`` (``produce_id``, ``pounds``), and ``households_pickup``.
    """
    org = signal.organization_id
    _require(holding, ("event_id", "lot_id", "current_version", "food_bank_id", "food_bank_name", "timezone", "items", "households_pickup"), "holding")
    if holding["food_bank_id"] != org:
        raise ReadingError(f"cooler reading is {org}'s, but the holding is {holding['food_bank_id']}'s")
    tz = _zone(holding["timezone"])
    truck = check_reading(truck_reading, resources=("truck",), organization_id=org)
    hours = check_reading(pickup_hours_reading, resources=("pickup-hours",), organization_id=org)
    detected_at = signal.observed_at.astimezone(tz)

    version = holding["current_version"]
    if type(version) is not int or version < 1:
        raise FlowInputError("holding current_version must be a positive whole number")
    items = holding["items"]
    if not isinstance(items, list) or not items:
        raise FlowInputError("holding has no items")

    failure = CoolerFailure(
        food_bank_id=org,
        food_bank_name=str(holding["food_bank_name"]),
        lot_id=str(holding["lot_id"]),
        current_version=version,
        detected_at=detected_at,
        items=tuple(_held_item(i) for i in items),
        households_pickup=_window(holding["households_pickup"], tz, "holding households_pickup"),
        own_pickup_windows=_windows(hours.data.get("windows"), tz, f"{org} pickup-hours"),
        truck=_truck(truck, detected_at, tz),
    )
    return failure, truck.flags + hours.flags


def _truck(reading: SystemReading, detected_at: datetime, tz: ZoneInfo) -> Truck | None:
    data = reading.data
    available, refrigerated = data.get("available"), data.get("refrigerated")
    if type(available) is not bool or type(refrigerated) is not bool:
        raise ReadingError(f"{reading.organization_id} truck reading must say available and refrigerated")
    windows = _windows(data.get("windows"), tz, f"{reading.organization_id} truck")
    if not available:
        return None
    usable = sorted((w for w in windows if w.end > detected_at), key=lambda w: w.start)
    if not usable:
        return None  # #15 then says the food bank has no truck free
    return Truck(refrigerated=refrigerated, available_from=usable[0].start)


# --- Directory rediscovery -> candidates (Lane C shape, PR #27) --------------------------


def candidates_from_directory(
    directory_result: Mapping[str, Any],
    answers: Mapping[str, Mapping[str, Any]],
    travel_minutes: Mapping[str, float],
    *,
    exclude: str,
    timezone: str,
) -> tuple[tuple[Candidate, ...], tuple[str, ...]]:
    """Candidates from Directory records plus each food bank's own answer.

    ``answers[food_bank_id]`` is ``{"response": "answered", "name", "storage":
    <its storage reading>, "pickup_hours": <its pickup-hours reading>}`` or
    ``{"response": "declined", "name", "reason"}``. A food bank with no answer gets
    ``no_answer``. ``travel_minutes`` is from the route calculator; a missing value
    stays missing. Returns the candidates and flags (Directory mode, replayed readings)
    for the dashboard.
    """
    tz = _zone(timezone)
    if not isinstance(directory_result, Mapping) or not isinstance(directory_result.get("records"), list):
        raise FlowInputError("Directory result must have a records list")
    mode = directory_result.get("mode")
    flags: list[str] = []
    if mode != "agntcy_directory":
        flags.append(f"Directory results came from {mode!r}, not the AGNTCY Directory")

    candidates: list[Candidate] = []
    seen: set[str] = set()
    for record in directory_result["records"]:
        org, caps, card_name = _record_info(record)
        if caps.get("role") != "food_bank" or org == exclude or org in seen:
            continue
        seen.add(org)
        answer = answers.get(org)
        minutes = travel_minutes.get(org)
        if minutes is not None and (not _is_number(minutes) or minutes < 0):
            raise FlowInputError(f"travel minutes for {org} must be a non-negative number")
        name = str(answer.get("name") or card_name) if answer else card_name
        candidate, candidate_flags = _candidate(org, name, answer, minutes, tz)
        candidates.append(candidate)
        flags.extend(candidate_flags)

    for org in sorted(set(answers) - seen - {exclude}):
        flags.append(f"ignored an answer from {org}, which the Directory search didn't return")
    return tuple(candidates), tuple(flags)


def _record_info(record: Any) -> tuple[str, Mapping[str, Any], str]:
    try:
        info = json.loads(record["annotations"]["harvestnet"])
        org = info["organization_id"]
        caps = info.get("capabilities") or {}
    except (KeyError, TypeError, ValueError) as exc:
        raise FlowInputError("Directory record has no HarvestNet annotation") from exc
    if not isinstance(org, str) or not org or not isinstance(caps, Mapping):
        raise FlowInputError("Directory record annotation has no organization_id")
    card_name = org
    for module in record.get("modules") or ():
        name = ((module.get("data") or {}).get("card_data") or {}).get("name") if isinstance(module, Mapping) else None
        if name:
            card_name = str(name)
            break
    return org, caps, card_name


def _candidate(org: str, name: str, answer: Mapping[str, Any] | None, minutes: float | None, tz: ZoneInfo):
    if answer is None:
        return Candidate(food_bank_id=org, name=name, response="no_answer", travel_minutes=minutes), ()
    response = answer.get("response")
    if response == "declined":
        reason = answer.get("reason")
        return Candidate(food_bank_id=org, name=name, response="declined", declined_reason=None if reason is None else str(reason)), ()
    if response != "answered":
        raise FlowInputError(f"{org}'s answer has unknown response {response!r}")
    storage = check_reading(answer.get("storage"), resources=("storage",), organization_id=org)
    hours = check_reading(answer.get("pickup_hours"), resources=("pickup-hours",), organization_id=org)
    cold = storage.data.get("cold_available_lb")
    if not _is_number(cold) or cold < 0:
        raise ReadingError(f"{org} storage reading has no valid cold_available_lb")
    candidate = Candidate(
        food_bank_id=org,
        name=name,
        response="answered",
        cold_space_lb=float(cold),
        pickup_windows=_windows(hours.data.get("windows"), tz, f"{org} pickup-hours"),
        travel_minutes=None if minutes is None else float(minutes),
    )
    return candidate, storage.flags + hours.flags


# --- The new version and its approvals (Lane C shape, PR #28) ----------------------------


def terms_hash(terms: Mapping[str, Any]) -> str:
    """Same as Lane C's ``transport.terms_hash``: sha256 of sorted, compact JSON."""
    canonical = json.dumps(terms, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class NewVersion:
    """A proposed new draft version. It needs fresh approvals; old ones never carry over."""

    event_id: str
    lot_id: str
    version: int
    based_on_version: int
    proposer_id: str
    receiving_food_bank_id: str | None
    receiving_food_bank_name: str | None
    households_collect: PickupWindow | None
    organizations: tuple[str, ...]  # whose humans must approve this exact version
    terms: dict[str, Any]
    terms_hash: str
    status: str  # awaiting_receiver_decision, or awaiting_approval when no food bank receives
    approvals: tuple[str, ...] = ()

    @property
    def committed(self) -> bool:
        # Commitment needs every named organization's human to approve this exact
        # version, through Lane C's approvals and the core. Never here.
        return False

    def approval_request(self) -> dict[str, Any]:
        """The body for Lane C's ``POST /approval-requests``."""
        return {"event_id": self.event_id, "version": self.version, "terms": self.terms, "organizations": list(self.organizations)}


@dataclass(frozen=True)
class ApprovalStatus:
    approved_by: tuple[str, ...]
    declined_by: tuple[str, ...]
    missing: tuple[str, ...]
    ignored: tuple[tuple[str, str], ...]  # (organization_id, why it doesn't count)

    @property
    def all_named_approved(self) -> bool:
        return not self.missing and not self.declined_by

    @property
    def state(self) -> str:
        if self.declined_by:
            return "declined"
        return "all_named_approved" if self.all_named_approved else "awaiting_approvals"


def approval_status(new_version: NewVersion, approvals: Sequence[Mapping[str, Any]]) -> ApprovalStatus:
    """Count only human decisions on this exact event, version, and terms hash.

    ``approvals`` are Lane C decision records: ``event_id``, ``version``,
    ``organization_id``, ``terms_hash``, ``decision`` (``approve`` or ``decline``).
    """
    approved, declined, ignored = set(), set(), []
    for a in approvals:
        org = str(a.get("organization_id"))
        if org not in new_version.organizations:
            ignored.append((org, "not named on this version"))
        elif a.get("event_id") != new_version.event_id:
            ignored.append((org, "for a different event"))
        elif a.get("version") != new_version.version:
            ignored.append((org, f"for version {a.get('version')}, not {new_version.version}"))
        elif a.get("terms_hash") != new_version.terms_hash:
            ignored.append((org, "for different terms"))
        elif a.get("decision") == "approve":
            approved.add(org)
        elif a.get("decision") == "decline":
            declined.add(org)
        else:
            ignored.append((org, f"unknown decision {a.get('decision')!r}"))
    approved -= declined
    return ApprovalStatus(
        approved_by=tuple(sorted(approved)),
        declined_by=tuple(sorted(declined)),
        missing=tuple(o for o in new_version.organizations if o not in approved and o not in declined),
        ignored=tuple(ignored),
    )


# --- The flow ----------------------------------------------------------------------------

_AWAITING = ("awaiting_receiver_decision", "awaiting_approval")


@dataclass(frozen=True)
class CoolerFailureFlow:
    status: str  # "no_failure" or "assessed"
    signal: CoolerSignal
    failure: CoolerFailure | None
    candidates: tuple[Candidate, ...]
    decision: CoolerFailureDecision | None
    new_version: NewVersion | None
    flags: tuple[str, ...]
    profiles: ProfileSet | None = field(repr=False, compare=False, default=None)

    def dashboard(self) -> dict[str, Any]:
        """The food bank dashboard payload: JSON-safe, counts only, no household data."""
        view: dict[str, Any] = {
            "food_bank_id": self.signal.organization_id,
            "status": self.status,
            "synthetic": self.signal.reading.synthetic,
            "reading": {**self.signal.reading.summary(), "cooler_status": "failed" if self.signal.failed else "working"},
            "flags": list(self.flags),
        }
        if self.decision is None:
            return view
        d = self.decision
        view.update(
            profile_set_version=d.profile_set_version,
            items={
                "move": [_item_view(i) for i in d.items_to_move],
                "stay": [_item_view(i) for i in d.items_staying],
                "human_check": [_item_view(i) for i in d.items_unsupported],
            },
            reason_cards=[_card_view(c) for c in d.reason_cards],
            fallback=[{"produce_id": f.produce_id, "pounds": f.pounds, "kind": f.kind, "reason": f.reason} for f in d.fallback],
            new_version=None
            if self.new_version is None
            else {
                "event_id": self.new_version.event_id,
                "version": self.new_version.version,
                "based_on_version": self.new_version.based_on_version,
                "status": self.new_version.status,
                "receiving_food_bank_id": self.new_version.receiving_food_bank_id,
                "needs_approval_from": list(self.new_version.organizations),
                "terms_hash": self.new_version.terms_hash,
                "committed": self.new_version.committed,
            },
        )
        return view

    def rule_checks(self) -> dict[str, bool]:
        """The rule checks Lane B can run on its own outputs, recomputed from the terms."""
        nv, d, failure = self.new_version, self.decision, self.failure
        if d is None or failure is None:
            return {}
        held = _pounds_by_item((i.produce_id, i.pounds) for i in failure.items)
        to_move = _pounds_by_item((i.produce_id, i.pounds) for i in d.items_to_move)
        terms = nv.terms if nv is not None else {"moves": [], "fallback": [], "staying": [], "needs_human_check": []}
        moved = _pounds_by_item((m["produce_id"], m["pounds"]) for m in terms["moves"])
        fallback = _pounds_by_item((f["produce_id"], f["pounds"]) for f in terms["fallback"])
        staying = _pounds_by_item((s["produce_id"], s["pounds"]) for s in terms["staying"])
        human = _pounds_by_item((h["produce_id"], h["pounds"]) for h in terms["needs_human_check"])
        if nv is None:  # nothing needed to move: the decision itself accounts for every pound
            staying = _pounds_by_item((i.produce_id, i.pounds) for i in d.items_staying)
            human = _pounds_by_item((i.produce_id, i.pounds) for i in d.items_unsupported)

        profiles = self.profiles or load_profiles()
        moving_ids = set(moved) | set(fallback)
        card_ids = [c.food_bank_id for c in d.reason_cards]
        return {
            "only_cold_dependent_items_move": all(p in profiles and profiles.get(p).needs_cold for p in moving_ids)
            and all(p in profiles and not profiles.get(p).needs_cold for p in staying),
            "every_candidate_has_reason_card": (not to_move and not card_ids)
            or sorted(card_ids) == sorted(c.food_bank_id for c in self.candidates),
            "pounds_conserved": _same(held, _add(moved, fallback, staying, human)),
            "all_pounds_have_pathway": _same(to_move, _add(moved, fallback)),
            "versioned_approvals": nv is None
            or (
                nv.version == nv.based_on_version + 1
                and nv.terms.get("version") == nv.version
                and nv.terms_hash == terms_hash(nv.terms)
                and nv.approval_request()["version"] == nv.version
            ),
            "no_auto_commit": nv is None or (nv.committed is False and nv.approvals == () and nv.status in _AWAITING),
        }


def run_cooler_failure_flow(
    *,
    cooler_reading: Any,
    truck_reading: Any,
    pickup_hours_reading: Any,
    holding: Mapping[str, Any],
    directory_result: Mapping[str, Any],
    answers: Mapping[str, Mapping[str, Any]],
    travel_minutes: Mapping[str, float],
    profiles: ProfileSet | None = None,
) -> CoolerFailureFlow:
    """From the failing food bank's cooler reading to a new version awaiting fresh approvals."""
    profiles = profiles or load_profiles()
    signal = read_cooler_signal(cooler_reading)
    if not signal.failed:
        return CoolerFailureFlow("no_failure", signal, None, (), None, None, signal.flags, profiles)

    failure, own_flags = cooler_failure_from_readings(signal, truck_reading, pickup_hours_reading, holding)
    candidates, candidate_flags = candidates_from_directory(
        directory_result, answers, travel_minutes, exclude=failure.food_bank_id, timezone=holding["timezone"]
    )
    flags = signal.flags + own_flags + candidate_flags

    decision = assess_cooler_failure(failure, candidates, profiles=profiles)
    new_version = None
    if decision.items_to_move:
        new_version = _new_version(str(holding["event_id"]), failure, decision, signal)
    return CoolerFailureFlow("assessed", signal, failure, candidates, decision, new_version, flags, profiles)


def _new_version(event_id: str, failure: CoolerFailure, d: CoolerFailureDecision, signal: CoolerSignal) -> NewVersion:
    p = d.proposal
    moves = []
    if p is not None:
        moves = [
            {
                "produce_id": i.produce_id,
                "pounds": _plain(i.pounds),
                "from_food_bank_id": failure.food_bank_id,
                "to_food_bank_id": p.receiving_food_bank_id,
                "mover": p.mover,
                "departs_at": _iso(p.departs_at),
                "arrives_at": _iso(p.arrives_at),
                "households_collect": _window_view(p.households_collect),
            }
            for i in p.items
        ]
    version = failure.current_version + 1
    terms = {
        "event_id": event_id,
        "lot_id": failure.lot_id,
        "version": version,
        "based_on_version": failure.current_version,
        "change": "cooler_failure",
        "proposer_id": failure.food_bank_id,
        "evidence": {"cooler_reading": signal.reading.summary(), "profile_set_version": d.profile_set_version},
        "moves": moves,
        "fallback": [
            {"produce_id": f.produce_id, "pounds": _plain(f.pounds), "kind": f.kind, "food_bank_id": failure.food_bank_id, "reason": f.reason}
            for f in d.fallback
        ],
        "staying": [{"produce_id": i.produce_id, "pounds": _plain(i.pounds), "food_bank_id": failure.food_bank_id} for i in d.items_staying],
        "needs_human_check": [{"produce_id": i.produce_id, "pounds": _plain(i.pounds), "reason": i.reason} for i in d.items_unsupported],
        "reason": p.reason if p is not None else "; ".join(f.reason for f in d.fallback),
    }
    # With no receiver, the failing food bank's own manager still approves the changed plan.
    organizations = tuple(p.needs_approval_from) if p is not None else (failure.food_bank_id,)
    return NewVersion(
        event_id=event_id,
        lot_id=failure.lot_id,
        version=version,
        based_on_version=failure.current_version,
        proposer_id=failure.food_bank_id,
        receiving_food_bank_id=None if p is None else p.receiving_food_bank_id,
        receiving_food_bank_name=None if p is None else p.receiving_food_bank_name,
        households_collect=None if p is None else p.households_collect,
        organizations=organizations,
        terms=terms,
        terms_hash=terms_hash(terms),
        status="awaiting_receiver_decision" if p is not None else "awaiting_approval",
    )


# --- Household texts (front_desk wording) --------------------------------------------------

DECLINE_REPLIES = {Language.EN: ("can't make it", "cant make it", "cannot make it"), Language.ES: ("no puedo ir",)}
"""Matches the phrases Lane C's reply workflow releases a portion on (PR #28)."""
ACCEPT_REPLIES = {Language.EN: ("yes",), Language.ES: ("sí", "si")}

_NOTICE = {
    Language.EN: {
        "changed": "Your pickup changed.",
        "reply": "Reply YES to keep it, or CAN'T MAKE IT to decline. If you decline, your portion goes to another household.",
        "decline": "Can't make it? Reply CAN'T MAKE IT and your portion goes to another household.",
    },
    Language.ES: {
        "changed": "Su recogida cambió.",
        "reply": "Responda SÍ para conservarla, o NO PUEDO IR para rechazarla. Si la rechaza, su porción pasa a otro hogar.",
        "decline": "¿No puede ir? Responda NO PUEDO IR y su porción pasa a otro hogar.",
    },
}


@dataclass(frozen=True)
class HouseholdNotice:
    """One pickup notice (section 11): request code, food bank, items and pounds, window, version."""

    request_code: str
    language: Language
    event_id: str
    version: int
    food_bank_id: str
    food_bank: str
    items: tuple[tuple[str, str, float], ...]  # (produce_id, display name, pounds)
    window: PickupWindow
    reply_expected: bool  # the household didn't choose this food bank, so it is asked
    decline_replies: tuple[str, ...]
    accept_replies: tuple[str, ...]
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Lane C's pickup notice fields (PR #28) where they exist. ``to``, ``pickup_id``,
        and ``release_url`` belong to the core and n8n, never to this module."""
        return {
            "committed": True,
            "event_id": self.event_id,
            "version": self.version,
            "request_code": self.request_code,
            "language": self.language.value,
            "food_bank_id": self.food_bank_id,
            "food_bank": self.food_bank,
            "items": [{"name": name, "pounds": _plain(lb), "produce_id": pid} for pid, name, lb in self.items],
            "window": _window_view(self.window),
            "reply_expected": self.reply_expected,
            "decline_replies": list(self.decline_replies),
            "accept_replies": list(self.accept_replies),
            "message": self.message,
        }


def household_change_notices(
    new_version: NewVersion,
    approvals: Sequence[Mapping[str, Any]],
    households: Sequence[Mapping[str, Any]],
    item_names: Mapping[str, Mapping[str, str]] | None = None,
    profiles: ProfileSet | None = None,
) -> tuple[HouseholdNotice, ...]:
    """Texts for households whose portions the new version moves to the receiving food bank.

    ``households`` are request records: ``request_code``, ``language``,
    ``chosen_food_banks``, and ``portions`` (``produce_id``, ``pounds``,
    ``food_bank_id``) as the portion calculator assigns them under the new version.
    ``item_names[language][produce_id]`` gives display names; English falls back to the
    produce profile's name, and any other language must be given.
    """
    status = approval_status(new_version, approvals)
    if not status.all_named_approved:
        raise NotCommittedError(
            f"version {new_version.version} is {status.state}: missing {list(status.missing)}, declined by {list(status.declined_by)}"
        )
    receiver = new_version.receiving_food_bank_id
    if receiver is None:
        return ()  # nothing moved to another food bank; the same-day offer is Workflow 3's
    profiles = profiles or load_profiles()
    item_names = item_names or {}
    moved = _pounds_by_item((m["produce_id"], m["pounds"]) for m in new_version.terms["moves"])

    notices, assigned = [], {}
    for h in households:
        _require(h, ("request_code", "language", "chosen_food_banks", "portions"), "household")
        language = _language(h["language"])
        items = []
        for portion in h["portions"]:
            _require(portion, ("produce_id", "pounds", "food_bank_id"), "portion")
            pid, lb = portion["produce_id"], portion["pounds"]
            if portion["food_bank_id"] != receiver or pid not in moved:
                continue  # unchanged, or not part of this version: never mentioned
            if not _is_number(lb) or lb <= 0:
                raise FlowInputError(f"portion pounds for {h['request_code']} must be a positive number from the portion calculator")
            assigned[pid] = assigned.get(pid, 0.0) + float(lb)
            items.append((pid, _item_name(pid, language, item_names, profiles), float(lb)))
        if not items:
            continue
        chose_receiver = receiver in h["chosen_food_banks"]
        notices.append(_notice(new_version, str(h["request_code"]), language, tuple(items), reply_expected=not chose_receiver))

    for pid, lb in assigned.items():
        if lb > moved[pid] and not math.isclose(lb, moved[pid]):
            raise FlowInputError(
                f"portions give {_plain(lb)} lb of {pid}, but version {new_version.version} moves {_plain(moved[pid])} lb; "
                "the portion calculator must recompute"
            )
    return tuple(notices)


def _notice(nv: NewVersion, code: str, language: Language, items, *, reply_expected: bool) -> HouseholdNotice:
    window = nv.households_collect
    facts = PickupFacts(
        food_bank=nv.receiving_food_bank_name,
        window_start=window.start.time(),
        window_end=window.end.time(),
        code=code,
        # Every named organization approved this exact version, so these portions are committed.
        portions=[ProducePortion(name, lb, AgreementStatus.COMMITTED) for _, name, lb in items],
    )
    t = _NOTICE[language]
    message = " ".join((t["changed"], pickup_wording(facts, language), t["reply"] if reply_expected else t["decline"]))
    return HouseholdNotice(
        request_code=code,
        language=language,
        event_id=nv.event_id,
        version=nv.version,
        food_bank_id=nv.receiving_food_bank_id,
        food_bank=nv.receiving_food_bank_name,
        items=items,
        window=window,
        reply_expected=reply_expected,
        decline_replies=DECLINE_REPLIES[language],
        accept_replies=ACCEPT_REPLIES[language] if reply_expected else (),
        message=message,
    )


def _item_name(pid: str, language: Language, names: Mapping[str, Mapping[str, str]], profiles: ProfileSet) -> str:
    given = (names.get(language.value) or {}).get(pid)
    if given:
        return given
    if language is Language.EN and pid in profiles:
        return profiles.get(pid).name.lower()
    raise FlowInputError(f"no {language.value} name for {pid}; it must be given, not guessed")


def _language(value: Any) -> Language:
    try:
        return Language(value)
    except ValueError as exc:
        raise FlowInputError(f"unsupported household language {value!r}") from exc


# --- Helpers -------------------------------------------------------------------------------


def _require(raw: Any, keys: Sequence[str], what: str) -> None:
    if not isinstance(raw, Mapping):
        raise FlowInputError(f"{what} must be a JSON object")
    missing = [k for k in keys if raw.get(k) is None]
    if missing:
        raise FlowInputError(f"{what} is missing {missing}")


def _held_item(raw: Any) -> HeldItem:
    _require(raw, ("produce_id", "pounds"), "held item")
    if not _is_number(raw["pounds"]) or raw["pounds"] <= 0:
        raise FlowInputError(f"held item {raw['produce_id']!r} must have positive pounds")
    return HeldItem(produce_id=str(raw["produce_id"]), pounds=float(raw["pounds"]))


def _zone(name: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(name))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise FlowInputError(f"unknown timezone {name!r}") from exc


def _instant(value: Any, what: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ReadingError(f"{what} is missing")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReadingError(f"{what} isn't an ISO-8601 time: {value!r}") from exc
    if t.tzinfo is None:
        raise ReadingError(f"{what} has no timezone: {value!r}")
    return t


def _window(raw: Any, tz: ZoneInfo, what: str) -> PickupWindow:
    if not isinstance(raw, Mapping):
        raise FlowInputError(f"{what} window must be an object with start and end")
    start = _instant(raw.get("start"), f"{what} start").astimezone(tz)
    end = _instant(raw.get("end"), f"{what} end").astimezone(tz)
    if end <= start:
        raise FlowInputError(f"{what} window ends before it starts")
    return PickupWindow(start=start, end=end)


def _windows(raw: Any, tz: ZoneInfo, what: str) -> tuple[PickupWindow, ...]:
    if not isinstance(raw, list):
        raise ReadingError(f"{what} reading has no windows list")
    return tuple(_window(w, tz, what) for w in raw)


def _iso(t: datetime) -> str:
    return t.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")


def _window_view(w: PickupWindow) -> dict[str, str]:
    return {"start": _iso(w.start), "end": _iso(w.end)}


def _plain(x: float) -> float | int:
    return int(x) if float(x).is_integer() else x


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, PickupWindow):
        return _window_view(value)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float):
        return _plain(value)
    return value


def _item_view(i) -> dict[str, Any]:
    return {"produce_id": i.produce_id, "pounds": _plain(i.pounds), "reason": i.reason}


def _card_view(c: ReasonCard) -> dict[str, Any]:
    return {
        "food_bank_id": c.food_bank_id,
        "name": c.name,
        "outcome": c.outcome,
        "text": c.text,
        "reasons": list(c.reasons),
        "facts": _jsonable(c.facts),
    }


def _pounds_by_item(pairs) -> dict[str, float]:
    out: dict[str, float] = {}
    for pid, lb in pairs:
        out[pid] = out.get(pid, 0.0) + float(lb)
    return out


def _add(*parts: Mapping[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in parts:
        for pid, lb in part.items():
            out[pid] = out.get(pid, 0.0) + lb
    return out


def _same(a: Mapping[str, float], b: Mapping[str, float]) -> bool:
    return set(a) == set(b) and all(math.isclose(a[k], b[k]) for k in a)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
