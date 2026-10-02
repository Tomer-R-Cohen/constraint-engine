"""Pre-solve feasibility analysis for hard capacity and load rules.

Only capacity and load hard rules have a simple closed-form arithmetic
pre-check (how many slot places the group can fill vs. slots*min / slots*max)
worth doing before invoking the solver.
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
from constraint_engine.constraints import Constraint, load_slot_groups, resolve_group_members, selected_slots


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


def _holding_bounds(load_rules: list[tuple[Constraint, set]], members: set, slots: set, num_slots: int,
                    slots_per_entity: tuple[int, int]) -> tuple[dict, dict]:
    """For each member, the fewest and most of `slots` it can hold, from the
    slots-per-entity band and the given (rule, its members) hard load rules."""
    load_min, load_max = slots_per_entity
    low = {e: max(0, load_min - (num_slots - len(slots))) for e in members}
    high = {e: min(load_max, len(slots)) for e in members}
    for c, rule_members in load_rules:
        groups = [set(group) for group in load_slot_groups(c.args, num_slots)]
        covered = set().union(*groups)
        disjoint = sum(len(group) for group in groups) == len(covered)
        lo, hi = c.args.get("min"), c.args.get("max")
        # Within each group the rule allows lo..hi; slots outside every
        # group are unconstrained by it.
        most = sum(min(hi, len(slots & group)) for group in groups) + len(slots - covered) if hi is not None else None
        least_each = [max(0, lo - len(group - slots)) for group in groups] if lo is not None else []
        fewest = (sum(least_each) if disjoint else max(least_each, default=0)) if lo is not None else None
        for e in rule_members & members:
            if most is not None:
                high[e] = min(high[e], most)
            if fewest is not None:
                low[e] = max(low[e], fewest)
    return low, high


def analyze_feasibility(df: pd.DataFrame, constraints: list[Constraint], num_slots: int,
                        slots_per_entity: tuple[int, int] = (1, 1)) -> FeasibilityReport:
    """Check whether population totals can possibly satisfy each active,
    hard "capacity" and "load" rule, independent of the solver and of any
    other rule except the slots-per-entity band and hard load rules (which
    bound how many slots anyone can hold).

    Returns a FeasibilityReport listing each checked rule as feasible or
    not, with the arithmetic spelled out.
    """
    report = FeasibilityReport()
    n = len(df)
    k = num_slots
    single = tuple(slots_per_entity) == (1, 1)

    if k < 1:
        report.add(text.FEAS_NO_SLOTS, False, text.NUM_SLOTS_TOO_SMALL)
        return report

    if single and n < k:
        report.add(text.FEAS_FEWER_ENTITIES_THAN_SLOTS_RULE, False, text.FEAS_FEWER_ENTITIES_THAN_SLOTS.format(n=n, k=k))

    hard = [c for c in constraints if c.active and c.hard and c.type in ("capacity", "load")]
    members_by_id = {c.id: set(resolve_group_members(df, c.args["group"])) for c in hard}
    load_rules = [(c, members_by_id[c.id]) for c in hard if c.type == "load"]

    for c in hard:
        members = members_by_id[c.id]
        slots = selected_slots(c.args, k)
        lo = c.args.get("min")
        hi = c.args.get("max")
        ok = True
        if c.type == "load":
            # Each member on its own, in each slot group: the band and the
            # other load rules must leave room for this one.
            parts = []
            for group in load_slot_groups(c.args, k):
                low, high = _holding_bounds(load_rules, members, set(group), k, slots_per_entity)
                if lo is not None and any(high[e] < lo for e in members):
                    ok = False
                    parts.append(text.FEAS_LOAD_MIN_UNREACHABLE.format(lo=lo, most=min(high.values())))
                if hi is not None and any(low[e] > hi for e in members):
                    ok = False
                    parts.append(text.FEAS_LOAD_MAX_UNREACHABLE.format(hi=hi, fewest=max(low.values())))
                if not ok:
                    break
            report.add(c.label, ok, " ".join(parts) or text.FEAS_LOAD_OK, constraint_id=c.id)
            continue
        low, high = _holding_bounds(load_rules, members, set(slots), k, slots_per_entity)
        count = len(slots)
        if single:
            parts = [text.FEAS_GROUP_TOTAL.format(total=len(members))]
        else:
            parts = [text.FEAS_GROUP_PLACES.format(most=sum(high.values()), fewest=sum(low.values()), count=count)]
        if lo is not None:
            needed = count * lo
            ok = ok and sum(high.values()) >= needed
            parts.append(text.FEAS_NEED_AT_LEAST.format(needed=needed, lo=lo, k=count))
        if hi is not None:
            capacity = count * hi
            ok = ok and sum(low.values()) <= capacity
            parts.append(text.FEAS_ROOM_FOR_AT_MOST.format(capacity=capacity, hi=hi, k=count))
        report.add(c.label, ok, " ".join(parts), constraint_id=c.id)

    return report
