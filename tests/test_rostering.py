"""Several slots per entity: a small shift roster.

Slots are (day, shift) cells numbered day * 2 + shift, shift 0 = morning,
1 = night.
"""

import pandas as pd
import pytest

from constraint_engine.constraints import Constraint
from constraint_engine.decision_support import assignment_distance, generate_portfolio, verify_assignment
from constraint_engine.feasibility import analyze_feasibility
from constraint_engine.optimizer import OptimizationError, SolverConfig, optimize

DAYS = 7
MORNINGS = [2 * d for d in range(DAYS)]
NIGHTS = [2 * d + 1 for d in range(DAYS)]
ALL = {"kind": "all"}


def staff():
    return pd.DataFrame(
        {"night_ok": [True, True, False, True, False]},
        index=["ana", "ben", "cy", "dee", "eli"],
    )


def roster_config(**kwargs):
    return SolverConfig(num_slots=2 * DAYS, slots_per_entity=(0, 2 * DAYS), time_limit_seconds=10, **kwargs)


def roster_rules():
    rules = [
        Constraint(type="capacity", hard=True, label="2 on every morning",
                   args={"group": ALL, "min": 2, "max": 2, "slots": MORNINGS}),
        Constraint(type="capacity", hard=True, label="1 on every night",
                   args={"group": ALL, "min": 1, "max": 1, "slots": NIGHTS}),
        Constraint(type="capacity", hard=True, label="nights only for night-qualified staff",
                   args={"group": {"kind": "column_value", "column": "night_ok", "value": False}, "max": 0, "slots": NIGHTS}),
        Constraint(type="load", hard=True, label="3-6 shifts a week", args={"group": ALL, "min": 3, "max": 6}),
        Constraint(type="fixed", hard=True, label="ana works Monday morning", args={"entity": "ana", "slot": 0}),
        Constraint(type="separate", hard=True, label="ben and cy never on the same shift",
                   args={"entity_a": "ben", "entity_b": "cy"}),
    ]
    rules += [
        Constraint(type="load", hard=True, label=f"one shift on day {d + 1}",
                   args={"group": ALL, "max": 1, "slots": [2 * d, 2 * d + 1]})
        for d in range(DAYS)
    ]
    return rules


def test_roster_meets_coverage_loads_and_rules():
    df = staff()
    rules = roster_rules()
    result = optimize(df, roster_config(), rules)
    assert result.is_feasible
    roster = result.assignment

    for slot in range(2 * DAYS):
        on_shift = [e for e, slots in roster.items() if slot in slots]
        assert len(on_shift) == (2 if slot in MORNINGS else 1)
        if slot in NIGHTS:
            assert all(df.loc[e, "night_ok"] for e in on_shift)
    for e, slots in roster.items():
        assert 3 <= len(slots) <= 6
        assert all(not {2 * d, 2 * d + 1} <= set(slots) for d in range(DAYS))
    assert 0 in roster["ana"]
    assert not set(roster["ben"]) & set(roster["cy"])

    report = verify_assignment(df, roster, rules, 2 * DAYS, (0, 2 * DAYS))
    assert report.is_valid, report.summary


def test_together_means_sharing_at_least_one_slot():
    df = pd.DataFrame(index=["a", "b"])
    rules = [
        Constraint(type="fixed", hard=True, label="a on 0", args={"entity": "a", "slot": 0}),
        Constraint(type="fixed", hard=True, label="b on 1", args={"entity": "b", "slot": 1}),
        Constraint(type="together", hard=True, label="a with b", args={"entity_a": "a", "entity_b": "b"}),
    ]
    result = optimize(df, SolverConfig(num_slots=3, slots_per_entity=(1, 2), time_limit_seconds=5), rules)
    assert result.is_feasible
    assert set(result.assignment["a"]) & set(result.assignment["b"])
    assert verify_assignment(df, result.assignment, rules, 3, (1, 2)).is_valid


def test_flexible_load_bends_by_the_minimum_amount():
    # 3 slots each need one person, but 2 people may work 1 slot each.
    df = pd.DataFrame(index=["a", "b"])
    cover = Constraint(type="capacity", hard=True, label="1 per slot", args={"group": ALL, "min": 1, "max": 1})
    load = Constraint(type="load", hard=True, label="at most 1 slot", args={"group": ALL, "max": 1})
    cfg = SolverConfig(num_slots=3, slots_per_entity=(0, 3), time_limit_seconds=5)

    assert not optimize(df, cfg, [cover, load]).is_feasible
    result = optimize(df, cfg, [cover, load], flexible_constraint_ids={load.id})
    assert result.is_feasible
    assert sorted(len(slots) for slots in result.assignment.values()) == [1, 2]

    check = verify_assignment(df, result.assignment, [cover, load], 3, (0, 3)).checks[-1]
    assert (check.status, check.shortfall, check.affected_entities) == ("violated", 1, [
        e for e, slots in result.assignment.items() if len(slots) == 2
    ])


def test_soft_load_is_a_preference():
    df = pd.DataFrame(index=["a", "b"])
    cover = Constraint(type="capacity", hard=True, label="1 per slot", args={"group": ALL, "min": 1, "max": 1})
    prefer = Constraint(type="load", hard=False, label="a works exactly 1", args={"group": {"kind": "members", "members": ["a"]}, "min": 1, "max": 1})
    result = optimize(df, SolverConfig(num_slots=4, slots_per_entity=(0, 4), time_limit_seconds=5), [cover, prefer])
    assert len(result.assignment["a"]) == 1
    assert len(result.assignment["b"]) == 3


def test_roster_options_differ_and_renamed_shifts_count_as_different():
    df = staff()
    options, conflicts = generate_portfolio(df, roster_config(), roster_rules(), time_budget_seconds=15)
    assert conflicts == []
    assert len(options) == 3
    assert all(option.verification.is_valid for option in options)
    for i, a in enumerate(options):
        for b in options[i + 1:]:
            assert assignment_distance(a.assignment, b.assignment, 2 * DAYS, interchangeable=False) > 0

    swapped = {"a": [1], "b": [0]}
    assert assignment_distance({"a": [0], "b": [1]}, swapped, 2, interchangeable=False) == 2
    assert assignment_distance({"a": [0], "b": [1]}, swapped, 2, interchangeable=True) == 0


def test_interchangeable_slots_need_one_slot_each():
    with pytest.raises(OptimizationError):
        optimize(pd.DataFrame(index=[1, 2]), SolverConfig(num_slots=2, slots_per_entity=(0, 2), slots_interchangeable=True), [])


def test_rule_naming_a_missing_slot_raises():
    rule = Constraint(type="capacity", hard=True, label="slot 9", args={"group": ALL, "min": 1, "slots": [8]})
    with pytest.raises(OptimizationError):
        optimize(pd.DataFrame(index=[1, 2]), SolverConfig(num_slots=2, slots_per_entity=(0, 2)), [rule])


def test_feasibility_counts_slot_places_not_people():
    # 3 slots need 2 each = 6 places, but 2 people work at most 2 slots = 4.
    df = pd.DataFrame(index=["a", "b"])
    cover = Constraint(type="capacity", hard=True, label="2 per slot", args={"group": ALL, "min": 2})
    load = Constraint(type="load", hard=True, label="at most 2", args={"group": ALL, "max": 2})
    report = analyze_feasibility(df, [cover, load], 3, (0, 3))
    assert [f.constraint_id for f in report.infeasible] == [cover.id]

    roomy = analyze_feasibility(df, [cover], 3, (0, 3))
    assert roomy.all_feasible()


def test_feasibility_flags_a_load_the_band_cannot_reach():
    df = pd.DataFrame(index=["a"])
    load = Constraint(type="load", hard=True, label="at least 4", args={"group": ALL, "min": 4})
    report = analyze_feasibility(df, [load], 3, (0, 3))
    assert [f.constraint_id for f in report.infeasible] == [load.id]
