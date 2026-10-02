"""Pre-solve feasibility analysis for hard count rules.

Only plain count rules (per slot or per item, no weights, no evenness) have
a simple closed-form arithmetic pre-check worth doing before invoking the
solver.
Everything else (share, stretch, transition, and any interaction between
several hard rules) has no such closed form --
infeasibility there is only knowable by actually solving, and is explained
afterward via the solver's own conflict-set extraction (see
`OptimizationResult.conflicting_constraint_ids`) rather than pre-checked here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from constraint_engine import text
from constraint_engine.constraints import Constraint, resolve_group_members, slot_groups


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


def _is_plain_count(c: Constraint, grouping: str) -> bool:
    """A hard count of placements (no weights, no evenness) per item
    ("each") or over all items ("all") -- the shapes with closed-form checks."""
    return (c.active and c.hard and c.type == "count" and not c.args.get("weights") and not c.args.get("even")
            and c.args.get("item_groups", "all") == grouping)


def _holding_bounds(per_item_rules: list[tuple[Constraint, set]], members: set, slots: set, num_slots: int,
                    slots_per_entity: tuple[int, int]) -> tuple[dict, dict]:
    """For each member, the fewest and most of `slots` it can hold, from the
    slots-per-entity band and the given (rule, its members) hard per-item
    count rules."""
    load_min, load_max = slots_per_entity
    low = {e: max(0, load_min - (num_slots - len(slots))) for e in members}
    high = {e: min(load_max, len(slots)) for e in members}
    for c, rule_members in per_item_rules:
        groups = [set(group) for _, group in slot_groups(c.args, num_slots)]
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
    """Check, before solving, whether the population alone makes a hard
    count rule impossible: a per-slot range the group is too small or too
    large for, or a per-item range the slots-per-entity band (and other
    per-item counts) leave no room for. No other interaction is considered.

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

    per_item = [(c, set(resolve_group_members(df, c.args.get("items", {"kind": "all"}))))
                for c in constraints if _is_plain_count(c, "each")]
    for c, members in per_item:
        lo, hi = c.args.get("min"), c.args.get("max")
        ok, parts = True, []
        # Each member on its own, in each slot group: the band and the
        # other per-item counts must leave room for this one.
        for _, group in slot_groups(c.args, k):
            low, high = _holding_bounds(per_item, members, set(group), k, slots_per_entity)
            if lo is not None and any(high[e] < lo for e in members):
                ok = False
                parts.append(text.FEAS_LOAD_MIN_UNREACHABLE.format(lo=lo, most=min(high.values())))
            if hi is not None and any(low[e] > hi for e in members):
                ok = False
                parts.append(text.FEAS_LOAD_MAX_UNREACHABLE.format(hi=hi, fewest=max(low.values())))
            if not ok:
                break
        report.add(c.label, ok, " ".join(parts) or text.FEAS_LOAD_OK, constraint_id=c.id)

    for c in constraints:
        if not _is_plain_count(c, "all"):
            continue
        members = set(resolve_group_members(df, c.args.get("items", {"kind": "all"})))
        groups = slot_groups(c.args, k)
        covered = set().union(*(set(group) for _, group in groups))
        lo, hi = c.args.get("min"), c.args.get("max")
        low, high = _holding_bounds(per_item, members, covered, k, slots_per_entity)
        count = len(groups)
        ok = True
        if single:
            parts = [text.FEAS_GROUP_TOTAL.format(total=len(members))]
        else:
            parts = [text.FEAS_GROUP_PLACES.format(most=sum(high.values()), fewest=sum(low.values()), count=len(covered))]
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
