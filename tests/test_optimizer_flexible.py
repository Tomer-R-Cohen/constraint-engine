import pandas as pd

from constraint_engine.constraints import Constraint
from constraint_engine.optimizer import SolverConfig, optimize


def _df(n, **cols):
    return pd.DataFrame(cols or None, index=range(1, n + 1))


def test_flexible_capacity_bends_by_the_minimum_amount():
    # 5 flagged entities, 2 slots, at most 2 per slot: impossible by one.
    df = _df(10, flag=[True] * 5 + [False] * 5)
    cap = Constraint(type="capacity", hard=True, label="flag cap",
                     args={"group": {"kind": "column", "column": "flag"}, "max": 2})
    cfg = SolverConfig(num_slots=2, time_limit_seconds=5)

    assert not optimize(df, cfg, [cap]).is_feasible
    result = optimize(df, cfg, [cap], flexible_constraint_ids={cap.id})

    assert result.is_feasible
    counts = sorted(sum(1 for e in range(1, 6) if result.assignment[e] == [c]) for c in range(2))
    assert counts == [2, 3]  # exactly one entity over, not the rule dropped


def test_flexible_rule_keeps_other_hard_rules_enforced():
    df = _df(4)
    size = Constraint(type="capacity", hard=True, label="two per slot",
                      args={"group": {"kind": "all"}, "min": 2, "max": 2})
    together = Constraint(type="together", hard=True, label="together", args={"entity_a": 1, "entity_b": 2})
    separate = Constraint(type="separate", hard=True, label="separate", args={"entity_a": 1, "entity_b": 2})
    result = optimize(df, SolverConfig(num_slots=2, time_limit_seconds=5), [size, together, separate],
                      flexible_constraint_ids={separate.id})

    assert result.is_feasible
    assert result.assignment[1] == result.assignment[2]
    assert sorted(list(result.assignment.values()).count([c]) for c in range(2)) == [2, 2]


def test_anchor_keeps_entities_in_place_when_nothing_else_matters():
    df = _df(6)
    size = Constraint(type="capacity", hard=True, label="three per slot",
                      args={"group": {"kind": "all"}, "min": 3, "max": 3})
    anchor = {1: [1], 2: [0], 3: [1], 4: [0], 5: [1], 6: [0]}
    result = optimize(df, SolverConfig(num_slots=2, time_limit_seconds=5), [size],
                      anchor_assignment=anchor, anchor_weight=1.0)
    assert result.assignment == anchor
