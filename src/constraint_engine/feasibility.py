"""Pre-solve feasibility analysis for hard 'capacity' rules.

Only capacity-type hard rules have a simple closed-form arithmetic pre-check
(total group size vs. k*min / k*max) worth doing before invoking the solver.
Everything else (pairwise separate/together, at-least-one-of, and any
interaction between several hard rules) has no such closed form --
infeasibility there is only knowable by actually solving, and is explained
afterward via the solver's own conflict-set extraction (see
`OptimizationResult.conflicting_constraint_ids`) rather than pre-checked here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from constraint_engine import text
from constraint_engine.constraints import Constraint, resolve_group_members


@dataclass
class FeasibilityFinding:
    rule: str
    feasible: bool
    message: str
    constraint_id: str = ""


@dataclass
class FeasibilityReport:
    findings: list[FeasibilityFinding] = field(default_factory=list)

    def add(self, rule: str, feasible: bool, message: str, constraint_id: str = "") -> None:
        self.findings.append(FeasibilityFinding(rule, feasible, message, constraint_id))

    @property
    def infeasible(self) -> list[FeasibilityFinding]:
        return [f for f in self.findings if not f.feasible]

    def all_feasible(self) -> bool:
        return len(self.infeasible) == 0


def analyze_feasibility(df: pd.DataFrame, constraints: list[Constraint], num_slots: int) -> FeasibilityReport:
    """Check whether population totals can possibly satisfy each active,
    hard "capacity" rule, independent of the solver and of any other rule
    (no cross-rule interaction is considered here).

    Returns a FeasibilityReport listing each checked rule as feasible or
    not, with the arithmetic spelled out.
    """
    report = FeasibilityReport()
    n = len(df)
    k = num_slots

    if k < 1:
        report.add(text.FEAS_NO_SLOTS, False, text.NUM_SLOTS_TOO_SMALL)
        return report

    if n < k:
        report.add(text.FEAS_FEWER_ENTITIES_THAN_SLOTS_RULE, False, text.FEAS_FEWER_ENTITIES_THAN_SLOTS.format(n=n, k=k))

    for c in constraints:
        if not c.active or not c.hard or c.type != "capacity":
            continue
        total = len(resolve_group_members(df, c.args["group"]))
        lo = c.args.get("min")
        hi = c.args.get("max")
        ok = True
        parts = [text.FEAS_GROUP_TOTAL.format(total=total)]
        if lo is not None:
            needed = k * lo
            ok = ok and total >= needed
            parts.append(text.FEAS_NEED_AT_LEAST.format(needed=needed, lo=lo, k=k))
        if hi is not None:
            capacity = k * hi
            ok = ok and total <= capacity
            parts.append(text.FEAS_ROOM_FOR_AT_MOST.format(capacity=capacity, hi=hi, k=k))
        report.add(c.label, ok, " ".join(parts), constraint_id=c.id)

    return report
