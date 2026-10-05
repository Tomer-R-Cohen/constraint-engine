"""The workspace behind the tools: data -> slots -> rules -> solve -> look up."""

import os

import pandas as pd
import pytest

from constraint_engine.spec import CountRule, ShareRule, StretchRule, TransitionRule, load_spec
from constraint_engine.workspace import Workspace, WorkspaceError


@pytest.fixture
def staff_csv(tmp_path):
    path = tmp_path / "staff.csv"
    pd.DataFrame({
        "Name": ["Ana", "Ben", "Cy", "Dee", "Eli"],
        "Night qualified": ["yes", "yes", "", "yes", ""],
        "Role": ["nurse", "nurse", "aide", "nurse", "aide"],
    }).to_csv(path, index=False)
    return str(path)


def roster(ws, path):
    loaded = ws.load_data(path, id_column="Name", name="ward")
    pid = loaded["problem_id"]
    ws.set_slots(pid, grid={"day": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "shift": ["morning", "night"]},
                 vocabulary={"entity": "employee", "entities": "employees", "slot": "shift", "slots": "shifts"},
                 slots_per_item=(0, 14))
    return pid


def rule(**fields):
    kind = {"count": CountRule, "share": ShareRule, "stretch": StretchRule, "transition": TransitionRule}[fields["type"]]
    return kind.model_validate(fields)


def test_load_data_describes_columns(staff_csv):
    ws = Workspace()
    loaded = ws.load_data(staff_csv, id_column="Name")
    assert loaded["items"] == 5 and loaded["id_column"] == "Name" and not loaded["id_column_guessed"]
    kinds = {c["name"]: c["kind"] for c in loaded["columns"]}
    assert kinds == {"Night qualified": "flag", "Role": "category"}


def test_grid_slots_and_read_back(staff_csv):
    ws = Workspace()
    pid = roster(ws, staff_csv)
    assert ws.list_rules(pid) == {"settings": "Each employee has at most 14 shifts.", "rules": []}
    assert ws.problems[pid].slots[1].id == "Mon-night"
    assert ws.problems[pid].slots[1].attributes == {"day": "Mon", "shift": "night"}


def test_rules_are_checked_against_the_data_when_added(staff_csv):
    ws = Workspace()
    pid = roster(ws, staff_csv)
    added = ws.add_rule(pid, rule(type="count", per_item="all", per_slot="each",
                                  slots={"where": {"shift": "night"}}, min=1, max=1))
    assert added["read_back"] == "Every shift where shift is night has exactly 1 employee. Mandatory."
    with pytest.raises(WorkspaceError, match="no column 'Shoe size'"):
        ws.add_rule(pid, rule(type="count", per_item="all", per_slot="each", items={"column": "Shoe size"}, max=1))
    assert len(ws.list_rules(pid)["rules"]) == 1  # the bad rule was not kept


def test_full_round_lookup_and_export(staff_csv, tmp_path):
    ws = Workspace()
    pid = roster(ws, staff_csv)
    for fields in [
        dict(type="count", per_item="all", per_slot="each", slots={"where": {"shift": "morning"}}, min=2, max=2),
        dict(type="count", per_item="all", per_slot="each", slots={"where": {"shift": "night"}}, min=1, max=1),
        dict(type="count", per_item="all", per_slot="each", items={"column": "Night qualified", "value": False},
             slots={"where": {"shift": "night"}}, max=0),
        dict(type="count", per_item="each", per_slot="all", min=3, max=6),
        dict(type="count", per_item="each", per_slot={"attribute": "day"}, max=1),
        dict(id="rest", type="transition", per="day", after={"where": {"shift": "night"}},
             not_followed_by={"where": {"shift": "morning"}}),
        dict(type="share", item="Ben", **{"with": ["Cy"]}, max=0),
    ]:
        ws.add_rule(pid, rule(**fields))

    summary = ws.solve(pid, time_budget_seconds=15)
    assert summary["mode"] == "perfect"
    assert len(summary["options"]) == 3
    first = summary["options"][0]
    assert first["option_id"] == "round-1/option-1" and first["meets_every_mandatory_rule"]
    assert set(summary["record"]) == {"spec_hash", "data_hash", "engine_version", "seed", "created_at"}

    whole = ws.get_option(pid, first["option_id"])["assignment"]
    assert set(whole) == {"Ana", "Ben", "Cy", "Dee", "Eli"}
    ben = ws.get_option(pid, first["option_id"], item="Ben")
    assert ben["slots"] == whole["Ben"]
    on_monday_night = ws.get_option(pid, first["option_id"], slot="Mon-night")["items"]
    assert len(on_monday_night) == 1

    out = tmp_path / "roster.xlsx"
    ws.export_option(pid, first["option_id"], str(out))
    by_item = pd.read_excel(out, sheet_name="By item")
    by_slot = pd.read_excel(out, sheet_name="By slot")
    assert list(by_item["Name"]) == ["Ana", "Ben", "Cy", "Dee", "Eli"]
    assert by_slot.set_index("Slot").loc["Mon-morning", "Count"] == 2

    refined = ws.solve(pid, time_budget_seconds=15, refine_option=first["option_id"])
    assert refined["round_id"] == "round-2"
    assert all(o["items_moved_from_base"] is not None for o in refined["options"])


def test_conflicts_are_reported_with_read_backs(staff_csv):
    ws = Workspace()
    pid = roster(ws, staff_csv)
    ws.add_rule(pid, rule(id="two-nights", type="count", per_item="all", per_slot="each",
                          slots={"where": {"shift": "night"}}, min=2, max=2))
    ws.add_rule(pid, rule(id="qualified", type="count", per_item="all", per_slot="each",
                          items={"column": "Night qualified", "value": False}, slots={"where": {"shift": "night"}}, max=0))
    ws.add_rule(pid, rule(id="few-nights", type="count", per_item="each", per_slot="all",
                          slots={"where": {"shift": "night"}}, max=2))
    summary = ws.solve(pid, time_budget_seconds=15)
    assert summary["mode"] == "compromise"
    assert summary["conflicting_rules"]
    assert all(r["read_back"].endswith("Mandatory.") for r in summary["conflicting_rules"])
    assert all(o["exceptions"] for o in summary["options"])


def test_spec_round_trip_and_switching_rules(staff_csv):
    ws = Workspace()
    pid = roster(ws, staff_csv)
    ws.add_rule(pid, rule(id="streak", type="stretch", per="day", max=5))
    off = ws.set_rule_active(pid, "streak", False)
    assert off["read_back"].endswith("Switched off.")
    saved = ws.get_spec(pid)
    assert load_spec(saved).rules[0].active is False

    other = ws.load_data(staff_csv, id_column="Name")["problem_id"]
    listed = ws.set_spec(other, saved)
    assert [r["rule_id"] for r in listed["rules"]] == ["streak"]
    ws.remove_rule(other, "streak")
    assert ws.list_rules(other)["rules"] == []


def test_unknown_things_are_named(staff_csv):
    ws = Workspace()
    with pytest.raises(WorkspaceError, match="no problem"):
        ws.list_rules("nope")
    pid = roster(ws, staff_csv)
    with pytest.raises(WorkspaceError, match="no rule"):
        ws.remove_rule(pid, "nope")
    with pytest.raises(WorkspaceError, match="no option"):
        ws.get_option(pid, "round-9/option-1")
    with pytest.raises(WorkspaceError, match="not found"):
        ws.load_data("missing.csv")


def test_schedule_tables_are_built_from_the_assignment(staff_csv):
    ws = Workspace()
    pid = roster(ws, staff_csv)
    ws.add_rule(pid, rule(type="count", per_item="all", per_slot="each", min=1, max=1))
    option = ws.solve(pid, time_budget_seconds=10)["options"][0]["option_id"]
    shown = ws.get_option(pid, option)
    assignment = shown["assignment"]

    # A day x shift grid: one row per day, one column per shift.
    lines = shown["table_by_slot"].splitlines()
    assert lines[0] == "| day | morning | night |"
    assert len(lines) == 2 + 7
    for line, day in zip(lines[2:], ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        cells = [c.strip() for c in line.strip("|").split("|")]
        assert cells[0] == day
        for cell, shift in zip(cells[1:], ["morning", "night"]):
            expected = [e for e, slots in assignment.items() if f"{day}-{shift}" in slots]
            assert cell.split(", ") == expected

    by_item = shown["table_by_item"].splitlines()
    assert by_item[0] == "| Item | Slots |" and len(by_item) == 2 + 5
    assert by_item[2] == f"| Ana | {', '.join(assignment['Ana']) or '—'} |"


def test_schedule_table_lists_slots_when_they_are_not_a_grid(staff_csv):
    ws = Workspace()
    pid = ws.load_data(staff_csv, id_column="Name")["problem_id"]
    ws.set_slots(pid, grid={"class": ["A", "B"]})
    option = ws.solve(pid, time_budget_seconds=5)["options"][0]["option_id"]
    lines = ws.get_option(pid, option)["table_by_slot"].splitlines()
    assert lines[0] == "| Slot | Count | Items |"
    assert sum(int(line.split("|")[2]) for line in lines[2:]) == 5


def test_problems_survive_a_restart(staff_csv, tmp_path):
    store = str(tmp_path / "store")
    ws = Workspace(store)
    pid = roster(ws, staff_csv)
    ws.add_rule(pid, rule(id="nights", type="count", per_item="all", per_slot="each",
                          slots={"where": {"shift": "night"}}, min=1, max=1))
    ws.add_rule(pid, rule(id="rest", type="count", per_item="each", per_slot="all", max=5, mode="soft", priority="high"))
    ws.set_rule_active(pid, "rest", False)
    option_id = ws.solve(pid, time_budget_seconds=10)["options"][0]["option_id"]
    before = ws.get_option(pid, option_id)
    os.remove(staff_csv)  # the stored copy is used, not the original

    restarted = Workspace(store)
    assert restarted.list_rules(pid) == ws.list_rules(pid)
    assert restarted.get_spec(pid) == ws.get_spec(pid)
    assert restarted.get_option(pid, option_id) == before
    assert restarted.describe_data(pid) == ws.describe_data(pid)
    refined = restarted.solve(pid, time_budget_seconds=10, refine_option=option_id)
    assert refined["round_id"] == "round-2"
    assert len(Workspace(store).problems[pid].rounds) == 2


def test_without_a_store_nothing_is_written(staff_csv, tmp_path):
    ws = Workspace()
    roster(ws, staff_csv)
    assert sorted(os.listdir(tmp_path)) == ["staff.csv"]
