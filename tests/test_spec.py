"""The problem spec: schema, read-backs, checks against data, and solving."""

import pandas as pd
import pytest
from pydantic import ValidationError

from constraint_engine.compiler import SpecError, check_spec, compile_spec, entity_table, solve_spec
from constraint_engine.optimizer import optimize
from constraint_engine.readback import describe_rule, describe_spec
from constraint_engine.spec import data_hash, dump_spec, load_spec, spec_hash

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def roster_spec(**overrides) -> dict:
    spec = {
        "name": "ward roster",
        "vocabulary": {"entity": "employee", "entities": "employees", "slot": "shift", "slots": "shifts"},
        "entities": {"source": "staff.xlsx#Sheet1", "id_column": "Name"},
        "slots": [
            {"id": f"{day.lower()}-{shift[:2]}", "attributes": {"day": day, "shift": shift}}
            for day in DAYS for shift in ("morning", "night")
        ],
        "settings": {"slots_per_entity": [0, 14], "time_limit_seconds": 10},
        "rules": [
            {"id": "mornings", "type": "capacity", "slots": {"where": {"shift": "morning"}}, "min": 2, "max": 2},
            {"id": "nights", "type": "capacity", "slots": {"where": {"shift": "night"}}, "min": 1, "max": 1},
            {"id": "qualified", "type": "capacity", "entities": {"column": "Night qualified", "value": False},
             "slots": {"where": {"shift": "night"}}, "max": 0},
            {"id": "week", "type": "load", "min": 3, "max": 6},
            {"id": "daily", "type": "load", "per": "day", "max": 1},
            {"id": "ana-monday", "type": "fixed", "entity": "Ana", "slot": "mon-mo"},
            {"id": "ben-cy", "type": "separate", "entity_a": "Ben", "entity_b": "Cy"},
            {"id": "dee-eli", "type": "together", "entity_a": "Dee", "entity_b": "Eli", "mode": "soft", "priority": "low"},
        ],
    }
    spec.update(overrides)
    return spec


def staff_sheet() -> pd.DataFrame:
    return pd.DataFrame({
        "Name": ["Ana", "Ben", "Cy", "Dee", "Eli"],
        "Night qualified": ["yes", "yes", "", "yes", ""],
        "Role": ["nurse", "nurse", "aide", "nurse", "aide"],
    })


def staff():
    spec = load_spec(roster_spec())
    return spec, entity_table(staff_sheet(), spec)


# ---------------------------------------------------------------- schema

@pytest.mark.parametrize("rule", [
    {"type": "together", "entity_a": "Ana", "entity_b": "Ben", "priority": "high"},  # priority on a hard rule
    {"type": "capacity", "min": 3, "max": 2},  # reversed band
    {"type": "load"},  # no band at all
    {"type": "balance"},  # nothing to balance
    {"type": "balance", "by_column": "Role", "flag_columns": ["Night qualified"]},  # two targets
    {"type": "capacity", "max": 2, "colour": "red"},  # unknown field
    {"type": "teleport"},  # unknown rule type
    {"type": "capacity", "max": 1, "entities": {"members": ["Ana"], "column": "Role"}},  # mixed selector
])
def test_malformed_rules_are_rejected(rule):
    with pytest.raises(ValidationError):
        load_spec(roster_spec(rules=[rule]))


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValidationError):
        load_spec(roster_spec(rules=[{"id": "x", "type": "load", "max": 1}, {"id": "x", "type": "load", "max": 2}]))


def test_spec_round_trips_through_json():
    spec = load_spec(roster_spec())
    again = load_spec(dump_spec(spec))
    assert again == spec
    assert spec_hash(again) == spec_hash(spec)


# ------------------------------------------------------------- read-backs

def test_read_backs_are_plain_english_from_templates():
    spec = load_spec(roster_spec())
    assert describe_spec(spec) == [
        "Each employee has at most 14 shifts.",
        "Every shift where shift is morning has exactly 2 employees. Mandatory.",
        "Every shift where shift is night has exactly 1 employee. Mandatory.",
        "Every shift where shift is night has no employees whose Night qualified is no. Mandatory.",
        "Each employee has between 3 and 6 shifts. Mandatory.",
        "Each employee has at most 1 shift per day. Mandatory.",
        "Ana has shift mon-mo. Mandatory.",
        "Ben and Cy never share a shift. Mandatory.",
        "Dee and Eli share at least one shift. Preference, low priority.",
    ]


def test_read_backs_follow_one_slot_wording_and_switches():
    spec = load_spec({
        "vocabulary": {"entity": "student", "entities": "students", "slot": "class", "slots": "classes"},
        "slots": [{"id": "7A"}, {"id": "7B"}],
        "rules": [
            {"type": "together", "entity_a": 1, "entity_b": 2, "active": False},
            {"type": "balance", "by_column": "School", "mode": "soft"},
            {"type": "at_least_one_of", "entity": 3, "candidates": [4, 5]},
            {"type": "capacity", "slots": {"ids": ["7A"]}, "entities": {"column": "Support"}, "min": 1},
        ],
    })
    assert describe_spec(spec) == [
        "Each student has exactly 1 class.",
        "1 and 2 are in the same class. Switched off.",
        "Spread students evenly across the classes by School. Preference, medium priority.",
        "3 is in the same class as at least one of 4 or 5. Mandatory.",
        "Class 7A has at least 1 student marked Support. Mandatory.",
    ]


# ------------------------------------------------------- checks against data

def test_every_problem_is_reported_at_once():
    spec = load_spec(roster_spec(rules=[
        {"id": "a", "type": "capacity", "entities": {"column": "Shoe size"}, "max": 1},
        {"id": "b", "type": "capacity", "entities": {"column": "Role"}, "max": 1},
        {"id": "c", "type": "capacity", "entities": {"column": "Role", "value": "doctor"}, "max": 1},
        {"id": "d", "type": "separate", "entity_a": "Ana", "entity_b": "Zed"},
        {"id": "e", "type": "fixed", "entity": "Ana", "slot": "mon-evening"},
        {"id": "f", "type": "load", "per": "week", "max": 5},
        {"id": "g", "type": "capacity", "slots": {"where": {"shift": "evening"}}, "max": 1},
        {"id": "h", "type": "together", "entity_a": "Ana", "entity_b": "Ana"},
    ]))
    _, df = staff()
    problems = check_spec(spec, df)
    assert [p.split(":")[0] for p in problems] == [f"Rule {r}" for r in "abcdefgh"]
    assert "no column 'Shoe size'" in problems[0]
    assert "not a yes/no column" in problems[1] and "aide, nurse" in problems[1]
    assert "no row has Role = doctor" in problems[2] and "aide, nurse" in problems[2]
    assert "no entity 'Zed'" in problems[3]
    assert "no slot 'mon-evening'" in problems[4]
    assert "attribute 'week'" in problems[5] and "day, shift" in problems[5]
    assert "matches no slot" in problems[6]
    with pytest.raises(SpecError):
        compile_spec(spec, df)


def test_entity_references_match_ids_of_either_type():
    spec = load_spec({"slots": [{"id": "A"}, {"id": "B"}],
                      "rules": [{"id": "pair", "type": "together", "entity_a": "1", "entity_b": 2}]})
    df = pd.DataFrame(index=[1, 2, 3])
    problem = compile_spec(spec, df)
    assert problem.constraints[0].args == {"entity_a": 1, "entity_b": 2}


def test_unknown_id_column_is_reported():
    with pytest.raises(SpecError):
        entity_table(staff_sheet(), load_spec(roster_spec(entities={"id_column": "Employee"})))


# ---------------------------------------------------------------- compiling

def test_each_spec_rule_becomes_one_engine_rule_with_its_id_and_read_back():
    spec, df = staff()
    problem = compile_spec(spec, df)
    assert [c.id for c in problem.constraints] == [r.id for r in spec.rules]
    assert [c.label for c in problem.constraints] == [describe_rule(r, spec) for r in spec.rules]
    daily = next(c for c in problem.constraints if c.id == "daily")
    assert daily.args["slot_groups"] == [[2 * d, 2 * d + 1] for d in range(7)]
    qualified = next(c for c in problem.constraints if c.id == "qualified")
    assert qualified.args["group"] == {"kind": "column_value", "column": "Night qualified", "value": False}
    assert qualified.args["slots"] == list(range(1, 14, 2))
    soft = next(c for c in problem.constraints if c.id == "dee-eli")
    assert soft.args["weight"] == pytest.approx(5.0 / 3)


def test_compiled_roster_solves_and_keeps_every_rule():
    spec, df = staff()
    problem = compile_spec(spec, df)
    result = optimize(problem.df, problem.config, problem.constraints)
    assert result.is_feasible
    roster = problem.named(result.assignment)
    for day in DAYS:
        morning, night = f"{day.lower()}-mo", f"{day.lower()}-ni"
        assert sum(morning in shifts for shifts in roster.values()) == 2
        on_night = [e for e, shifts in roster.items() if night in shifts]
        assert len(on_night) == 1 and on_night[0] in {"Ana", "Ben", "Dee"}
        assert all(not {morning, night} <= set(shifts) for shifts in roster.values())
    assert "mon-mo" in roster["Ana"]
    assert all(3 <= len(shifts) <= 6 for shifts in roster.values())


def test_solve_spec_returns_options_in_spec_terms_with_a_record():
    spec, df = staff()
    first = solve_spec(spec, df, time_budget_seconds=15)
    second = solve_spec(spec, df, time_budget_seconds=15)

    assert first["mode"] == "perfect"
    assert len(first["options"]) == 3
    assert first["spec_hash"] == spec_hash(spec) and first["data_hash"] == data_hash(df)
    assert first["seed"] == 42
    option = first["options"][0]
    assert set(option["assignment"]) == {"Ana", "Ben", "Cy", "Dee", "Eli"}
    assert all(slot in {s.id for s in spec.slots} for shifts in option["assignment"].values() for slot in shifts)
    assert {check["constraint_id"] for check in option["verification"]["checks"]} >= {r.id for r in spec.rules}
    # Same spec, same data, same seed: the same options.
    assert [o["assignment"] for o in first["options"]] == [o["assignment"] for o in second["options"]]


def test_conflicts_point_at_spec_rule_ids_and_name_slots():
    spec = load_spec(roster_spec(rules=[
        {"id": "nights", "type": "capacity", "slots": {"where": {"shift": "night"}}, "min": 2, "max": 2},
        {"id": "qualified", "type": "capacity", "entities": {"column": "Night qualified", "value": False},
         "slots": {"where": {"shift": "night"}}, "max": 0},
        {"id": "two-nights", "type": "load", "slots": {"where": {"shift": "night"}}, "max": 2},
    ]))
    df = entity_table(staff_sheet(), spec)
    result = solve_spec(spec, df, time_budget_seconds=15)

    assert result["mode"] == "compromise"
    assert set(result["conflicting_rule_ids"]) <= {"nights", "qualified", "two-nights"}
    exceptions = [item for option in result["options"] for item in option["exceptions"]]
    assert exceptions
    assert all(isinstance(slot, str) for item in exceptions for slot in item["slots"])
