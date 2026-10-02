"""Rules over time: stretch lengths (run) and rest between slots (transition)."""

import pandas as pd
import pytest

from constraint_engine.compiler import compile_spec, entity_table, solve_spec
from constraint_engine.constraints import Constraint
from constraint_engine.decision_support import stretches, verify_assignment
from constraint_engine.optimizer import SolverConfig, optimize
from constraint_engine.spec import load_spec

ALL = {"kind": "all"}
WEEK = [[d] for d in range(7)]  # one slot per day


def one_person_week(*rules, flexible=()):
    df = pd.DataFrame(index=["a"])
    cfg = SolverConfig(num_slots=7, slots_per_entity=(0, 7), time_limit_seconds=5)
    result = optimize(df, cfg, list(rules), flexible_constraint_ids=set(flexible))
    return df, result


def days(n):
    return Constraint(type="load", hard=True, label=f"{n} days", args={"group": ALL, "min": n, "max": n})


def run(**args):
    return Constraint(type="run", hard=args.pop("hard", True), label="run", args={"group": ALL, "units": WEEK, **args})


def test_stretches_helper():
    assert stretches([True, True, False, True], True) == [(0, 2), (3, 1)]
    assert stretches([True, True, False, True], False) == [(2, 1)]
    assert stretches([], True) == []


def test_max_stretch_forces_a_break():
    _, result = one_person_week(days(6), run(max=5))
    worked = [d in result.assignment["a"] for d in range(7)]
    assert result.is_feasible
    assert max(length for _, length in stretches(worked, True)) <= 5


def test_impossible_stretch_is_traced_to_both_rules():
    load, limit = days(7), run(max=5)
    _, result = one_person_week(load, limit)
    assert not result.is_feasible
    assert set(result.conflicting_constraint_ids) == {load.id, limit.id}


def test_short_stretches_are_allowed_only_at_the_edges():
    # 6 of 7 days with days off in stretches of at least 2: the single day
    # off cannot sit in the middle of the week.
    _, result = one_person_week(days(6), run(of="off", min=2))
    off = [d for d in range(7) if d not in result.assignment["a"]]
    assert off in ([0], [6])


def test_flexible_stretch_bends_and_the_verifier_counts_it():
    load, limit = days(7), run(max=5)
    df, result = one_person_week(load, limit, flexible=[limit.id])
    assert result.is_feasible
    check = verify_assignment(df, result.assignment, [load, limit], 7, (0, 7)).checks[-1]
    assert (check.status, check.shortfall, check.affected_entities) == ("violated", 1, ["a"])


def test_soft_stretch_is_kept_when_it_can_be():
    _, result = one_person_week(days(4), run(max=2, hard=False))
    worked = [d in result.assignment["a"] for d in range(7)]
    assert max(length for _, length in stretches(worked, True)) <= 2


def test_transition_keeps_rest_after_a_night():
    # Two days, morning (0, 2) and night (1, 3). Each slot needs one person.
    df = pd.DataFrame(index=["ana", "ben"])
    rules = [
        Constraint(type="capacity", hard=True, label="cover", args={"group": ALL, "min": 1, "max": 1}),
        Constraint(type="fixed", hard=True, label="ana Mon night", args={"entity": "ana", "slot": 1}),
        Constraint(type="fixed", hard=True, label="ben Mon morning", args={"entity": "ben", "slot": 0}),
        Constraint(type="transition", hard=True, label="rest", args={"group": ALL, "pairs": [[1, 2]]}),
    ]
    result = optimize(df, SolverConfig(num_slots=4, slots_per_entity=(0, 4), time_limit_seconds=5), rules)
    assert result.is_feasible
    assert 2 not in result.assignment["ana"] and 2 in result.assignment["ben"]
    assert verify_assignment(df, result.assignment, rules, 4, (0, 4)).is_valid


def test_transition_violations_are_reported_with_slot_names():
    df = pd.DataFrame(index=["ana"])
    rule = Constraint(type="transition", hard=True, label="rest", args={"group": ALL, "pairs": [[1, 2]]})
    report = verify_assignment(df, {"ana": [1, 2]}, [rule], 4, (0, 4), ["mon-mo", "mon-ni", "tue-mo", "tue-ni"])
    check = report.checks[-1]
    assert (check.status, check.shortfall) == ("violated", 1)
    assert check.actual == {"ana": [["mon-ni", "tue-mo"]]}


# ------------------------------------------------------------------- spec

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def week_spec(rules, staff_range=(0, 14)):
    return load_spec({
        "vocabulary": {"entity": "employee", "entities": "employees", "slot": "shift", "slots": "shifts"},
        "entities": {"id_column": "Name"},
        "slots": [{"id": f"{d.lower()}-{s[:2]}", "attributes": {"day": d, "shift": s}}
                  for d in DAYS for s in ("morning", "night")],
        "settings": {"slots_per_entity": list(staff_range), "time_limit_seconds": 10},
        "rules": rules,
    })


def test_spec_compiles_time_units_and_pairs():
    spec = week_spec([
        {"id": "nights", "type": "run", "per": "day", "max": 2, "slots": {"where": {"shift": "night"}}},
        {"id": "rest", "type": "transition", "per": "day", "after": {"where": {"shift": "night"}},
         "not_followed_by": {"where": {"shift": "morning"}}},
        {"id": "long-rest", "type": "transition", "per": "day", "within": 2, "after": {"where": {"shift": "night"}},
         "not_followed_by": {}},
    ])
    problem = compile_spec(spec, pd.DataFrame(index=["Ana"]))
    nights, rest, long_rest = problem.constraints
    assert nights.args["units"] == [[2 * d + 1] for d in range(7)]
    assert rest.args["pairs"] == [[2 * d + 1, 2 * d + 2] for d in range(6)]
    # Night of day d forbids both shifts of days d+1 and d+2.
    assert [1, 2] in long_rest.args["pairs"] and [1, 5] in long_rest.args["pairs"] and [1, 6] not in long_rest.args["pairs"]


def test_roster_with_time_rules_solves_and_keeps_every_rule():
    raw = pd.DataFrame({"Name": ["Ana", "Ben", "Cy", "Dee", "Eli"]})
    spec = week_spec([
        {"id": "cover", "type": "capacity", "min": 1, "max": 1},
        {"id": "daily", "type": "load", "per": "day", "max": 1},
        {"id": "week", "type": "load", "min": 2, "max": 4},
        {"id": "streak", "type": "run", "per": "day", "max": 2},
        {"id": "nights", "type": "run", "per": "day", "max": 1, "slots": {"where": {"shift": "night"}}},
        {"id": "rest", "type": "transition", "per": "day", "after": {"where": {"shift": "night"}},
         "not_followed_by": {"where": {"shift": "morning"}}},
    ])
    df = entity_table(raw, spec)
    result = solve_spec(spec, df, time_budget_seconds=20)
    assert result["mode"] == "perfect" and result["options"]

    for option in result["options"]:
        assert option["verification"]["is_valid"]
        for shifts in option["assignment"].values():
            held = set(shifts)
            worked = [bool(held & {f"{d.lower()}-mo", f"{d.lower()}-ni"}) for d in DAYS]
            nights = [f"{d.lower()}-ni" in held for d in DAYS]
            assert max((n for _, n in stretches(worked, True)), default=0) <= 2
            assert max((n for _, n in stretches(nights, True)), default=0) <= 1
            for today, tomorrow in zip(DAYS, DAYS[1:]):
                assert not {f"{today.lower()}-ni", f"{tomorrow.lower()}-mo"} <= held


@pytest.mark.parametrize("rule", [
    {"type": "run", "max": 2},  # no time unit
    {"type": "run", "per": "day"},  # no band
    {"type": "transition", "per": "day", "after": {}},  # nothing forbidden
    {"type": "transition", "per": "day", "after": {}, "not_followed_by": {}, "within": 0},
])
def test_malformed_time_rules_are_rejected(rule):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        week_spec([rule])
