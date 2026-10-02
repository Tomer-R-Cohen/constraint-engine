import pandas as pd

from constraint_engine.constraints import Constraint
from constraint_engine.feasibility import analyze_feasibility


def make_df(n=30, flagged=10):
    return pd.DataFrame({"flag": [i <= flagged for i in range(1, n + 1)]}, index=range(1, n + 1))


def per_slot(lo, hi, hard=True, group=None):
    return Constraint(type="capacity", hard=hard, label="flag per slot",
                      args={"group": group or {"kind": "column", "column": "flag"}, "min": lo, "max": hi})


def test_feasible_range_reports_all_feasible():
    report = analyze_feasibility(make_df(flagged=18), [per_slot(3, 4)], 6)
    assert report.all_feasible()


def test_too_few_for_the_minimum_is_detected():
    # 6 slots need >= 3 each = 18, but only 5 are flagged.
    rule = per_slot(3, 4)
    report = analyze_feasibility(make_df(flagged=5), [rule], 6)
    assert [f.constraint_id for f in report.infeasible] == [rule.id]
    assert "18" in report.infeasible[0].message


def test_too_many_for_the_maximum_is_detected():
    # 6 slots allow at most 1 each = 6, but 10 are flagged.
    rule = per_slot(None, 1)
    report = analyze_feasibility(make_df(flagged=10), [rule], 6)
    assert [f.constraint_id for f in report.infeasible] == [rule.id]


def test_soft_rules_are_not_checked():
    report = analyze_feasibility(make_df(flagged=5), [per_slot(3, 4, hard=False)], 6)
    assert report.findings == []


def test_slot_size_feasibility():
    rule = per_slot(5, 6, group={"kind": "all"})
    report = analyze_feasibility(make_df(n=31), [rule], 6)
    assert report.findings[0].feasible


def test_fewer_entities_than_slots_is_reported():
    report = analyze_feasibility(make_df(n=4, flagged=2), [], 6)
    assert not report.all_feasible()
