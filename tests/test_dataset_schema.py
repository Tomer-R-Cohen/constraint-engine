"""Spreadsheet columns: what kind each one is, and whether a rule about one
reaches the solver meaning what it says."""

import pandas as pd
import pytest

from constraint_engine.constraints import resolve_group_members
from constraint_engine.dataset_schema import classify_series, describe_columns, guess_id_column, prepare_entities
from constraint_engine.optimizer import SolverConfig, optimize
from constraint_engine.rules import flag, per_slot


@pytest.mark.parametrize(
    "values,expected",
    [
        (["yes", "", "yes", ""], "flag"),
        (["כן", "", "כן", ""], "flag"),
        ([1, 0, 1, 0], "flag"),
        (["V", "", "V"], "flag"),
        (["north", "south", "north"], "category"),
        ([3.5, 2.0, 4.25], "number"),
        ([f"note number {i}" for i in range(40)], None),  # free text
        (["", "", ""], None),  # empty
        ([0, 0, 0], None),  # nobody flagged -> describes no subgroup
        (["yes", "yes", "yes"], None),  # everybody flagged -> same
        (["north", "north", "north"], None),  # a constant, not a category
    ],
)
def test_classify_series(values, expected):
    kind, _values, _true = classify_series(pd.Series(values))
    assert kind == expected


def test_describe_skips_id_layout_and_note_columns():
    raw = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "Unnamed: 3": [1, 0, 1],
            "Notes": ["long free text " + str(i) for i in range(3)],
            "Twins": ["yes", "", "yes"],
            "Area": ["north", "south", "north"],
        }
    )
    schema = describe_columns(raw, skip={"id"})

    assert schema.names() == ["Twins", "Area"]
    assert schema.get("Twins").kind == "flag"
    assert schema.get("Twins").true_count == 2
    assert schema.get("Area").kind == "category"
    assert set(schema.get("Area").values) == {"north", "south"}


def test_guess_id_column_prefers_unique_integers():
    raw = pd.DataFrame({"name": ["a", "b", "c"], "group": [1, 1, 2], "number": [7, 3, 9]})
    assert guess_id_column(raw) == "number"
    assert guess_id_column(raw.drop(columns="number")) is None


def test_flag_columns_become_real_booleans():
    """The bug this prevents: any non-empty string is truthy in Python, so
    leaving a column of "yes"/"" as strings would make resolve_group_members
    match every entity, silently."""
    raw = pd.DataFrame({"id": [11, 12, 13, 14], "Twins": ["yes", "", "yes", None]})
    out = prepare_entities(raw, describe_columns(raw, skip={"id"}), id_column="id")

    assert out["Twins"].tolist() == [True, False, True, False]
    members = resolve_group_members(out, {"kind": "column", "column": "Twins"})
    assert members == [11, 13], "only the flagged entities belong to the group"


def test_rows_are_numbered_when_there_is_no_id_column():
    raw = pd.DataFrame({"Twins": ["yes", "", "yes"]})
    out = prepare_entities(raw, describe_columns(raw))
    assert out.index.tolist() == [1, 2, 3]


def test_duplicate_ids_are_refused():
    raw = pd.DataFrame({"id": [1, 1, 2], "Twins": ["yes", "", "yes"]})
    with pytest.raises(ValueError):
        prepare_entities(raw, describe_columns(raw, skip={"id"}), id_column="id")


def test_a_rule_on_a_spreadsheet_column_reaches_the_solver():
    raw = pd.DataFrame({"name": ["a", "b", "c", "d"], "Twins": ["yes", "", "yes", ""]})
    df = prepare_entities(raw, describe_columns(raw), id_column="name")
    rule = per_slot("at most 1 twin per slot", items=flag("Twins"), max=1)
    result = optimize(df, SolverConfig(num_slots=2, time_limit_seconds=5), [rule])
    assert result.assignment["a"] != result.assignment["c"]
