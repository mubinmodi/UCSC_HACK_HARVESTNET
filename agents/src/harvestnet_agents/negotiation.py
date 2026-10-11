"""The agent move interface for negotiators (tickets #11 and #13).

**Every shape here is proposed.** Ticket #1 (contract day) was meant to agree the agent
move interface and has not happened yet. This module follows #1's description: a
negotiator receives the current **draft version**, its own **specialists' facts**, and
its **turn**, and returns one move: accept, counter with one amendment plus a reason,
reject with a reason, request a hold, or ask a human. It adds one proposed move, ``pass``
(no change, with a reason), because the advocate must be able to take its turn without
voting. The shapes are plain frozen dataclasses with JSON loaders so they are easy to
adapt once #1 lands.

Rules enforced here, by construction (docs/MVP_DESIGN.md sections 6 and 8):

- Every move has a non-empty reason, and names the draft version it is about.
- A counter carries exactly one amendment. Other moves carry none.
- The advocate can only counter or pass. ``Move`` raises ``AdvocateCannotVote`` for any
  advocate accept, reject, hold request, or ask-a-human (ADR 0001, CONTEXT.md).
- A hold request names only the requesting organization's own resources.
- No move commits anything. ``Move.commits`` is always ``False``: a commitment needs
  every named organization's human to approve the same version, which happens elsewhere
  (Lane A's protocol and Lane C's version-bound approvals).
- A draft can never allocate more pounds of an item than the lot holds. Unallocated
  pounds are the lot's unclaimed pounds, so every pound is visibly accounted for.

``Move.to_dict()`` produces the wire shape proposed by Lane C's transport (PR #27:
``organization_id``, ``version``, ``action``, ``reason``, ``amendment``,
``resource_owner``), so the two sides should fit without an adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Mapping

__all__ = [
    "ADVOCATE_MOVES",
    "AdvocateCannotVote",
    "AdvocateFacts",
    "AgentInput",
    "Allocation",
    "Amendment",
    "DemandCounts",
    "DonorFacts",
    "DraftError",
    "DraftVersion",
    "DropOff",
    "FoodBankFacts",
    "FoodBankGap",
    "HoldRequest",
    "LotItem",
    "Move",
    "MoveError",
    "MoveKind",
    "Mover",
    "OrgMessage",
    "Role",
    "SetPounds",
    "SetTransport",
    "ShiftPounds",
    "StorageSlot",
    "TimeWindow",
    "Transport",
    "Truck",
    "Turn",
    "amendment_from_dict",
    "amendment_to_dict",
    "parse_agent_input",
    "parse_draft",
    "parse_facts",
    "parse_turn",
]


class DraftError(ValueError):
    """A draft version or amendment breaks the draft rules."""


class MoveError(ValueError):
    """A move breaks the move rules."""


class AdvocateCannotVote(MoveError):
    """The advocate proposes and argues, but never accepts, rejects, holds, or vetoes."""


class Role(StrEnum):
    DONOR = "donor"
    FOOD_BANK = "food_bank"
    ADVOCATE = "advocate"


class MoveKind(StrEnum):
    ACCEPT = "accept"
    COUNTER = "counter"
    REJECT = "reject"
    REQUEST_HOLD = "request_hold"
    ASK_HUMAN = "ask_human"
    PASS = "pass"  # proposed addition: take the turn with no change


ADVOCATE_MOVES = frozenset({MoveKind.COUNTER, MoveKind.PASS})


class Mover(StrEnum):
    """Who moves a food bank's share: the donor drops it off, or the food bank collects."""

    DONOR = "donor"
    FOOD_BANK = "food_bank"


# --- Draft agreement ---------------------------------------------------------------------


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"time window ends before it starts: {self.start} to {self.end}")

    def contains(self, at: datetime) -> bool:
        return self.start <= at <= self.end


@dataclass(frozen=True)
class LotItem:
    """One item of the surplus lot, with the donor's condition evidence."""

    produce_id: str
    pounds: float
    condition_grade: str  # good, use_soon, not_for_people (from the donor's check)
    usable_until: datetime  # from the donor's condition specialist (days left)
    condition_doubt: str | None = None  # e.g. "cold chain unknown"; a human must check


@dataclass(frozen=True)
class Allocation:
    produce_id: str
    food_bank_id: str
    pounds: float


@dataclass(frozen=True)
class Transport:
    """Who moves one food bank's share, and when it leaves the donor and arrives."""

    food_bank_id: str
    mover: Mover
    departs_at: datetime
    arrives_at: datetime


@dataclass(frozen=True)
class SetPounds:
    """Set one food bank's pounds of one item (0 removes it)."""

    produce_id: str
    food_bank_id: str
    pounds: float
    kind: Literal["set_pounds"] = "set_pounds"


@dataclass(frozen=True)
class ShiftPounds:
    """Move pounds of one item from one food bank to another."""

    produce_id: str
    from_food_bank_id: str
    to_food_bank_id: str
    pounds: float
    kind: Literal["shift_pounds"] = "shift_pounds"


@dataclass(frozen=True)
class SetTransport:
    """Set who moves one food bank's share, and when."""

    food_bank_id: str
    mover: Mover
    departs_at: datetime
    arrives_at: datetime
    kind: Literal["set_transport"] = "set_transport"


Amendment = SetPounds | ShiftPounds | SetTransport


@dataclass(frozen=True)
class DraftVersion:
    """One numbered version of the shared draft agreement for one surplus lot."""

    lot_id: str
    version: int
    donor_id: str
    deadline: datetime  # when the produce must leave the donor
    items: tuple[LotItem, ...]
    allocations: tuple[Allocation, ...] = ()
    transports: tuple[Transport, ...] = ()
    drop_off_to: tuple[str, ...] = ()  # food banks the donor offered to drop off to
    drop_off_refrigerated: bool = False  # whether that offered drop-off keeps a cold chain
    proposer_id: str = ""
    reason: str = ""
    based_on_version: int | None = None
    names: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ids = [i.produce_id for i in self.items]
        if len(set(ids)) != len(ids):
            raise DraftError("each item appears once in a lot")
        for item in self.items:
            if item.pounds < 0:
                raise DraftError(f"{item.produce_id}: pounds can't be negative")
        seen: set[tuple[str, str]] = set()
        for a in self.allocations:
            if a.produce_id not in ids:
                raise DraftError(f"allocation names {a.produce_id!r}, which is not in the lot")
            if a.pounds < 0:
                raise DraftError("allocated pounds can't be negative")
            if (a.produce_id, a.food_bank_id) in seen:
                raise DraftError(f"{a.food_bank_id} has two lines for {a.produce_id}")
            seen.add((a.produce_id, a.food_bank_id))
        for item in self.items:
            if sum(a.pounds for a in self.allocations if a.produce_id == item.produce_id) > item.pounds:
                raise DraftError(f"{item.produce_id}: allocated more pounds than the lot holds")
        banks = [tr.food_bank_id for tr in self.transports]
        if len(set(banks)) != len(banks):
            raise DraftError("each food bank has at most one transport line")
        for tr in self.transports:
            if tr.arrives_at < tr.departs_at:
                raise DraftError(f"{tr.food_bank_id}: arrives before it departs")

    # Reading the draft

    def item(self, produce_id: str) -> LotItem:
        for i in self.items:
            if i.produce_id == produce_id:
                return i
        raise KeyError(produce_id)

    def pounds(self, produce_id: str, food_bank_id: str) -> float:
        return sum(a.pounds for a in self.allocations if a.produce_id == produce_id and a.food_bank_id == food_bank_id)

    def planned_lb(self, food_bank_id: str) -> float:
        return sum(a.pounds for a in self.allocations if a.food_bank_id == food_bank_id)

    def allocated_lb(self, produce_id: str) -> float:
        return sum(a.pounds for a in self.allocations if a.produce_id == produce_id)

    def unallocated_lb(self, produce_id: str) -> float:
        return self.item(produce_id).pounds - self.allocated_lb(produce_id)

    def allocations_to(self, food_bank_id: str) -> tuple[Allocation, ...]:
        return tuple(a for a in self.allocations if a.food_bank_id == food_bank_id and a.pounds > 0)

    def transport(self, food_bank_id: str) -> Transport | None:
        return next((tr for tr in self.transports if tr.food_bank_id == food_bank_id), None)

    def named_food_banks(self) -> tuple[str, ...]:
        """Food banks with pounds in this version, in draft order."""
        out: list[str] = []
        for a in self.allocations:
            if a.pounds > 0 and a.food_bank_id not in out:
                out.append(a.food_bank_id)
        return tuple(out)

    def named_organizations(self) -> tuple[str, ...]:
        return (self.donor_id, *self.named_food_banks())

    def name_of(self, organization_id: str) -> str:
        return self.names.get(organization_id, organization_id)

    # Changing the draft

    def amend(self, amendment: Amendment, *, proposer_id: str, reason: str) -> DraftVersion:
        """The next version with one amendment applied. Raises ``DraftError`` if invalid."""
        allocations = list(self.allocations)
        transports = list(self.transports)
        match amendment:
            case SetPounds(produce_id=p, food_bank_id=fb, pounds=lb):
                self._known(p)
                allocations = _set(allocations, p, fb, lb)
            case ShiftPounds(produce_id=p, from_food_bank_id=src, to_food_bank_id=dst, pounds=lb):
                self._known(p)
                if lb <= 0:
                    raise DraftError("a shift moves a positive number of pounds")
                if lb > self.pounds(p, src):
                    raise DraftError(f"{src} has only {self.pounds(p, src)} lb of {p} to shift")
                allocations = _set(allocations, p, src, self.pounds(p, src) - lb)
                allocations = _set(allocations, p, dst, self.pounds(p, dst) + lb)
            case SetTransport(food_bank_id=fb, mover=m, departs_at=d, arrives_at=a):
                transports = [tr for tr in transports if tr.food_bank_id != fb] + [Transport(fb, Mover(m), d, a)]
            case _:
                raise DraftError(f"unknown amendment {amendment!r}")
        return replace(
            self,
            version=self.version + 1,
            based_on_version=self.version,
            allocations=tuple(a for a in allocations if a.pounds > 0),
            transports=tuple(transports),
            proposer_id=proposer_id,
            reason=reason,
        )

    def _known(self, produce_id: str) -> None:
        if produce_id not in {i.produce_id for i in self.items}:
            raise DraftError(f"{produce_id!r} is not in the lot")


def _set(allocations: list[Allocation], produce_id: str, food_bank_id: str, pounds: float) -> list[Allocation]:
    if pounds < 0:
        raise DraftError("pounds can't be negative")
    out = [a for a in allocations if not (a.produce_id == produce_id and a.food_bank_id == food_bank_id)]
    if pounds > 0:
        # Keep the line where it was, so draft order stays stable.
        for i, a in enumerate(allocations):
            if a.produce_id == produce_id and a.food_bank_id == food_bank_id:
                out.insert(i, Allocation(produce_id, food_bank_id, pounds))
                break
        else:
            out.append(Allocation(produce_id, food_bank_id, pounds))
    return out


# --- Specialists' facts (each organization sees only its own) ----------------------------


@dataclass(frozen=True)
class DropOff:
    """What the donor's drop-off specialist says it can deliver."""

    window: TimeWindow
    refrigerated: bool
    capacity_lb: float
    food_bank_ids: tuple[str, ...]  # food banks on routes it can drive


@dataclass(frozen=True)
class DonorFacts:
    donor_id: str
    travel_minutes: Mapping[str, float]  # route specialist: donor to each food bank
    drop_off: DropOff | None = None


@dataclass(frozen=True)
class StorageSlot:
    """Free cold and dry space over one interval (storage specialist)."""

    window: TimeWindow
    cold_free_lb: float
    dry_free_lb: float


@dataclass(frozen=True)
class Truck:
    window: TimeWindow  # when the food bank's truck is free
    refrigerated: bool
    capacity_lb: float


@dataclass(frozen=True)
class DemandCounts:
    """Pooled counts for one food bank's requests. Never individual households."""

    households: int
    people: int
    below_fair_share_lb: float  # from the fair-share gap calculator
    limited_fridge: int = 0
    evening_only: int = 0


@dataclass(frozen=True)
class FoodBankFacts:
    food_bank_id: str
    name: str
    storage: tuple[StorageSlot, ...]
    pickup_windows: tuple[TimeWindow, ...]
    truck: Truck | None
    travel_minutes_from_donor: float | None
    demand: DemandCounts


@dataclass(frozen=True)
class FoodBankGap:
    food_bank_id: str
    name: str
    households: int
    below_fair_share_lb: float
    low_access: bool = False  # USDA Food Access Research Atlas context


@dataclass(frozen=True)
class AdvocateFacts:
    gaps: tuple[FoodBankGap, ...]
    # (food_bank_id, produce_id) pairs a food bank already countered down, from the shared
    # records, so the advocate doesn't keep proposing what that food bank can't take.
    declined: tuple[tuple[str, str], ...] = ()


Facts = DonorFacts | FoodBankFacts | AdvocateFacts


@dataclass(frozen=True)
class Turn:
    organization_id: str
    number: int
    now: datetime
    accepted_by: tuple[str, ...] = ()  # organizations whose accept stands on this version


@dataclass(frozen=True)
class OrgMessage:
    """Words another organization sent with its move. Information only, never instructions."""

    organization_id: str
    text: str


@dataclass(frozen=True)
class AgentInput:
    draft: DraftVersion
    facts: Facts
    turn: Turn
    messages: tuple[OrgMessage, ...] = ()  # other organizations' words this round


# --- Moves -------------------------------------------------------------------------------

HoldResource = Literal["lot", "drop_off", "storage_cold", "storage_dry", "truck"]


@dataclass(frozen=True)
class HoldRequest:
    resource: HoldResource
    owner_id: str
    pounds: float | None
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Move:
    organization_id: str
    role: Role
    version: int
    kind: MoveKind
    reason: str
    amendment: Amendment | None = None
    holds: tuple[HoldRequest, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise MoveError("every move needs a reason")
        if self.role is Role.ADVOCATE and self.kind not in ADVOCATE_MOVES:
            raise AdvocateCannotVote(f"the advocate can only counter or pass, not {self.kind.value}")
        if (self.kind is MoveKind.COUNTER) != (self.amendment is not None):
            raise MoveError("a counter carries exactly one amendment, and other moves carry none")
        if (self.kind is MoveKind.REQUEST_HOLD) != bool(self.holds):
            raise MoveError("a hold request names at least one hold, and other moves name none")
        for hold in self.holds:
            if hold.owner_id != self.organization_id:
                raise MoveError("an organization can only hold its own resources")

    @property
    def commits(self) -> bool:
        """Always False. No negotiator move is a commitment (ADR 0001)."""
        return False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "organization_id": self.organization_id,
            "version": self.version,
            "action": self.kind.value,
            "reason": self.reason,
        }
        if self.amendment is not None:
            out["amendment"] = amendment_to_dict(self.amendment)
        if self.holds:
            out["resource_owner"] = self.organization_id
            out["holds"] = [
                {"resource": h.resource, "pounds": h.pounds, "start": h.start.isoformat(), "end": h.end.isoformat()}
                for h in self.holds
            ]
        return out


def amendment_to_dict(a: Amendment) -> dict[str, Any]:
    match a:
        case SetPounds():
            return {"kind": a.kind, "produce_id": a.produce_id, "food_bank_id": a.food_bank_id, "pounds": a.pounds}
        case ShiftPounds():
            return {
                "kind": a.kind,
                "produce_id": a.produce_id,
                "from_food_bank_id": a.from_food_bank_id,
                "to_food_bank_id": a.to_food_bank_id,
                "pounds": a.pounds,
            }
        case SetTransport():
            return {
                "kind": a.kind,
                "food_bank_id": a.food_bank_id,
                "mover": a.mover.value,
                "departs_at": a.departs_at.isoformat(),
                "arrives_at": a.arrives_at.isoformat(),
            }
    raise DraftError(f"unknown amendment {a!r}")


def amendment_from_dict(raw: Mapping[str, Any]) -> Amendment:
    kind = raw.get("kind")
    if kind == "set_pounds":
        return SetPounds(raw["produce_id"], raw["food_bank_id"], float(raw["pounds"]))
    if kind == "shift_pounds":
        return ShiftPounds(raw["produce_id"], raw["from_food_bank_id"], raw["to_food_bank_id"], float(raw["pounds"]))
    if kind == "set_transport":
        return SetTransport(raw["food_bank_id"], Mover(raw["mover"]), _dt(raw["departs_at"]), _dt(raw["arrives_at"]))
    raise DraftError(f"unknown amendment kind {kind!r}")


# --- Recorded-input loaders --------------------------------------------------------------


def parse_draft(raw: Mapping[str, Any]) -> DraftVersion:
    return DraftVersion(
        lot_id=raw["lot_id"],
        version=int(raw["version"]),
        donor_id=raw["donor_id"],
        deadline=_dt(raw["deadline"]),
        items=tuple(
            LotItem(
                produce_id=i["produce_id"],
                pounds=float(i["pounds"]),
                condition_grade=i["condition_grade"],
                usable_until=_dt(i["usable_until"]),
                condition_doubt=i.get("condition_doubt"),
            )
            for i in raw["items"]
        ),
        allocations=tuple(Allocation(a["produce_id"], a["food_bank_id"], float(a["pounds"])) for a in raw.get("allocations", [])),
        transports=tuple(
            Transport(tr["food_bank_id"], Mover(tr["mover"]), _dt(tr["departs_at"]), _dt(tr["arrives_at"]))
            for tr in raw.get("transports", [])
        ),
        drop_off_to=tuple(raw.get("drop_off_to", [])),
        drop_off_refrigerated=bool(raw.get("drop_off_refrigerated", False)),
        proposer_id=raw.get("proposer_id", ""),
        reason=raw.get("reason", ""),
        based_on_version=raw.get("based_on_version"),
        names=dict(raw.get("names", {})),
    )


def parse_facts(role: Role | str, raw: Mapping[str, Any]) -> Facts:
    role = Role(role)
    if role is Role.DONOR:
        d = raw.get("drop_off")
        return DonorFacts(
            donor_id=raw["donor_id"],
            travel_minutes={k: float(v) for k, v in raw.get("travel_minutes", {}).items()},
            drop_off=None
            if d is None
            else DropOff(_window(d["window"]), bool(d["refrigerated"]), float(d["capacity_lb"]), tuple(d["food_bank_ids"])),
        )
    if role is Role.FOOD_BANK:
        truck = raw.get("truck")
        demand = raw["demand"]
        return FoodBankFacts(
            food_bank_id=raw["food_bank_id"],
            name=raw.get("name", raw["food_bank_id"]),
            storage=tuple(
                StorageSlot(_window(s["window"]), float(s["cold_free_lb"]), float(s["dry_free_lb"])) for s in raw.get("storage", [])
            ),
            pickup_windows=tuple(_window(w) for w in raw.get("pickup_windows", [])),
            truck=None if truck is None else Truck(_window(truck["window"]), bool(truck["refrigerated"]), float(truck["capacity_lb"])),
            travel_minutes_from_donor=None if raw.get("travel_minutes_from_donor") is None else float(raw["travel_minutes_from_donor"]),
            demand=DemandCounts(
                households=int(demand["households"]),
                people=int(demand["people"]),
                below_fair_share_lb=float(demand["below_fair_share_lb"]),
                limited_fridge=int(demand.get("limited_fridge", 0)),
                evening_only=int(demand.get("evening_only", 0)),
            ),
        )
    return AdvocateFacts(
        gaps=tuple(
            FoodBankGap(g["food_bank_id"], g.get("name", g["food_bank_id"]), int(g["households"]), float(g["below_fair_share_lb"]), bool(g.get("low_access", False)))
            for g in raw["gaps"]
        ),
        declined=tuple((d["food_bank_id"], d["produce_id"]) for d in raw.get("declined", [])),
    )


def parse_turn(raw: Mapping[str, Any]) -> Turn:
    return Turn(
        organization_id=raw["organization_id"],
        number=int(raw["number"]),
        now=_dt(raw["now"]),
        accepted_by=tuple(raw.get("accepted_by", [])),
    )


def parse_agent_input(raw: Mapping[str, Any]) -> tuple[Role, AgentInput]:
    """Load ``{"role", "draft", "facts", "turn", "messages"?}``: one recorded negotiator input."""
    role = Role(raw["role"])
    messages = tuple(OrgMessage(m["organization_id"], m["text"]) for m in raw.get("messages", []))
    return role, AgentInput(parse_draft(raw["draft"]), parse_facts(role, raw["facts"]), parse_turn(raw["turn"]), messages)


def _window(raw: Mapping[str, Any]) -> TimeWindow:
    return TimeWindow(_dt(raw["start"]), _dt(raw["end"]))


def _dt(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)
