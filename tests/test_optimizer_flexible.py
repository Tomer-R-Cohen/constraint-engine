import pandas as pd

from constraint_engine.optimizer import SolverConfig, optimize
from constraint_engine.rules import apart, flag, per_slot, together


def _df(n, **cols):
    return pd.DataFrame(cols or None, index=range(1, n + 1))


def test_flexible_count_bends_by_the_minimum_amount():
    # 5 flagged entities, 2 slots, at most 2 per slot: impossible by one.
    df = _df(10, flag=[True] * 5 + [False] * 5)
    cap = per_slot("flag cap", items=flag("flag"), max=2)
    cfg = SolverConfig(num_slots=2, time_limit_seconds=5)

    assert not optimize(df, cfg, [cap]).is_feasible
    result = optimize(df, cfg, [cap], flexible_constraint_ids={cap.id})

    assert result.is_feasible
    counts = sorted(sum(1 for e in range(1, 6) if result.assignment[e] == [c]) for c in range(2))
    assert counts == [2, 3]  # exactly one entity over, not the rule dropped


def test_flexible_rule_keeps_other_hard_rules_enforced():
    df = _df(4)
    size = per_slot("two per slot", min=2, max=2)
    with_ = together(1, 2)
    without = apart(1, 2)
    result = optimize(df, SolverConfig(num_slots=2, time_limit_seconds=5), [size, with_, without],
                      flexible_constraint_ids={without.id})

    assert result.is_feasible
    assert result.assignment[1] == result.assignment[2]
    assert sorted(list(result.assignment.values()).count([c]) for c in range(2)) == [2, 2]


def test_anchor_keeps_entities_in_place_when_nothing_else_matters():
    df = _df(6)
    size = per_slot("three per slot", min=3, max=3)
    anchor = {1: [1], 2: [0], 3: [1], 4: [0], 5: [1], 6: [0]}
    result = optimize(df, SolverConfig(num_slots=2, time_limit_seconds=5), [size],
                      anchor_assignment=anchor, anchor_weight=1.0)
    assert result.assignment == anchor


def test_soft_count_prefers_staying_inside_the_range():
    # Nothing forces it, but the preference puts exactly one entity on each slot.
    df = _df(2)
    prefer = per_slot("one per slot", min=1, max=1, hard=False)
    cfg = SolverConfig(num_slots=2, slots_per_entity=(0, 2), time_limit_seconds=5)
    result = optimize(df, cfg, [prefer])
    assert sorted(s for slots in result.assignment.values() for s in slots) == [0, 1]
