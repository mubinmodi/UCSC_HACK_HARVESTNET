"""The proposed agent move interface (#11): drafts, amendments, and move rules."""

from datetime import datetime

import pytest

from harvestnet_agents.negotiation import (
    AdvocateCannotVote,
    Allocation,
    DraftError,
    DraftVersion,
    HoldRequest,
    LotItem,
    Move,
    MoveError,
    MoveKind,
    Mover,
    Role,
    SetPounds,
    SetTransport,
    ShiftPounds,
    Transport,
    parse_draft,
)


def t(hhmm):
    return datetime.fromisoformat(f"2026-10-13T{hhmm}")


def draft(**overrides):
    base = dict(
        lot_id="lot-1",
        version=2,
        donor_id="market",
        deadline=t("15:00"),
        items=(
            LotItem("apples", 300, "good", usable_until=datetime(2026, 10, 30)),
            LotItem("romaine", 200, "good", usable_until=datetime(2026, 10, 18)),
        ),
        allocations=(Allocation("apples", "rural", 250), Allocation("romaine", "city", 200)),
        transports=(Transport("city", Mover.FOOD_BANK, t("14:00"), t("14:30")),),
    )
    base.update(overrides)
    return DraftVersion(**base)


def test_draft_reports_planned_and_unallocated_pounds():
    d = draft()
    assert d.planned_lb("rural") == 250
    assert d.unallocated_lb("apples") == 50
    assert d.unallocated_lb("romaine") == 0
    assert d.named_food_banks() == ("rural", "city")
    assert d.named_organizations() == ("market", "rural", "city")


def test_a_draft_can_never_allocate_more_than_the_lot_holds():
    with pytest.raises(DraftError):
        draft(allocations=(Allocation("apples", "rural", 250), Allocation("apples", "city", 100)))


def test_every_amendment_makes_a_new_version_and_old_terms_stay_unchanged():
    d = draft()
    d3 = d.amend(SetPounds("apples", "eastside", 50), proposer_id="eastside", reason="r")
    assert (d3.version, d3.based_on_version, d3.proposer_id) == (3, 2, "eastside")
    assert d3.pounds("apples", "eastside") == 50 and d.pounds("apples", "eastside") == 0

    d4 = d3.amend(ShiftPounds("apples", "rural", "eastside", 20), proposer_id="advocate", reason="r")
    assert (d4.pounds("apples", "rural"), d4.pounds("apples", "eastside")) == (230, 70)

    d5 = d4.amend(SetTransport("rural", Mover.DONOR, t("13:00"), t("13:40")), proposer_id="market", reason="r")
    assert d5.transport("rural").mover is Mover.DONOR

    with pytest.raises(DraftError):
        d5.amend(ShiftPounds("apples", "rural", "city", 999), proposer_id="advocate", reason="r")


def test_every_move_needs_a_reason():
    with pytest.raises(MoveError):
        Move("rural", Role.FOOD_BANK, 2, MoveKind.ACCEPT, reason="  ")


def test_a_counter_carries_exactly_one_amendment():
    with pytest.raises(MoveError):
        Move("rural", Role.FOOD_BANK, 2, MoveKind.COUNTER, reason="r")
    with pytest.raises(MoveError):
        Move("rural", Role.FOOD_BANK, 2, MoveKind.ACCEPT, reason="r", amendment=SetPounds("apples", "rural", 1))


@pytest.mark.parametrize("kind", [MoveKind.ACCEPT, MoveKind.REJECT, MoveKind.REQUEST_HOLD, MoveKind.ASK_HUMAN])
def test_the_advocate_can_never_accept_reject_hold_or_veto(kind):
    with pytest.raises(AdvocateCannotVote):
        Move("advocate", Role.ADVOCATE, 2, kind, reason="r")


def test_holds_are_only_on_the_organizations_own_resources():
    hold = HoldRequest("storage_cold", owner_id="city", pounds=200, start=t("14:30"), end=t("20:00"))
    Move("city", Role.FOOD_BANK, 2, MoveKind.REQUEST_HOLD, reason="r", holds=(hold,))
    with pytest.raises(MoveError):
        Move("rural", Role.FOOD_BANK, 2, MoveKind.REQUEST_HOLD, reason="r", holds=(hold,))


def test_accept_is_a_move_on_one_version_and_never_a_commitment():
    move = Move("rural", Role.FOOD_BANK, 2, MoveKind.ACCEPT, reason="fits")
    assert move.version == 2
    assert move.commits is False
    wire = move.to_dict()
    assert wire == {"organization_id": "rural", "version": 2, "action": "accept", "reason": "fits"}


def test_wire_shape_matches_the_lane_c_transport_proposal():
    hold = HoldRequest("truck", owner_id="city", pounds=200, start=t("14:00"), end=t("14:30"))
    wire = Move("city", Role.FOOD_BANK, 2, MoveKind.REQUEST_HOLD, reason="r", holds=(hold,)).to_dict()
    assert wire["action"] == "request_hold" and wire["resource_owner"] == "city"
    counter = Move("city", Role.FOOD_BANK, 2, MoveKind.COUNTER, reason="r", amendment=SetPounds("apples", "city", 5))
    assert counter.to_dict()["amendment"] == {"kind": "set_pounds", "produce_id": "apples", "food_bank_id": "city", "pounds": 5}


def test_parse_draft_round_trips_a_recorded_draft():
    raw = {
        "lot_id": "lot-1",
        "version": 1,
        "donor_id": "market",
        "deadline": "2026-10-13T15:00",
        "items": [{"produce_id": "apples", "pounds": 300, "condition_grade": "good", "usable_until": "2026-10-30T00:00"}],
        "allocations": [{"produce_id": "apples", "food_bank_id": "rural", "pounds": 100}],
        "transports": [{"food_bank_id": "rural", "mover": "donor", "departs_at": "2026-10-13T13:00", "arrives_at": "2026-10-13T13:40"}],
        "drop_off_to": ["rural"],
        "names": {"rural": "Rural food bank"},
    }
    d = parse_draft(raw)
    assert d.pounds("apples", "rural") == 100
    assert d.transport("rural").mover is Mover.DONOR
    assert d.name_of("rural") == "Rural food bank" and d.name_of("city") == "city"
