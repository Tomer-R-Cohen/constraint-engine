import pandas as pd
import pytest

from constraint_engine.constraints import Constraint
from constraint_engine.optimizer import OptimizationError, SolverConfig, optimize


def make_df():
    """12 students for 2 classes, shaped like the Shibutzit sample data."""
    levels = ["high", "mid", "low"]
    schools = ["school a", "school b"]
    rows = {
        i: {
            "origin": i <= 7,
            "differential": i in (1, 2),
            "inclusion": i in (3, 4, 5, 6),
            "hamar": i in (8, 9, 10),
            "level": levels[i % 3],
            "school": schools[i % 2],
            "current_class": i % 4,
        }
        for i in range(1, 13)
    }
    return pd.DataFrame.from_dict(rows, orient="index")


def base_config(num_slots=2):
    return SolverConfig(num_slots=num_slots, time_limit_seconds=15, random_seed=42)


def cap(column, lo, hi):
    return Constraint(type="capacity", hard=True, label=f"{lo}-{hi} {column} per class",
                      args={"group": {"kind": "column", "column": column}, "min": lo, "max": hi})


def balance(group, weight):
    return Constraint(type="balance", hard=False, label="balance", args={"group": group, "weight": weight})


def base_constraints(requests=None):
    """Shibutzit's built-in rule set for this data, written out."""
    return [
        Constraint(type="capacity", hard=True, label="class size 5-7",
                   args={"group": {"kind": "all"}, "min": 5, "max": 7}),
        cap("differential", None, 1),
        cap("origin", 3, 4),
        cap("inclusion", 2, 2),
        cap("hamar", 1, 2),
        Constraint(type="partner_requests", hard=False, label="friend requests", args={"requests": requests or {}}),
        balance({"kind": "column_all_values", "column": "level"}, 2.0),
        balance({"kind": "column_all_values", "column": "school"}, 2.0),
        balance({"kind": "column_all_values", "column": "current_class"}, 1.5),
        balance({"kind": "columns", "columns": ["differential", "origin", "inclusion", "hamar"]}, 1.0),
    ]


def counts_per_slot(df, result, column):
    counts = [0, 0]
    for e, flagged in df[column].items():
        if flagged:
            counts[result.assignment[e]] += 1
    return counts


def test_all_entities_assigned_exactly_once():
    df = make_df()
    result = optimize(df, base_config(), base_constraints())
    assert result.is_feasible
    assert set(result.assignment) == set(df.index)
    assert all(0 <= s < 2 for s in result.assignment.values())


def test_slot_size_balanced():
    df = make_df()
    result = optimize(df, base_config(), base_constraints())
    sizes = [list(result.assignment.values()).count(s) for s in range(2)]
    assert abs(sizes[0] - sizes[1]) <= 1


def test_capacity_range_respected():
    df = make_df()
    result = optimize(df, base_config(), base_constraints())
    assert all(3 <= c <= 4 for c in counts_per_slot(df, result, "origin"))


def test_capacity_exact():
    df = make_df()
    result = optimize(df, base_config(), base_constraints())
    assert counts_per_slot(df, result, "inclusion") == [2, 2]


def test_capacity_max_only():
    df = make_df()
    result = optimize(df, base_config(), base_constraints())
    assert all(c <= 1 for c in counts_per_slot(df, result, "differential"))


def test_fixed_assignment_respected():
    df = make_df()
    constraints = base_constraints() + [Constraint(type="fixed", hard=True, label="1 in slot 2", args={"entity": 1, "slot": 1})]
    result = optimize(df, base_config(), constraints)
    assert result.is_feasible
    assert result.assignment[1] == 1


def test_invalid_num_slots_raises():
    df = make_df()
    config = base_config()
    config.num_slots = 0
    with pytest.raises(OptimizationError):
        optimize(df, config, base_constraints())


def test_fixed_to_nonexistent_slot_raises():
    df = make_df()
    constraints = base_constraints() + [Constraint(type="fixed", hard=True, label="1 in slot 6", args={"entity": 1, "slot": 5})]
    with pytest.raises(OptimizationError):
        optimize(df, base_config(), constraints)


def test_partner_requests_co_place_a_mutual_pair():
    df = make_df()
    # 11 & 12 are in no capacity group, so the reward is free to co-place them.
    result = optimize(df, base_config(), base_constraints(requests={11: [12], 12: [11]}))
    assert result.is_feasible
    assert result.assignment[11] == result.assignment[12]


def test_separate_hard_keeps_pair_apart():
    df = make_df()
    constraints = base_constraints() + [
        Constraint(type="separate", hard=True, args={"entity_a": 11, "entity_b": 12}, label="apart")
    ]
    result = optimize(df, base_config(), constraints)
    assert result.is_feasible
    assert result.assignment[11] != result.assignment[12]


def test_together_hard_forces_same_slot():
    df = make_df()
    constraints = base_constraints() + [
        Constraint(type="together", hard=True, args={"entity_a": 11, "entity_b": 12}, label="together")
    ]
    result = optimize(df, base_config(), constraints)
    assert result.is_feasible
    assert result.assignment[11] == result.assignment[12]


def test_at_least_one_of_hard_satisfied():
    df = make_df()
    constraints = base_constraints() + [
        Constraint(type="together", hard=True, args={"entity_a": 11, "entity_b": 12}, label="anchor pair"),
        Constraint(type="at_least_one_of", hard=True, args={"entity": 10, "candidates": [11, 12]}, label="10 with 11 or 12"),
    ]
    result = optimize(df, base_config(), constraints)
    assert result.is_feasible
    assert result.assignment[10] in (result.assignment[11], result.assignment[12])


def test_string_entity_ids_work():
    df = pd.DataFrame({"night_ok": [True, False, True, False]}, index=["ana", "ben", "cy", "dee"])
    constraints = [
        Constraint(type="capacity", hard=True, label="2 per slot", args={"group": {"kind": "all"}, "min": 2, "max": 2}),
        Constraint(type="balance", hard=True, label="night_ok even",
                   args={"group": {"kind": "column", "column": "night_ok"}}),
        Constraint(type="together", hard=True, label="ana with ben", args={"entity_a": "ana", "entity_b": "ben"}),
    ]
    result = optimize(df, SolverConfig(num_slots=2, time_limit_seconds=5), constraints)
    assert result.is_feasible
    assert result.assignment["ana"] == result.assignment["ben"] != result.assignment["cy"]


def test_balance_column_all_values_hard_forces_even_split_per_value():
    df = pd.DataFrame({"category": ["x", "x", "x", "x", "y", "y", "y", "y"]}, index=range(1, 9))
    config = SolverConfig(num_slots=2, time_limit_seconds=10, random_seed=1)
    constraints = [
        Constraint(type="capacity", hard=True, args={"group": {"kind": "all"}, "min": 4, "max": 4}, label="size"),
        Constraint(type="balance", hard=True, args={"group": {"kind": "column_all_values", "column": "category"}, "weight": 1.0},
                   label="test"),
    ]
    result = optimize(df, config, constraints)
    assert result.is_feasible
    counts = {"x": [0, 0], "y": [0, 0]}
    for e, category in df["category"].items():
        counts[category][result.assignment[e]] += 1
    assert counts == {"x": [2, 2], "y": [2, 2]}


def test_balance_columns_hard_forces_even_split_across_columns():
    df = pd.DataFrame(
        {
            "flag_a": [True, True, False, False, True, False, True, False],
            "flag_b": [False, True, True, False, False, True, False, True],
        },
        index=range(1, 9),
    )
    config = SolverConfig(num_slots=2, time_limit_seconds=10, random_seed=1)
    constraints = [
        Constraint(type="capacity", hard=True, args={"group": {"kind": "all"}, "min": 4, "max": 4}, label="size"),
        Constraint(type="balance", hard=True, args={"group": {"kind": "columns", "columns": ["flag_a", "flag_b"]}, "weight": 1.0},
                   label="test"),
    ]
    result = optimize(df, config, constraints)
    assert result.is_feasible
    assert counts_per_slot(df, result, "flag_a") == [2, 2]
    assert counts_per_slot(df, result, "flag_b") == [2, 2]


def test_conflict_set_extraction_identifies_contradictory_constraints():
    df = make_df()
    together = Constraint(type="together", hard=True, args={"entity_a": 1, "entity_b": 2}, label="together")
    separate = Constraint(type="separate", hard=True, args={"entity_a": 1, "entity_b": 2}, label="apart")
    result = optimize(df, base_config(), base_constraints() + [together, separate])
    assert not result.is_feasible
    assert together.id in result.conflicting_constraint_ids
    assert separate.id in result.conflicting_constraint_ids


def test_same_inputs_give_the_same_assignment():
    df = make_df()
    first = optimize(df, base_config(), base_constraints(requests={11: [12], 12: [11]}))
    second = optimize(df, base_config(), base_constraints(requests={11: [12], 12: [11]}))
    assert first.assignment == second.assignment
