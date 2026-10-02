"""Independent verification and decision-support portfolio generation.

Nothing in this module trusts CP-SAT's status. An assignment is valid only
when this evaluator can account for every entity and every active hard rule.
The same evaluator is used for solver output, manual edits, and relaxed
what-if candidates.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from itertools import permutations
from time import monotonic
from typing import Any, Iterator, Optional

import pandas as pd

from constraint_engine import text
from constraint_engine.constraints import (
    DEFAULT_WEIGHT,
    Constraint,
    item_groups,
    placement_weight,
    slot_groups,
)
from constraint_engine.feasibility import analyze_feasibility
from constraint_engine.optimizer import OptimizationResult, SolverConfig, optimize


@dataclass
class RuleCheck:
    constraint_id: str
    label: str
    rule_type: str
    hard: bool
    status: str  # satisfied | violated | not_applicable
    summary: str
    expected: Any = None
    actual: Any = None
    # How far the rule is from fully met, in its own natural unit (entities
    # outside a range, total gap between slots, unmet requests...). 0 means
    # met; lower is better. Lets options be compared rule by rule.
    shortfall: float = 0
    affected_entities: list = field(default_factory=list)
    affected_slots: list[int | str] = field(default_factory=list)


@dataclass
class VerificationReport:
    is_valid: bool
    summary: str
    entities_expected: int
    entities_assigned: int
    hard_rules_satisfied: int
    hard_rules_violated: int
    soft_rules_satisfied: int
    soft_rules_violated: int
    checks: list[RuleCheck]

    def to_dict(self) -> dict:
        return {**asdict(self), "checks": [asdict(check) for check in self.checks]}


@dataclass
class CandidateOption:
    id: str
    title: str
    strategy: str
    assignment: dict
    verification: VerificationReport
    metrics: dict
    compromises: list[str]
    relaxed_constraint_ids: list[str]
    objective_value: Optional[float]
    wall_time_seconds: float
    differs_from_first: int = 0
    # Precise bends of mandatory rules ("slot 4: 3, the range is 2"), read
    # from the verifier -- never from solver internals.
    exceptions: list[dict] = field(default_factory=list)
    # Filled by rank_tradeoffs() once the whole round is known, because
    # "better" and "worse" only mean something relative to the siblings.
    scores: dict = field(default_factory=dict)
    gains: list[str] = field(default_factory=list)
    losses: list[str] = field(default_factory=list)
    moved_from_reference: Optional[int] = None

    def to_dict(self, include_assignment: bool = False) -> dict:
        payload = asdict(self)
        payload["verification"] = self.verification.to_dict()
        if not include_assignment:
            payload.pop("assignment", None)
        return payload


def slot_metrics(assignment: dict, num_slots: int) -> dict:
    """Rule-independent facts about an assignment."""
    sizes = [0] * num_slots
    for slots in assignment.values():
        for slot in slots:
            if 0 <= slot < num_slots:
                sizes[slot] += 1
    loads = [len(slots) for slots in assignment.values()]
    return {
        "slot_sizes": sizes,
        "slot_size_spread": (max(sizes) - min(sizes)) if sizes else 0,
        "load_spread": (max(loads) - min(loads)) if loads else 0,
    }


def verify_assignment(
    df: pd.DataFrame,
    assignment: dict,
    constraints: list[Constraint],
    num_slots: int,
    slots_per_entity: tuple[int, int] = (1, 1),
    slot_names: Optional[list[str]] = None,
) -> VerificationReport:
    """Evaluate all active rules without using optimizer internals or status.

    `assignment` maps each entity to the list of slots it holds; an entity
    missing from it holds none. Slots are reported by `slot_names` when
    given, else numbered from 1.
    """

    def name(slot: int):
        return slot_names[slot] if slot_names else slot + 1

    expected_entities = df.index.tolist()
    expected_set = set(expected_entities)
    load_min, load_max = slots_per_entity
    checks: list[RuleCheck] = []

    def holds(e) -> set:
        return set(assignment.get(e, ()))

    unknown = [e for e in assignment if e not in expected_set]
    out_of_range = [e for e, slots in assignment.items()
                    if any(not isinstance(s, int) or not 0 <= s < num_slots for s in slots) or len(set(slots)) != len(slots)]
    missing = [e for e in expected_entities if not holds(e) and load_min > 0]
    wrong_count = [e for e in expected_entities if holds(e) and not load_min <= len(holds(e)) <= load_max]
    structural_ok = not (missing or unknown or out_of_range or wrong_count) and num_slots > 0
    details = []
    if missing:
        details.append(text.INTEGRITY_MISSING.format(count=len(missing)))
    if wrong_count:
        details.append(text.INTEGRITY_WRONG_COUNT.format(count=len(wrong_count), min=load_min, max=load_max))
    if unknown:
        details.append(text.INTEGRITY_UNKNOWN.format(count=len(unknown)))
    if out_of_range:
        details.append(text.INTEGRITY_OUT_OF_RANGE.format(count=len(out_of_range)))
    affected = missing + wrong_count + unknown + out_of_range
    checks.append(RuleCheck(
        constraint_id="assignment_integrity", label=text.INTEGRITY_LABEL, rule_type="integrity", hard=True,
        status="satisfied" if structural_ok else "violated",
        summary=text.INTEGRITY_OK if structural_ok else "; ".join(details),
        expected={"entities": len(expected_set), "slots": num_slots, "slots_per_entity": [load_min, load_max]},
        actual={"assigned": sum(1 for e in expected_entities if holds(e))},
        shortfall=len(affected), affected_entities=affected,
    ))

    slot_members = [{e for e, slots in assignment.items() if index in slots} for index in range(max(0, num_slots))]

    def shares(a, b) -> bool:
        return bool(holds(a) & holds(b))

    def add(con: Constraint, ok: bool, summary: str, *, expected=None, actual=None, shortfall=None,
            entities=None, slots=None, na=False):
        checks.append(RuleCheck(
            constraint_id=con.id, label=con.label, rule_type=con.type, hard=con.hard,
            status="not_applicable" if na else ("satisfied" if ok else "violated"), summary=summary,
            expected=expected, actual=actual,
            shortfall=0 if na else (shortfall if shortfall is not None else int(not ok)),
            affected_entities=list(dict.fromkeys(entities or [])), affected_slots=list(slots or []),
        ))

    def held_by(ids) -> set:
        return set().union(*(holds(e) for e in ids)) if ids else set()

    for con in constraints:
        if not con.active:
            continue
        args = con.args
        if con.type == "count":
            rows = item_groups(df, args)
            columns = slot_groups(args, num_slots, slot_names)
            weight_of = placement_weight(args)
            cells = [[sum(weight_of(e, s) for e in ids for s in slots if s in holds(e)) for _, slots in columns]
                     for _, ids in rows]
            lo, hi = args.get("min"), args.get("max")
            outside = {}
            for r, row in enumerate(cells):
                for col, value in enumerate(row):
                    units = max(0, (lo - value) if lo is not None else 0) + max(0, (value - hi) if hi is not None else 0)
                    if units > 1e-9:
                        outside[r, col] = units
            even, allowed = args.get("even"), args.get("max_gap") or 0
            lines = []
            if even == "slots" and len(columns) > 1:
                lines = [[(r, col) for col in range(len(columns))] for r in range(len(rows))]
            elif even == "items" and len(rows) > 1:
                lines = [[(r, col) for r in range(len(rows))] for col in range(len(columns))]
            excess, uneven, largest = [], set(), 0
            for line in lines:
                values = [cells[r][col] for r, col in line]
                spread = max(values) - min(values)
                largest = max(largest, spread)
                if spread - allowed > 1e-9:
                    excess.append(spread - allowed)
                    uneven.update(cell for cell in line if cells[cell[0]][cell[1]] in (min(values), max(values)))
            bad = sorted(set(outside) | uneven)

            def cell_label(r, col):
                return " · ".join(part for part in (rows[r][0], columns[col][0]) if part) or text.TOTAL

            parts = []
            if outside:
                parts.append(text.COUNT_OUTSIDE.format(count=len(outside)))
            if excess:
                parts.append(text.COUNT_UNEVEN.format(gap=_number(largest)))
            expected = {"min": lo, "max": hi}
            if even:
                expected["max_gap"] = allowed
            add(con, not parts, "; ".join(parts) or text.COUNT_OK, expected=expected,
                actual={cell_label(r, col): _number(cells[r][col]) for r, col in bad} if bad
                else ({"largest_gap": _number(largest)} if even else None),
                shortfall=_number(sum(outside.values()) + sum(excess)),
                entities=[e for r, col in bad for e in rows[r][1] if holds(e) & set(columns[col][1])],
                slots=list(dict.fromkeys(columns[col][0] for _, col in bad if columns[col][0])))
        elif con.type == "share":
            bad_cases, units_total, applicable = [], 0, False
            for case in args["cases"]:
                entity = case["item"]
                others = [o for o in case["with"] if o in expected_set and o != entity]
                if entity not in expected_set or not others:
                    continue
                applicable = True
                shared = sum(shares(entity, o) for o in others)
                lo, hi = case.get("min"), case.get("max")
                units = max(0, (lo or 0) - shared) + max(0, (shared - hi) if hi is not None else 0)
                if units:
                    bad_cases.append((entity, others, shared))
                    units_total += units
            add(con, not bad_cases, text.SHARE_OK if not bad_cases else text.SHARE_BAD.format(count=len(bad_cases)),
                actual={str(entity): shared for entity, _, shared in bad_cases} or None, shortfall=units_total,
                entities=[e for entity, others, _ in bad_cases for e in [entity] + others], na=not applicable)
        elif con.type == "stretch":
            lo, hi = args.get("min"), args.get("max")
            target = args.get("of", "work") == "work"
            ignore_edges = bool(args.get("ignore_edges"))
            bad_stretches, bad_items = 0, []
            for _, ids in item_groups(df, {**args, "item_groups": args.get("item_groups", "each")}):
                held = held_by(ids)
                for sequence in args["sequences"]:
                    worked = [bool(held & set(unit)) for unit in sequence]
                    for start, length in stretches(worked, target):
                        inside = start > 0 and start + length < len(sequence)
                        too_long = hi is not None and length > hi and (inside or not ignore_edges)
                        too_short = lo is not None and length < lo and inside
                        if too_long or too_short:
                            bad_stretches += 1
                            bad_items.extend(ids)
            add(con, not bad_stretches,
                text.STRETCH_OK if not bad_stretches else text.STRETCH_BAD.format(count=bad_stretches),
                expected={"min": lo, "max": hi}, actual={"stretches_outside": bad_stretches},
                shortfall=bad_stretches, entities=bad_items)
        elif con.type == "transition":
            pairs = [(int(a), int(b)) for a, b in args["pairs"]]
            found, bad_items = {}, []
            for label, ids in item_groups(df, {**args, "item_groups": args.get("item_groups", "each")}):
                held = held_by(ids)
                hits = [(a, b) for a, b in pairs if a in held and b in held]
                if hits:
                    found[label] = [[name(a), name(b)] for a, b in hits]
                    bad_items.extend(ids)
            count = sum(len(hits) for hits in found.values())
            add(con, not found, text.TRANSITION_OK if not found else text.TRANSITION_BAD.format(count=count),
                expected=0, actual=found or None, shortfall=count, entities=bad_items)
        else:
            add(con, False, text.NO_CHECKER.format(type=con.type))

    hard_bad = sum(check.hard and check.status == "violated" for check in checks)
    hard_ok = sum(check.hard and check.status == "satisfied" for check in checks)
    soft_bad = sum(not check.hard and check.status == "violated" for check in checks)
    soft_ok = sum(not check.hard and check.status == "satisfied" for check in checks)
    valid = hard_bad == 0
    summary = text.VERIFY_VALID.format(ok=hard_ok) if valid else text.VERIFY_INVALID.format(bad=hard_bad, ok=hard_ok)
    entities_assigned = sum(1 for e in expected_entities if holds(e))
    return VerificationReport(valid, summary, len(expected_set), entities_assigned,
                              hard_ok, hard_bad, soft_ok, soft_bad, checks)


def _number(value):
    """A count as an int, a weighted sum rounded for people to read."""
    return int(value) if float(value).is_integer() else round(float(value), 2)


def stretches(values: list[bool], target: bool) -> list[tuple[int, int]]:
    """(start, length) of every maximal stretch of `target` in `values`."""
    found, start = [], None
    for index, value in enumerate(values + [not target]):
        if value == target and start is None:
            start = index
        elif value != target and start is not None:
            found.append((start, index - start))
            start = None
    return found


def assignment_distance(first: dict, second: dict, num_slots: int, interchangeable: bool = True) -> int:
    """How many entities hold different slots in the two assignments.

    With interchangeable slots (one slot per entity), slot labels are
    arbitrary: the count is the minimum over every renaming of slots.
    """
    entities = [e for e in first if e in second]
    unmatched = len(set(first) ^ set(second))
    if not interchangeable:
        return sum(set(first[e]) != set(second[e]) for e in entities) + unmatched
    if any(len(first[e]) != 1 or len(second[e]) != 1 for e in entities):
        raise ValueError(text.INTERCHANGEABLE_NEEDS_SINGLE_SLOT)
    first = {e: first[e][0] for e in entities}
    second = {e: second[e][0] for e in entities}
    if num_slots <= 8:
        best_same = 0
        for mapping in permutations(range(num_slots)):
            best_same = max(best_same, sum(mapping[first[e]] == second[e] for e in entities))
        return len(entities) - best_same + unmatched
    # Greedy fallback avoids factorial work for unusually large slot counts.
    pairs = sorted(((sum(first.get(e) == a and second.get(e) == b for e in entities), a, b)
                    for a in range(num_slots) for b in range(num_slots)), reverse=True)
    used_a, used_b, same = set(), set(), 0
    for count, a, b in pairs:
        if a not in used_a and b not in used_b:
            used_a.add(a); used_b.add(b); same += count
    return len(entities) - same + unmatched

# A round always offers this many options: fewer reads as "the engine gave
# up", more is more than a person can hold in mind at once.
PORTFOLIO_SIZE = 3
# Wall-clock budget for one whole round, shared by all its solves.
ROUND_BUDGET_SECONDS = 30.0

STRATEGIES = list(text.STRATEGY_TITLES)

# Soft rule types each emphasis pushes. Everything not listed is left alone.
PREFERENCE_TYPES = {"share"}
BALANCE_TYPES = {"count"}

# A refinement pushes its emphasis harder than a fresh round (see
# profile_constraints).
REFINE_STRENGTH = 1.5

# How strongly a refinement holds each entity in its base slot, per step of
# the "how much may change" ladder. Under the refinement's request emphasis
# one entity can be worth ~42 (8 x 3^1.5), so 60 dominates every soft goal
# (only the moves the rules or the new emphasis force), 10 trades against
# them, and 0 lets the emphasis reshape freely.
REFINE_WEIGHTS = [60.0, 10.0, 0.0]
# Share of the round's time per refinement step. "Small" barely searches
# (the anchor holds nearly everyone), so the time goes where the search is.
REFINE_TIME_SHARES = [0.2, 0.4, 0.4]


def _scale_weights(con: Constraint, factor: float) -> None:
    con.args["weight"] = float(con.args.get("weight", DEFAULT_WEIGHT.get(con.type, 1.0))) * factor


def profile_constraints(constraints: list[Constraint], strategy: str, strength: float = 1.0) -> list[Constraint]:
    """Re-weight the soft goals toward one emphasis. `strength` raises every
    factor to that power: a refinement asked for "more requests" from an
    option that already favored them has to push further than the round
    that produced it, or it can only return the same answer."""
    boost, damp = 3 ** strength, .35 ** strength
    balance_boost, preference_damp = 4 ** strength, .4 ** strength
    result = deepcopy(constraints)
    for con in result:
        if con.hard:
            continue
        if strategy == "preferences":
            if con.type in PREFERENCE_TYPES:
                _scale_weights(con, boost)
            elif con.type in BALANCE_TYPES:
                _scale_weights(con, damp)
        elif strategy == "balance":
            if con.type in BALANCE_TYPES:
                _scale_weights(con, balance_boost)
            elif con.type in PREFERENCE_TYPES:
                _scale_weights(con, preference_damp)
    return result


def _range_text(expected: Any) -> str:
    if not isinstance(expected, dict):
        return str(expected)
    lo, hi = expected.get("min"), expected.get("max")
    lo = None if lo is None else _number(lo)
    hi = None if hi is None else _number(hi)
    if lo is not None and hi is not None:
        return f"{lo}" if lo == hi else f"{lo}–{hi}"
    if hi is not None:
        return text.RANGE_UP_TO.format(hi=hi)
    return text.RANGE_AT_LEAST.format(lo=lo)


def describe_exceptions(report: VerificationReport) -> list[dict]:
    """Every violated mandatory rule, in slot-level detail where possible."""
    items = []
    for check in report.checks:
        if not check.hard or check.status != "violated" or check.constraint_id == "assignment_integrity":
            continue
        bounded = isinstance(check.expected, dict) and (check.expected.get("min") is not None
                                                         or check.expected.get("max") is not None)
        if check.rule_type == "count" and isinstance(check.actual, dict) and bounded:
            parts = ", ".join(text.CELL_VALUE.format(cell=cell, value=value) for cell, value in check.actual.items())
            description = text.EXCEPTION_DETAIL.format(label=check.label, parts=parts, range=_range_text(check.expected))
        else:
            description = text.EXCEPTION_SUMMARY.format(label=check.label, summary=check.summary)
        items.append({
            "constraint_id": check.constraint_id,
            "label": check.label,
            "text": description,
            "slots": list(check.affected_slots),
            "entities": list(check.affected_entities),
        })
    return items


def _candidate(option_id: str, title: str, strategy: str, result: OptimizationResult, df, original_constraints,
               cfg, relaxed_ids, first_assignment=None, reference=None) -> CandidateOption:
    report = verify_assignment(df, result.assignment, original_constraints, cfg.num_slots, cfg.slots_per_entity,
                               cfg.slot_names)
    metrics = slot_metrics(result.assignment, cfg.num_slots)
    compromises = [check.summary for check in report.checks if check.status == "violated"]
    moved = (sum(1 for e, slots in result.assignment.items() if set(reference.get(e, ())) != set(slots))
             if reference else None)
    return CandidateOption(option_id, title, strategy, result.assignment, report, metrics, compromises, list(relaxed_ids),
                           result.objective_value, result.wall_time_seconds,
                           assignment_distance(first_assignment, result.assignment, cfg.num_slots, cfg.interchangeable)
                           if first_assignment else 0,
                           exceptions=describe_exceptions(report), moved_from_reference=moved)


def _format(value: Any) -> str:
    if isinstance(value, float):
        value = round(value)
    return str(value)


def rank_tradeoffs(options: list[CandidateOption]) -> None:
    """Score each option against its siblings: strictly best is a gain,
    strictly worst is a loss. Deterministic, so the agent only has to put
    these facts into words, never derive them.

    Compared on: the gap between slot sizes, the gap between the most and
    fewest slots any entity holds, each soft rule's shortfall, and (when
    refining) how many entities moved."""
    if not options:
        return
    # (key, label, value per option); lower is better for every measure.
    measures: list[tuple[str, str, list]] = [
        ("slot_size_spread", text.METRIC_SLOT_SIZE_SPREAD, [option.metrics.get("slot_size_spread") for option in options]),
        ("load_spread", text.METRIC_LOAD_SPREAD, [option.metrics.get("load_spread") for option in options]),
    ]
    first_checks = [check for check in options[0].verification.checks if not check.hard]
    for check in first_checks:
        values = []
        for option in options:
            match = next((c for c in option.verification.checks if c.constraint_id == check.constraint_id), None)
            values.append(None if match is None or match.status == "not_applicable" else match.shortfall)
        measures.append((check.constraint_id, check.label.rstrip("."), values))
    if any(option.moved_from_reference is not None for option in options):
        measures.append(("moved_from_reference", text.METRIC_MOVED, [option.moved_from_reference for option in options]))

    for option in options:
        option.scores, option.gains, option.losses = {}, [], []
    rule_ids = {check.constraint_id for check in first_checks}
    for key, label, values in measures:
        best_text, worst_text = ((text.TRADEOFF_BEST_RULE, text.TRADEOFF_WORST_RULE) if key in rule_ids
                                 else (text.TRADEOFF_BEST, text.TRADEOFF_WORST))
        if any(value is None for value in values):
            continue
        best, worst = min(values), max(values)
        for option, value in zip(options, values):
            rank = "mid"
            if best != worst and value == best and values.count(best) == 1:
                rank = "best"
                option.gains.append(best_text.format(label=label, value=_format(value)))
            elif best != worst and value == worst and values.count(worst) == 1:
                rank = "worst"
                option.losses.append(worst_text.format(label=label, value=_format(value)))
            option.scores[key] = {"label": label, "value": value, "rank": rank, "higher_is_better": False}
    for option in options:
        option.losses = [item["text"] for item in option.exceptions] + option.losses


class PortfolioSearch:
    """One round of options, yielded as each is found and verified.

    A round is either *perfect* (every option meets every mandatory rule
    and they differ in what they favor) or a *compromise* round (nothing
    meets them all; each option bends a different rule by the smallest
    measured amount). With `anchor`, the round refines a chosen option:
    the same emphasis at three levels of how much may change.
    """

    def __init__(self, df: pd.DataFrame, config: SolverConfig, constraints: list[Constraint], *,
                 max_options: int = PORTFOLIO_SIZE, time_budget_seconds: Optional[float] = None,
                 anchor: Optional[dict] = None, emphasis: str = "balanced",
                 reference: Optional[dict] = None, fixed_slots: Optional[dict[int, list]] = None):
        self.df = df
        self.config = config
        self.constraints = constraints
        self.max_options = max_options
        self.deadline = monotonic() + (ROUND_BUDGET_SECONDS if time_budget_seconds is None else time_budget_seconds)
        self.anchor = anchor
        self.emphasis = emphasis if emphasis in text.STRATEGY_TITLES else "balanced"
        # What "moved" is counted against: the refined option, else the
        # assignment the user currently has.
        self.reference = anchor or reference
        # Slots held exactly as they are in every solve of this round.
        self.fixed_slots = fixed_slots or {}
        self.options: list[CandidateOption] = []
        self.conflicts: list[str] = []
        self.mode = "perfect"
        self.min_distance = max(1, len(df) // 20)

    def _cfg(self, solves_left: int, share: Optional[float] = None) -> SolverConfig:
        """An even split of what is left, or `share` of it when given."""
        cfg = deepcopy(self.config)
        remaining = max(0.0, self.deadline - monotonic())
        budget = remaining * share if share is not None else remaining / max(1, solves_left)
        cfg.time_limit_seconds = max(1.0, min(self.config.time_limit_seconds, budget))
        cfg.random_seed = self.config.random_seed + len(self.options)
        return cfg

    def _expired(self) -> bool:
        return monotonic() >= self.deadline

    def _solve(self, strategy: str, solves_left: int, flexible=(), anchor_weight: float = 0.0,
               share: Optional[float] = None):
        cfg = self._cfg(solves_left, share)
        excluded = [option.assignment for option in self.options] + ([self.anchor] if self.anchor else [])
        result = optimize(
            self.df, cfg, profile_constraints(self.constraints, strategy, REFINE_STRENGTH if self.anchor else 1.0),
            excluded_assignments=excluded,
            min_assignment_distance=self.min_distance,
            flexible_constraint_ids=set(flexible),
            anchor_assignment=self.anchor, anchor_weight=anchor_weight,
            # Each refinement step starts from the previous one, so "free"
            # builds on "medium" instead of re-searching from the base.
            hint_assignment=self.options[-1].assignment if self.anchor and self.options else self.anchor,
            fixed_slots=self.fixed_slots,
        )
        return cfg, result

    def _accept(self, title: str, strategy: str, cfg, result, relaxed) -> Optional[CandidateOption]:
        if any(assignment_distance(option.assignment, result.assignment, cfg.num_slots, cfg.interchangeable) == 0
               for option in self.options):
            return None
        option = _candidate(f"option-{len(self.options) + 1}", title, strategy, result, self.df, self.constraints, cfg,
                            relaxed, self.options[0].assignment if self.options else None, self.reference)
        self.options.append(option)
        return option

    def _share(self, step: int) -> Optional[float]:
        """Fraction of the remaining time for plan step `step` of a refinement."""
        if not self.anchor or step >= len(REFINE_TIME_SHARES):
            return None
        return REFINE_TIME_SHARES[step] / sum(REFINE_TIME_SHARES[step:])

    def _plan(self) -> list[tuple[str, str, float]]:
        if self.anchor:
            emphasis = text.STRATEGY_TITLES[self.emphasis]
            return [(self.emphasis, f"{label}{text.TITLE_JOIN}{emphasis}", weight)
                    for weight, label in zip(REFINE_WEIGHTS, text.REFINE_STEP_LABELS)]
        return [(strategy, title, 0.0) for strategy, title in text.STRATEGY_TITLES.items()]

    def __iter__(self) -> Iterator[CandidateOption]:
        plan = self._plan()
        hard = [con for con in self.constraints if con.active and con.hard]
        # Rules the population totals alone make impossible (5 entities for
        # 6 slots at "at least 1") must bend in every option; no solve is
        # needed to know that, so none of the budget is spent proving it.
        forced_ids = {finding.constraint_id for finding in
                      analyze_feasibility(self.df, self.constraints, self.config.num_slots,
                                          self.config.slots_per_entity).infeasible}
        forced = [con for con in hard if con.id in forced_ids]
        if forced:
            self.conflicts = [con.id for con in forced]
            yield from self._compromises(plan, hard, forced)
            return
        for index, (strategy, title, weight) in enumerate(plan):
            if len(self.options) >= self.max_options or (index and self._expired()):
                return
            cfg, result = self._solve(strategy, len(plan) - index, anchor_weight=weight, share=self._share(index))
            if not result.is_feasible:
                if not self.options:
                    self.conflicts = list(result.conflicting_constraint_ids)
                    yield from self._compromises(plan, hard, [])
                    return
                continue
            option = self._accept(title, strategy, cfg, result, [])
            if option:
                yield option

    def _compromises(self, plan, hard: list[Constraint], forced: list[Constraint]) -> Iterator[CandidateOption]:
        """Nothing meets every mandatory rule.

        Each attempt bends a set of rules by the smallest total amount. Where
        no rule is forced, one rule at a time comes first: options that bend
        *different* rules are the most useful choice to put in front of the
        user. Bigger sets are only tried when no smaller one works. Any
        remaining slots in the round follow its plan (emphasis, or how much
        may change) under the first set that worked."""
        self.mode = "compromise"
        by_id = {con.id: con for con in hard}
        conflicting = [con for con in hard if con.id in self.conflicts] or hard
        if forced:
            primary: list[list[Constraint]] = [forced]
            extended = forced + [con for con in conflicting if con not in forced]
            fallbacks = [extended] if len(extended) > len(forced) else []
        else:
            primary = [[con] for con in conflicting[:5]]
            fallbacks = [conflicting] if len(conflicting) > 1 else []
        if len(hard) > len((fallbacks or primary)[-1]):
            fallbacks.append(hard)

        first_strategy, first_title, first_weight = plan[0]
        worked: Optional[list[str]] = None
        attempts = primary + fallbacks
        for index, group in enumerate(attempts):
            if len(self.options) >= self.max_options or (index and self._expired()):
                break
            if worked and index >= len(primary):
                break
            ids = [con.id for con in group]
            cfg, result = self._solve(first_strategy, len(attempts) - index + len(plan) - 1,
                                      flexible=ids, anchor_weight=first_weight, share=self._share(0))
            if not result.is_feasible:
                continue
            worked = worked or ids
            single = len(ids) == 1
            title = (text.COMPROMISE_SINGLE.format(label=by_id[ids[0]].label) if single
                     else f"{text.COMPROMISE_MULTI}{text.TITLE_JOIN}{first_title}")
            option = self._accept(title, "single_rule_compromise" if single else "multi_rule_compromise",
                                  cfg, result, ids)
            if option:
                yield option

        if not worked:
            return
        prefix = self.options[0].title.split(text.TITLE_JOIN)[0] if self.options else text.COMPROMISE_MULTI
        rest = plan[1:]
        for index, (strategy, title, weight) in enumerate(rest):
            if len(self.options) >= self.max_options or self._expired():
                break
            cfg, result = self._solve(strategy, len(rest) - index, flexible=worked, anchor_weight=weight,
                                      share=self._share(index + 1))
            if result.is_feasible:
                option = self._accept(f"{prefix}{text.TITLE_JOIN}{title}", strategy, cfg, result, worked)
                if option:
                    yield option


def generate_portfolio(df: pd.DataFrame, config: SolverConfig, constraints: list[Constraint],
                       max_options: int = PORTFOLIO_SIZE, **kwargs) -> tuple[list[CandidateOption], list[str]]:
    """Collect a whole round. See PortfolioSearch for what a round is."""
    search = PortfolioSearch(df, config, constraints, max_options=max_options, **kwargs)
    options = list(search)
    rank_tradeoffs(options)
    return options, search.conflicts


def negotiation_question(options: list[CandidateOption]) -> Optional[dict]:
    if len(options) < 2:
        return None
    ids = [option.id for option in options]
    if all(option.verification.is_valid for option in options):
        return {"question": text.QUESTION_ALL_VALID, "options": ids, "reason": text.QUESTION_ALL_VALID_REASON}
    return {"question": text.QUESTION_COMPROMISE, "options": ids, "reason": text.QUESTION_COMPROMISE_REASON}
