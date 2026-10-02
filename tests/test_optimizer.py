import pandas as pd
import pytest

from constraint_engine.optimizer import OptimizationError, SolverConfig, optimize
from constraint_engine.rules import apart, fixed, flag, members, per_slot, share, spread, together, with_one_of


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


def friends(requests):
    """Friend requests as soft share rules: each requester with at least one."""
    return [with_one_of(e, asked, hard=False) for e, asked in requests.items()]


def base_constraints(requests=None):
    """Shibutzit's built-in rule set for this data, written as building blocks."""
    return [
        per_slot("class size 5-7", min=5, max=7),
        per_slot("differential", items=flag("differential"), max=1),
        per_slot("origin", items=flag("origin"), min=3, max=4),
        per_slot("inclusion", items=flag("inclusion"), min=2, max=2),
        per_slot("hamar", items=flag("hamar"), min=1, max=2),
        spread("level", item_groups={"column": "level"}, weight=2.0),
        spread("school", item_groups={"column": "school"}, weight=2.0),
        spread("current class", item_groups={"column": "current_class"}, weight=1.5),
        spread("categories", item_groups={"columns": ["differential", "origin", "inclusion", "hamar"]}, weight=1.0),
        *friends(requests or {}),
    ]


def slot_of(result, e):
    """The one slot an entity holds in a placement (one slot each)."""
    (slot,) = result.assignment[e]
    return slot


def counts_per_slot(df, result, column):
    counts = [0, 0]
    for e, flagged in df[column].items():
        if flagged:
            counts[slot_of(result, e)] += 1
    return counts


def test_all_entities_assigned_exactly_once():
    df = make_df()
    result = optimize(df, base_config(), base_constraints())
    assert result.is_feasible
    assert set(result.assignment) == set(df.index)
    assert all(slot_of(result, e) in (0, 1) for e in df.index)


def test_slot_size_balanced():
    df = make_df()
    result = optimize(df, base_config(), base_constraints())
    sizes = [sum(slot_of(result, e) == s for e in df.index) for s in range(2)]
    assert abs(sizes[0] - sizes[1]) <= 1


def test_count_range_respected():
    df = make_df()
    result = optimize(df, base_config(), base_constraints())
    assert all(3 <= c <= 4 for c in counts_per_slot(df, result, "origin"))


def test_count_exact():
    df = make_df()
    result = optimize(df, base_config(), base_constraints())
    assert counts_per_slot(df, result, "inclusion") == [2, 2]


def test_count_max_only():
    df = make_df()
    result = optimize(df, base_config(), base_constraints())
    assert all(c <= 1 for c in counts_per_slot(df, result, "differential"))


def test_fixed_assignment_respected():
    df = make_df()
    result = optimize(df, base_config(), base_constraints() + [fixed(1, 1)])
    assert result.is_feasible
    assert result.assignment[1] == [1]


def test_invalid_num_slots_raises():
    df = make_df()
    config = base_config()
    config.num_slots = 0
    with pytest.raises(OptimizationError):
        optimize(df, config, base_constraints())


def test_rule_naming_a_missing_slot_raises():
    with pytest.raises(OptimizationError):
        optimize(make_df(), base_config(), base_constraints() + [fixed(1, 5)])


def test_friend_requests_co_place_a_mutual_pair():
    df = make_df()
    # 11 & 12 are in no capacity group, so the reward is free to co-place them.
    result = optimize(df, base_config(), base_constraints(requests={11: [12], 12: [11]}))
    assert result.is_feasible
    assert result.assignment[11] == result.assignment[12]


def test_apart_hard_keeps_pair_apart():
    df = make_df()
    result = optimize(df, base_config(), base_constraints() + [apart(11, 12)])
    assert result.is_feasible
    assert result.assignment[11] != result.assignment[12]


def test_together_hard_forces_same_slot():
    df = make_df()
    result = optimize(df, base_config(), base_constraints() + [together(11, 12)])
    assert result.is_feasible
    assert result.assignment[11] == result.assignment[12]


def test_with_one_of_hard_satisfied():
    df = make_df()
    constraints = base_constraints() + [together(11, 12), with_one_of(10, [11, 12])]
    result = optimize(df, base_config(), constraints)
    assert result.is_feasible
    assert slot_of(result, 10) in (slot_of(result, 11), slot_of(result, 12))


def test_share_counts_how_many_of_a_list():
    # 4 per class, and 1 must share with exactly 2 of [2, 3, 4, 5].
    df = pd.DataFrame(index=range(1, 9))
    rule = share(1, [2, 3, 4, 5], "1 with exactly two", min=2, max=2)
    result = optimize(df, base_config(), [per_slot("size", min=4, max=4), rule])
    mine = slot_of(result, 1)
    assert sum(slot_of(result, e) == mine for e in (2, 3, 4, 5)) == 2


def test_string_entity_ids_work():
    df = pd.DataFrame({"night_ok": [True, False, True, False]}, index=["ana", "ben", "cy", "dee"])
    constraints = [
        per_slot("2 per slot", min=2, max=2),
        spread("night_ok even", items=flag("night_ok"), hard=True),
        together("ana", "ben"),
    ]
    result = optimize(df, SolverConfig(num_slots=2, time_limit_seconds=5), constraints)
    assert result.is_feasible
    assert result.assignment["ana"] == result.assignment["ben"] != result.assignment["cy"]


def test_hard_spread_by_column_forces_even_split_per_value():
    df = pd.DataFrame({"category": ["x", "x", "x", "x", "y", "y", "y", "y"]}, index=range(1, 9))
    config = SolverConfig(num_slots=2, time_limit_seconds=10, random_seed=1)
    constraints = [per_slot("size", min=4, max=4), spread("test", item_groups={"column": "category"}, hard=True)]
    result = optimize(df, config, constraints)
    assert result.is_feasible
    counts = {"x": [0, 0], "y": [0, 0]}
    for e, category in df["category"].items():
        counts[category][slot_of(result, e)] += 1
    assert counts == {"x": [2, 2], "y": [2, 2]}


def test_hard_spread_over_flag_columns_forces_even_split_per_column():
    df = pd.DataFrame(
        {
            "flag_a": [True, True, False, False, True, False, True, False],
            "flag_b": [False, True, True, False, False, True, False, True],
        },
        index=range(1, 9),
    )
    config = SolverConfig(num_slots=2, time_limit_seconds=10, random_seed=1)
    constraints = [per_slot("size", min=4, max=4), spread("test", item_groups={"columns": ["flag_a", "flag_b"]}, hard=True)]
    result = optimize(df, config, constraints)
    assert result.is_feasible
    assert counts_per_slot(df, result, "flag_a") == [2, 2]
    assert counts_per_slot(df, result, "flag_b") == [2, 2]


def test_conflict_set_extraction_identifies_contradictory_constraints():
    df = make_df()
    with_ = together(1, 2)
    without = apart(1, 2)
    result = optimize(df, base_config(), base_constraints() + [with_, without])
    assert not result.is_feasible
    assert with_.id in result.conflicting_constraint_ids
    assert without.id in result.conflicting_constraint_ids


def test_same_inputs_give_the_same_assignment():
    df = make_df()
    first = optimize(df, base_config(), base_constraints(requests={11: [12], 12: [11]}))
    second = optimize(df, base_config(), base_constraints(requests={11: [12], 12: [11]}))
    assert first.assignment == second.assignment


def test_weighted_count_sums_a_column():
    # Sizes 3, 3, 2, 2, 1, 1: each slot holds at most 6 of size.
    df = pd.DataFrame({"size": [3, 3, 2, 2, 1, 1]}, index=list("abcdef"))
    rule = per_slot("size per slot", weights={"items": df["size"].to_dict()}, max=6)
    result = optimize(df, SolverConfig(num_slots=2, time_limit_seconds=5), [rule])
    for s in range(2):
        assert sum(df.loc[e, "size"] for e, slots in result.assignment.items() if s in slots) <= 6


def test_fractional_weights_are_counted_exactly():
    # 7.5 + 8.25 = 15.75: a slot needing exactly 15.75 takes both; 15.74 is impossible.
    df = pd.DataFrame({"hours": [7.5, 8.25]}, index=["a", "b"])
    cfg = SolverConfig(num_slots=1, slots_per_entity=(0, 1), slots_interchangeable=False, time_limit_seconds=5)

    def hours(target):
        return per_slot("hours", weights={"items": df["hours"].to_dict()}, min=target, max=target)

    assert optimize(df, cfg, [hours(15.75)]).assignment == {"a": [0], "b": [0]}
    assert not optimize(df, cfg, [hours(15.74)]).is_feasible


def test_unknown_members_are_ignored():
    df = make_df()
    result = optimize(df, base_config(), base_constraints() + [per_slot("ghosts", items=members(99), max=0)])
    assert result.is_feasible
