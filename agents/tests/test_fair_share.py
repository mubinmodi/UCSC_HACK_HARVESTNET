"""Fair-share table (ticket #12). Values are the placeholder table from docs/MVP_DESIGN.md section 4."""

import inspect

import pytest

from harvestnet_agents.fair_share import FairShareError, fair_share, load_fair_share_table


@pytest.mark.parametrize(
    ("household_size", "pounds"),
    [(1, 4), (2, 7), (3, 10), (4, 12)],
)
def test_published_sizes(household_size, pounds):
    assert fair_share(household_size).pounds == pounds


@pytest.mark.parametrize(
    ("household_size", "pounds"),
    [(5, 14), (6, 16), (9, 22)],
)
def test_two_pounds_per_extra_person_above_four(household_size, pounds):
    assert fair_share(household_size).pounds == pounds


@pytest.mark.parametrize("household_size", [0, -1])
def test_household_size_must_be_at_least_one(household_size):
    with pytest.raises(FairShareError):
        fair_share(household_size)


def test_household_size_must_be_a_whole_number():
    with pytest.raises(FairShareError):
        fair_share(2.5)  # type: ignore[arg-type]
    with pytest.raises(FairShareError):
        fair_share(True)  # type: ignore[arg-type]


def test_table_is_versioned_and_labeled_placeholder():
    table = load_fair_share_table()
    assert table.version
    assert table.is_placeholder
    assert "placeholder" in table.note.lower()
    assert table.unit == "lb"
    assert table.period == "week"


def test_result_carries_table_version_and_placeholder_flag():
    result = fair_share(4)
    table = load_fair_share_table()
    assert result.table_version == table.version
    assert result.is_placeholder is True
    assert result.household_size == 4


def test_fair_share_depends_only_on_household_size():
    # MVP_DESIGN section 4: SNAP participation never changes the fair share.
    assert list(inspect.signature(fair_share).parameters) == ["household_size", "table"]


def test_custom_table_can_be_passed_in():
    table = load_fair_share_table(
        {
            "kind": "fair_share_table",
            "version": "test-1",
            "status": "placeholder",
            "note": "Placeholder for a test.",
            "unit": "lb",
            "period": "week",
            "pounds_by_household_size": {"1": 5, "2": 9},
            "each_additional_person_lb": 3,
        }
    )
    assert fair_share(1, table).pounds == 5
    assert fair_share(4, table).pounds == 15
    assert fair_share(4, table).table_version == "test-1"


def test_table_with_gaps_is_rejected():
    with pytest.raises(FairShareError):
        load_fair_share_table(
            {
                "kind": "fair_share_table",
                "version": "bad",
                "status": "placeholder",
                "note": "Placeholder.",
                "unit": "lb",
                "period": "week",
                "pounds_by_household_size": {"1": 4, "3": 10},
                "each_additional_person_lb": 2,
            }
        )


def test_table_without_version_is_rejected():
    with pytest.raises(FairShareError):
        load_fair_share_table(
            {
                "kind": "fair_share_table",
                "status": "placeholder",
                "note": "Placeholder.",
                "unit": "lb",
                "period": "week",
                "pounds_by_household_size": {"1": 4},
                "each_additional_person_lb": 2,
            }
        )
