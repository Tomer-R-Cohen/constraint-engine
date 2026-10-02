"""The problem spec: schema, read-backs, checks against data, and solving."""

import pandas as pd
import pytest
from pydantic import ValidationError

from constraint_engine.compiler import SpecError, check_spec, compile_spec, entity_table, solve_spec
from constraint_engine.optimizer import optimize
from constraint_engine.readback import describe_rule, describe_rule_body, describe_spec
from constraint_engine.spec import data_hash, dump_spec, load_spec, spec_hash

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
PER_SLOT = {"per_item": "all", "per_slot": "each"}
PER_ITEM = {"per_item": "each", "per_slot": "all"}


def roster_spec(**overrides) -> dict:
    spec = {
        "name": "ward roster",
        "vocabulary": {"entity": "employee", "entities": "employees", "slot": "shift", "slots": "shifts"},
        "entities": {"source": "staff.xlsx#Sheet1", "id_column": "Name"},
        "slots": [
            {"id": f"{day.lower()}-{shift[:2]}", "attributes": {"day": day, "shift": shift,
                                                                "hours": 8 if shift == "morning" else 10}}
            for day in DAYS for shift in ("morning", "night")
        ],
        "settings": {"slots_per_entity": [0, 14], "time_limit_seconds": 10},
        "rules": [
            {"id": "mornings", "type": "count", **PER_SLOT, "slots": {"where": {"shift": "morning"}}, "min": 2, "max": 2},
            {"id": "nights", "type": "count", **PER_SLOT, "slots": {"where": {"shift": "night"}}, "min": 1, "max": 1},
            {"id": "qualified", "type": "count", **PER_SLOT, "items": {"column": "Night qualified", "value": False},
             "slots": {"where": {"shift": "night"}}, "max": 0},
            {"id": "week", "type": "count", **PER_ITEM, "min": 3, "max": 6},
            {"id": "hours", "type": "count", **PER_ITEM, "sum": {"slot_attribute": "hours"}, "max": 50},
            {"id": "daily", "type": "count", "per_item": "each", "per_slot": {"attribute": "day"}, "max": 1},
            {"id": "ana-monday", "type": "count", **PER_ITEM, "items": {"members": ["Ana"]}, "slots": {"ids": ["mon-mo"]},
             "min": 1},
            {"id": "ben-cy", "type": "share", "item": "Ben", "with": ["Cy"], "max": 0},
            {"id": "dee-eli", "type": "share", "item": "Dee", "with": ["Eli"], "min": 1, "mode": "soft", "priority": "low"},
            {"id": "fair", "type": "count", **PER_ITEM, "even": "items", "mode": "soft"},
        ],
    }
    spec.update(overrides)
    return spec


def staff_sheet() -> pd.DataFrame:
    return pd.DataFrame({
        "Name": ["Ana", "Ben", "Cy", "Dee", "Eli"],
        "Night qualified": ["yes", "yes", "", "yes", ""],
        "Role": ["nurse", "nurse", "aide", "nurse", "aide"],
        "Friends": ["Ben", "Ana, Dee", "", "Ben", "Zed"],
        "Max hours": [40, 40, 24, 32, "lots"],
    })


def staff():
    spec = load_spec(roster_spec())
    return spec, entity_table(staff_sheet(), spec)


# ---------------------------------------------------------------- schema

@pytest.mark.parametrize("rule", [
    {"type": "share", "item": "Ana", "with": ["Ben"], "min": 1, "priority": "high"},  # priority on a hard rule
    {"type": "count", **PER_SLOT, "min": 3, "max": 2},  # reversed band
    {"type": "count", **PER_SLOT},  # no target at all
    {"type": "count", "per_slot": "each", "max": 2},  # grouping must be stated
    {"type": "count", **PER_SLOT, "max": 2, "max_gap": 1},  # gap without even
    {"type": "count", **PER_SLOT, "max": 2, "colour": "red"},  # unknown field
    {"type": "count", **PER_SLOT, "max": 1, "items": {"members": ["Ana"], "column": "Role"}},  # mixed selector
    {"type": "count", **PER_SLOT, "max": 1, "sum": {"item_column": "a", "slot_attribute": "b"}},  # two sums
    {"type": "share", "item": "Ana", "min": 1},  # nobody to share with
    {"type": "share", "item": "Ana", "with": ["Ben"], "with_column": "Friends", "min": 1},  # two forms
    {"type": "teleport"},  # unknown rule type
])
def test_malformed_rules_are_rejected(rule):
    with pytest.raises(ValidationError):
        load_spec(roster_spec(rules=[rule]))


def test_duplicate_ids_are_rejected():
    rule = {"type": "count", **PER_SLOT, "max": 1}
    with pytest.raises(ValidationError):
        load_spec(roster_spec(rules=[{"id": "x", **rule}, {"id": "x", **rule}]))


def test_spec_round_trips_through_json():
    spec = load_spec(roster_spec())
    text = dump_spec(spec)
    assert '"with"' in text and '"with_"' not in text
    again = load_spec(text)
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
        "Each employee has at most 50 hours. Mandatory.",
        "Each employee has at most 1 shift per day. Mandatory.",
        "Ana has shift mon-mo. Mandatory.",
        "Ben and Cy never share a shift. Mandatory.",
        "Dee and Eli share at least one shift. Preference, low priority.",
        "Give each employee a similar number of shifts. Preference, medium priority.",
    ]


def test_read_backs_follow_one_slot_wording_and_switches():
    spec = load_spec({
        "vocabulary": {"entity": "student", "entities": "students", "slot": "class", "slots": "classes"},
        "slots": [{"id": "7A"}, {"id": "7B"}],
        "rules": [
            {"type": "share", "item": 1, "with": [2], "min": 1, "active": False},
            {"type": "count", "per_item": {"column": "School"}, "per_slot": "each", "even": "slots", "mode": "soft"},
            {"type": "share", "item": 3, "with": [4, 5], "min": 1},
            {"type": "count", **PER_SLOT, "slots": {"ids": ["7A"]}, "items": {"column": "Support"}, "min": 1},
            {"type": "share", "with_column": "Friends", "min": 1, "mode": "soft"},
            {"type": "count", **PER_SLOT, "min": 25, "max": 28},
        ],
    })
    assert describe_spec(spec) == [
        "Each student has exactly 1 class.",
        "1 and 2 are in the same class. Switched off.",
        "Spread the students of each School evenly across the classes. Preference, medium priority.",
        "3 is in the same class as at least 1 of 4 and 5. Mandatory.",
        "Class 7A has at least 1 student marked Support. Mandatory.",
        "Each student is in the same class as at least 1 of the students named in Friends. Preference, medium priority.",
        "Every class has between 25 and 28 students. Mandatory.",
    ]


# ------------------------------------------------------- checks against data

def test_every_problem_is_reported_at_once():
    spec = load_spec(roster_spec(rules=[
        {"id": "a", "type": "count", **PER_SLOT, "items": {"column": "Shoe size"}, "max": 1},
        {"id": "b", "type": "count", **PER_SLOT, "items": {"column": "Role"}, "max": 1},
        {"id": "c", "type": "count", **PER_SLOT, "items": {"column": "Role", "value": "doctor"}, "max": 1},
        {"id": "d", "type": "share", "item": "Ana", "with": ["Zed"], "max": 0},
        {"id": "e", "type": "count", **PER_ITEM, "slots": {"ids": ["mon-evening"]}, "min": 1},
        {"id": "f", "type": "count", "per_item": "each", "per_slot": {"attribute": "week"}, "max": 5},
        {"id": "g", "type": "count", **PER_SLOT, "slots": {"where": {"shift": "evening"}}, "max": 1},
        {"id": "h", "type": "share", "item": "Ana", "with": ["Ana"], "min": 1},
        {"id": "i", "type": "count", **PER_ITEM, "sum": {"item_column": "Max hours"}, "max": 40},
        {"id": "j", "type": "share", "with_column": "Friends", "min": 1},
    ]))
    _, df = staff()
    problems = check_spec(spec, df)
    assert [p.split(":")[0] for p in problems] == [f"Rule {r}" for r in "abcdefghij"]
    assert "no column 'Shoe size'" in problems[0]
    assert "not a yes/no column" in problems[1] and "aide, nurse" in problems[1]
    assert "no row has Role = doctor" in problems[2] and "aide, nurse" in problems[2]
    assert "no entity 'Zed'" in problems[3]
    assert "no slot 'mon-evening'" in problems[4]
    assert "attribute 'week'" in problems[5] and "day, hours, shift" in problems[5]
    assert "matches no slot" in problems[6]
    assert "named twice" in problems[7]
    assert "non-negative number" in problems[8] and "Eli" in problems[8]
    assert "no entity 'Zed'" in problems[9]
    with pytest.raises(SpecError):
        compile_spec(spec, df)


def test_entity_references_match_ids_of_either_type():
    spec = load_spec({"slots": [{"id": "A"}, {"id": "B"}],
                      "rules": [{"id": "pair", "type": "share", "item": "1", "with": [2], "min": 1}]})
    problem = compile_spec(spec, pd.DataFrame(index=[1, 2, 3]))
    assert problem.constraints[0].args["cases"] == [{"item": 1, "with": [2], "min": 1, "max": None}]


def test_unknown_id_column_is_reported():
    with pytest.raises(SpecError):
        entity_table(staff_sheet(), load_spec(roster_spec(entities={"id_column": "Employee"})))


# ---------------------------------------------------------------- compiling

def test_each_spec_rule_becomes_one_engine_rule_with_its_id_and_read_back():
    spec, df = staff()
    problem = compile_spec(spec, df)
    assert [c.id for c in problem.constraints] == [r.id for r in spec.rules]
    # Engine labels are the rule text without its status, for use inside
    # exceptions and trade-offs; the full read-back adds the status.
    assert [c.label for c in problem.constraints] == [describe_rule_body(r, spec) for r in spec.rules]
    assert all(describe_rule(r, spec).startswith(describe_rule_body(r, spec)) for r in spec.rules)
    by_id = {c.id: c for c in problem.constraints}
    assert by_id["daily"].args["slot_groups"] == [[2 * d, 2 * d + 1] for d in range(7)]
    assert by_id["daily"].args["slot_group_labels"][0] == "day Mon"
    assert by_id["qualified"].args["items"] == {"kind": "column_value", "column": "Night qualified", "value": False}
    assert by_id["qualified"].args["slots"] == list(range(1, 14, 2))
    assert by_id["hours"].args["weights"] == {"slots": [8.0, 10.0] * 7}
    assert by_id["dee-eli"].args["weight"] == pytest.approx(5.0 / 3)


def test_friend_column_becomes_one_case_per_requester():
    spec = load_spec(roster_spec(rules=[{"id": "friends", "type": "share", "with_column": "Friends", "min": 1,
                                         "items": {"column": "Role", "value": "nurse"}}]))
    _, df = staff()
    (rule,) = compile_spec(spec, df).constraints
    assert rule.args["cases"] == [
        {"item": "Ana", "with": ["Ben"], "min": 1, "max": None},
        {"item": "Ben", "with": ["Ana", "Dee"], "min": 1, "max": None},
        {"item": "Dee", "with": ["Ben"], "min": 1, "max": None},
    ]


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
    assert all(sum(8 if s.endswith("mo") else 10 for s in shifts) <= 50 for shifts in roster.values())


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
        {"id": "nights", "type": "count", **PER_SLOT, "slots": {"where": {"shift": "night"}}, "min": 2, "max": 2},
        {"id": "qualified", "type": "count", **PER_SLOT, "items": {"column": "Night qualified", "value": False},
         "slots": {"where": {"shift": "night"}}, "max": 0},
        {"id": "two-nights", "type": "count", **PER_ITEM, "slots": {"where": {"shift": "night"}}, "max": 2},
    ]))
    df = entity_table(staff_sheet(), spec)
    result = solve_spec(spec, df, time_budget_seconds=15)

    assert result["mode"] == "compromise"
    assert set(result["conflicting_rule_ids"]) <= {"nights", "qualified", "two-nights"}
    exceptions = [item for option in result["options"] for item in option["exceptions"]]
    assert exceptions
    assert all(isinstance(slot, str) for item in exceptions for slot in item["slots"])
