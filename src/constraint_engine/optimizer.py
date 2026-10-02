"""CP-SAT assignment optimizer.

Binary decision variables x[entity, slot] = 1 if the entity holds the slot.
How many slots each entity holds is `SolverConfig.slots_per_entity`: (1, 1)
is placement (every entity in exactly one slot), wider bands are rostering.
Rules are supplied as a list of `Constraint` objects (see
constraints.py). Each hard rule is reified behind its own CP-SAT
"assumption" literal; if the model turns out infeasible,
`solver.SufficientAssumptionsForInfeasibility()` identifies a set of rules
jointly responsible, which we map back to `Constraint.id`s for
`OptimizationResult.conflicting_constraint_ids`. Soft rules contribute
weighted terms to a single objective, scaled to comparable magnitude
(roughly 0..num_entities) so no weight needs extreme tuning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import math

import pandas as pd
from ortools.sat.python import cp_model

from constraint_engine import text
from constraint_engine.constraints import (
    DEFAULT_WEIGHT,
    Constraint,
    item_groups,
    placement_weight,
    rule_slot_indexes,
    slot_groups,
)


class OptimizationError(Exception):
    """Raised when the optimizer cannot be run (e.g. bad configuration)."""


@dataclass
class SolverConfig:
    """Run parameters. Rules and weights live in the Constraint list passed
    to optimize(), not here."""

    num_slots: int = 6
    # How many slots each entity holds, (min, max). (1, 1) is placement:
    # every entity in exactly one slot. Rostering widens it and adds count
    # rules for per-group bands.
    slots_per_entity: tuple[int, int] = (1, 1)
    # Whether slots are interchangeable labels (class 1..6) or distinct
    # things (Monday morning). With interchangeable slots, two assignments
    # that differ only by renaming slots are the same answer. None means
    # interchangeable exactly when each entity holds one slot; it cannot be
    # True otherwise.
    slots_interchangeable: Optional[bool] = None
    # How results name the slots (e.g. "mon-am"); numbered from 1 if None.
    # Display only: the solver never reads it.
    slot_names: Optional[list[str]] = None
    time_limit_seconds: float = 60.0
    # Not a user dial, deliberately: the seed exists to keep solves
    # reproducible (see the num_search_workers note in optimize()). Changing
    # it only reshuffles which of several equally-good assignments you get,
    # which reads as the engine being random.
    random_seed: int = 42

    @property
    def single_slot(self) -> bool:
        return tuple(self.slots_per_entity) == (1, 1)

    @property
    def interchangeable(self) -> bool:
        return self.single_slot if self.slots_interchangeable is None else self.slots_interchangeable


@dataclass
class OptimizationResult:
    status_name: str
    is_feasible: bool
    assignment: dict  # entity id -> sorted list of slot indexes (0-based)
    objective_value: Optional[float]
    wall_time_seconds: float
    solver_log: str = ""
    infeasibility_notes: list[str] = field(default_factory=list)
    conflicting_constraint_ids: list[str] = field(default_factory=list)


def optimize(
    df: pd.DataFrame,
    config: SolverConfig,
    constraints: list[Constraint],
    excluded_assignments: Optional[list[dict]] = None,
    min_assignment_distance: int = 1,
    flexible_constraint_ids: Optional[set[str]] = None,
    anchor_assignment: Optional[dict] = None,
    anchor_weight: float = 0.0,
    hint_assignment: Optional[dict] = None,
    fixed_slots: Optional[dict[int, list]] = None,
) -> OptimizationResult:
    """Run the CP-SAT optimizer over the entities in `df` (one per row,
    identified by the index).

    Args:
        df: entity table; must include every column a rule's group selector
            references.
        config: run parameters (slot count, time limit, seed).
        constraints: the full rule list. Inactive rules are skipped.
        excluded_assignments / min_assignment_distance: earlier answers the
            result must differ from, in the slots of at least this many
            entities -- and, when slots are interchangeable, as a partition
            (renaming slots does not count as different).
        flexible_constraint_ids: hard rules that may bend. Each is compiled
            with measurable slack instead of being enforced, and the solve
            becomes lexicographic: first the smallest total slack, then the
            usual objective with that slack held fixed. This turns
            "impossible" into "possible if slot 4 takes one extra" instead
            of dropping the whole rule.
        anchor_assignment / anchor_weight: reward each entity that stays in
            its anchor slot, so a refinement changes as little as needed.
        hint_assignment: a starting point for the search only (never a
            rule).
        fixed_slots: {slot: [entity id, ...]} kept exactly as given for this
            solve -- nobody leaves, nobody joins. Never a rule, never bent.

    Returns:
        An OptimizationResult with the assignment (empty if infeasible) and
        solver diagnostics, including which rule ids conflict when
        infeasible.

    Raises:
        OptimizationError: if the configuration is structurally invalid
            (e.g. zero slots, a rule naming a missing slot).
    """
    if config.num_slots < 1:
        raise OptimizationError(text.NUM_SLOTS_TOO_SMALL)
    load_min, load_max = (int(v) for v in config.slots_per_entity)
    if not 0 <= load_min <= load_max:
        raise OptimizationError(text.BAD_SLOTS_PER_ENTITY.format(min=load_min, max=load_max))
    if config.interchangeable and not config.single_slot:
        raise OptimizationError(text.INTERCHANGEABLE_NEEDS_SINGLE_SLOT)
    single = config.single_slot

    excluded_assignments = excluded_assignments or []
    flexible_ids = set(flexible_constraint_ids or ())
    active = [c for c in constraints if c.active]

    entities = df.index.tolist()
    entity_set = set(entities)
    n = len(entities)
    k = config.num_slots

    for c in active:
        for slot in rule_slot_indexes(c.args):
            if slot < 0 or slot >= k:
                raise OptimizationError(text.RULE_NAMES_MISSING_SLOT.format(label=c.label, slot=slot + 1, num_slots=k))

    model = cp_model.CpModel()
    x: dict[tuple, cp_model.IntVar] = {}
    for e in entities:
        for s in range(k):
            x[e, s] = model.NewBoolVar(f"x_{e}_{s}")

    for e in entities:
        held = sum(x[e, s] for s in range(k))
        if load_min == load_max:
            model.Add(held == load_min)
        else:
            model.Add(held >= load_min)
            model.Add(held <= load_max)

    for slot, members in (fixed_slots or {}).items():
        if slot < 0 or slot >= k:
            raise OptimizationError(text.SLOT_DOES_NOT_EXIST.format(slot=slot + 1, num_slots=k))
        keep = set(members)
        for e in entities:
            model.Add(x[e, slot] == int(e in keep))

    # Portfolio generation can ask for another genuinely different answer.
    # This is deliberately a solver input rather than post-processing: a
    # different seed alone often returns the same optimum.
    minimum_distance = max(1, int(min_assignment_distance))
    placement = {}
    if excluded_assignments and config.interchangeable:
        for e in entities:
            placement[e] = model.NewIntVar(0, k - 1, f"placement_{e}")
            model.Add(placement[e] == sum(s * x[e, s] for s in range(k)))
    for index, previous in enumerate(excluded_assignments):
        held_before = {e: {s for s in previous[e] if 0 <= s < k} for e in entities if e in previous}
        if single:
            # One slot each: an entity moved iff it left its old slot.
            stays = [x[e, s] for held in held_before.values() for s in held]
            if stays:
                model.Add(sum(stays) <= len(stays) - min(minimum_distance, len(stays)))
        else:
            moved = []
            for e, held in held_before.items():
                differences = [1 - x[e, s] for s in held] + [x[e, s] for s in range(k) if s not in held]
                m = model.NewBoolVar(f"moved_{index}_{e}")
                model.Add(m <= sum(differences))
                moved.append(m)
            if moved:
                model.Add(sum(moved) >= min(minimum_distance, len(moved)))
        if not config.interchangeable:
            continue
        # Exclude the partition itself, including every renaming of slots.
        # Members must separate from an old group anchor, or two anchors merge.
        anchors = {}
        changed = []
        for e in entities:
            if not held_before.get(e):
                continue
            group = next(iter(held_before[e]))
            if group not in anchors:
                anchors[group] = e
                continue
            differs = model.NewBoolVar(f"partition_change_{len(changed)}_{e}")
            model.Add(placement[e] != placement[anchors[group]]).OnlyEnforceIf(differs)
            model.Add(placement[e] == placement[anchors[group]]).OnlyEnforceIf(differs.Not())
            changed.append(differs)
        anchor_ids = list(anchors.values())
        for index, first in enumerate(anchor_ids):
            for second in anchor_ids[index + 1:]:
                merged = model.NewBoolVar(f"partition_merge_{first}_{second}")
                model.Add(placement[first] == placement[second]).OnlyEnforceIf(merged)
                model.Add(placement[first] != placement[second]).OnlyEnforceIf(merged.Not())
                changed.append(merged)
        if anchors:
            model.AddBoolOr(changed)

    objective_terms = []
    # Units by which flexible hard rules are bent (entities over/under a
    # range, pairs split, ...). Minimized before anything else.
    slack_terms = []
    assumption_lits: list[cp_model.IntVar] = []
    # SufficientAssumptionsForInfeasibility() returns CP-SAT *variable*
    # indices (lit.Index()), not positions in the list passed to
    # AddAssumptions -- confirmed empirically, not just from docs. Map by
    # index, not by list position.
    constraint_id_by_var_index: dict[int, str] = {}

    def enable_lit(constraint: Constraint) -> cp_model.IntVar:
        """A reified 'this hard rule is active' literal, used both to gate
        the rule's own Add() calls (.OnlyEnforceIf) and as a CP-SAT
        assumption so infeasibility can be traced back to specific rules."""
        lit = model.NewBoolVar(f"assume_{constraint.id}")
        assumption_lits.append(lit)
        constraint_id_by_var_index[lit.Index()] = constraint.id
        return lit

    # Co-placement indicator y[a,b] = 1 if a and b end up in the same slot.
    same_slot_vars: dict[tuple, cp_model.IntVar] = {}

    def get_same_slot_var(a, b):
        key = tuple(sorted((a, b), key=repr))
        if key in same_slot_vars:
            return same_slot_vars[key]
        v = model.NewBoolVar(f"same_{key[0]}_{key[1]}")
        same_terms = []
        for s in range(k):
            both = model.NewBoolVar(f"both_{key[0]}_{key[1]}_{s}")
            model.AddMultiplicationEquality(both, [x[a, s], x[b, s]])
            same_terms.append(both)
        if single:
            model.Add(v == sum(same_terms))
        else:
            model.AddMaxEquality(v, same_terms)
        same_slot_vars[key] = v
        return v

    def band_shortfall(expr, lo, hi, name: str, top: int):
        """Units by which `expr` falls outside [lo, hi], as one expression."""
        units = []
        if lo is not None:
            under = model.NewIntVar(0, max(0, int(lo)), f"{name}_under")
            model.Add(expr + under >= lo)
            units.append(under)
        if hi is not None:
            over = model.NewIntVar(0, max(0, int(top)), f"{name}_over")
            model.Add(expr - over <= hi)
            units.append(over)
        return sum(units)

    def spread_var(exprs, top: int, name: str):
        """The largest minus the smallest of `exprs`."""
        largest = model.NewIntVar(0, top, f"{name}_max")
        smallest = model.NewIntVar(0, top, f"{name}_min")
        model.AddMaxEquality(largest, exprs)
        model.AddMinEquality(smallest, exprs)
        return largest - smallest

    def is_flexible(c: Constraint) -> bool:
        return c.hard and c.id in flexible_ids

    def finish(c: Constraint, hard, measures, scale: int = 1):
        """Post a rule in its mode. `hard(lit)` posts its constraints gated
        by lit; `measures()` returns non-negative expressions that are zero
        exactly when the rule holds, used to bend it (flexible) or to
        penalize breaking it (soft)."""
        if is_flexible(c):
            slack_terms.extend(measures())
        elif c.hard:
            hard(enable_lit(c))
        else:
            weight = c.args.get("weight", DEFAULT_WEIGHT[c.type])
            if weight > 0:
                objective_terms.append(-(weight / scale) * sum(measures()))

    def groups_in_model(args: dict, default: str):
        return [(label, [e for e in ids if e in entity_set])
                for label, ids in item_groups(df, {**args, "item_groups": args.get("item_groups", default)})]

    held_vars: dict[tuple, cp_model.IntVar] = {}

    def held(ids: list, slots: list[int], name: str):
        """True when any of `ids` holds any of `slots`."""
        if len(ids) == 1 and len(slots) == 1:
            return x[ids[0], slots[0]]
        key = (tuple(ids), tuple(slots))
        if key not in held_vars:
            v = model.NewBoolVar(name)
            if ids and slots:
                model.AddMaxEquality(v, [x[e, s] for e in ids for s in slots])
            else:
                model.Add(v == 0)
            held_vars[key] = v
        return held_vars[key]

    # ---- the four blocks ----

    def compile_count(c: Constraint):
        args = c.args
        rows = groups_in_model(args, "all")
        columns = slot_groups(args, k)
        weight_of = placement_weight(args)
        raw = [weight_of(e, s) for _, ids in rows for e in ids for _, slots in columns for s in slots]
        bounds = [v for v in (args.get("min"), args.get("max"), args.get("max_gap")) if v is not None]
        # CP-SAT counts in integers; fractional weights (7.5 hours) are
        # counted in hundredths, and the bounds with them.
        scale = 1 if all(float(v).is_integer() for v in raw + bounds) else 100

        def w(e, s) -> int:
            return int(round(weight_of(e, s) * scale))

        cells, tops = [], []
        for _, ids in rows:
            cells.append([sum(w(e, s) * x[e, s] for e in ids for s in slots) for _, slots in columns])
            tops.append([sum(max(0, w(e, s)) for e in ids for s in slots) for _, slots in columns])
        top = max((t for row in tops for t in row), default=0)
        lo = None if args.get("min") is None else math.ceil(args["min"] * scale - 1e-9)
        hi = None if args.get("max") is None else math.floor(args["max"] * scale + 1e-9)
        gap = int(round((args.get("max_gap") or 0) * scale))
        even = args.get("even")
        lines = []
        if even == "slots":
            lines = [row for row in cells if len(row) > 1]
        elif even == "items":
            lines = [list(column) for column in zip(*cells) if len(column) > 1]
        flat = [cell for row in cells for cell in row]

        def hard(lit):
            for cell in flat:
                if lo is not None:
                    model.Add(cell >= lo).OnlyEnforceIf(lit)
                if hi is not None:
                    model.Add(cell <= hi).OnlyEnforceIf(lit)
            for index, line in enumerate(lines):
                model.Add(spread_var(line, top, f"{c.id}_line{index}") <= gap).OnlyEnforceIf(lit)

        def measures():
            out = []
            if lo is not None or hi is not None:
                out += [band_shortfall(cell, lo, hi, f"{c.id}_cell{index}", top) for index, cell in enumerate(flat)]
            for index, line in enumerate(lines):
                excess = model.NewIntVar(0, top, f"{c.id}_excess{index}")
                model.Add(excess >= spread_var(line, top, f"{c.id}_line{index}") - gap)
                out.append(excess)
            return out

        finish(c, hard, measures, scale)

    def compile_share(c: Constraint):
        cases = []
        for case in c.args["cases"]:
            e = case["item"]
            others = [o for o in case["with"] if o in entity_set and o != e]
            if e in entity_set and others:
                cases.append((e, others, case.get("min"), case.get("max")))
        if not cases:
            return

        def hard(lit):
            for e, others, lo, hi in cases:
                if single and len(others) == 1 and (lo or 0) >= 1:
                    # One slot each: together means the same slot.
                    for s in range(k):
                        model.Add(x[e, s] == x[others[0], s]).OnlyEnforceIf(lit)
                    continue
                if hi == 0:
                    for o in others:
                        for s in range(k):
                            model.Add(x[e, s] + x[o, s] <= 1).OnlyEnforceIf(lit)
                    continue
                shared = sum(get_same_slot_var(e, o) for o in others)
                if lo is not None:
                    model.Add(shared >= lo).OnlyEnforceIf(lit)
                if hi is not None:
                    model.Add(shared <= hi).OnlyEnforceIf(lit)

        def measures():
            return [
                band_shortfall(sum(get_same_slot_var(e, o) for o in others), lo, hi, f"{c.id}_{e}", len(others))
                for e, others, lo, hi in cases
            ]

        finish(c, hard, measures)

    def stretch_patterns(literals: list, lo, hi, ignore_edges: bool, prefix: str) -> list[tuple[str, list, int]]:
        """Each way a stretch can break the band, as (kind, literals, bound):
        ("sum", window, hi) -- a window of hi+1 units all in the stretch;
        ("clause", lits, 0) -- the clause that forbids a bad stretch.
        A stretch shorter than lo is only bad with a known unit on both
        sides; with ignore_edges, a long stretch is too."""
        patterns = []
        n_units = len(literals)
        before, after = {}, {}

        def other_before(i):
            # Some unit before i is outside the stretch.
            if i not in before:
                v = model.NewBoolVar(f"{prefix}_before{i}")
                outside = [lit.Not() for lit in literals[:i]]
                model.AddBoolOr(outside).OnlyEnforceIf(v)
                for lit in outside:
                    model.AddImplication(lit, v)
                before[i] = v
            return before[i]

        def other_after(i):
            # Some unit from i on is outside the stretch.
            if i not in after:
                v = model.NewBoolVar(f"{prefix}_after{i}")
                outside = [lit.Not() for lit in literals[i:]]
                model.AddBoolOr(outside).OnlyEnforceIf(v)
                for lit in outside:
                    model.AddImplication(lit, v)
                after[i] = v
            return after[i]

        if hi is not None:
            for start in range(n_units - hi):
                window = literals[start:start + hi + 1]
                if not ignore_edges:
                    patterns.append(("sum", window, hi))
                elif start > 0 and start + hi + 1 < n_units:
                    clause = [lit.Not() for lit in window]
                    clause += [other_before(start).Not(), other_after(start + hi + 1).Not()]
                    patterns.append(("clause", clause, 0))
        if lo is not None and lo >= 2:
            for start in range(1, n_units):
                for length in range(1, lo):
                    end = start + length
                    if end >= n_units:
                        break
                    clause = [literals[start - 1]] + [lit.Not() for lit in literals[start:end]] + [literals[end]]
                    patterns.append(("clause", clause, 0))
        return patterns

    def compile_stretch(c: Constraint):
        args = c.args
        lo, hi = args.get("min"), args.get("max")
        of = args.get("of", "work")
        patterns = []
        for g, (_, ids) in enumerate(groups_in_model(args, "each")):
            if not ids:
                continue
            for q, sequence in enumerate(args["sequences"]):
                prefix = f"{c.id}_{g}_{q}"
                worked = [held(ids, list(unit), f"{prefix}_unit{u}") for u, unit in enumerate(sequence)]
                literals = [w.Not() for w in worked] if of == "off" else worked
                patterns += stretch_patterns(literals, lo, hi, bool(args.get("ignore_edges")), prefix)
        if not patterns:
            return

        def hard(lit):
            for kind, lits, bound in patterns:
                if kind == "sum":
                    model.Add(sum(lits) <= bound).OnlyEnforceIf(lit)
                else:
                    model.AddBoolOr(lits).OnlyEnforceIf(lit)

        def measures():
            out = []
            for index, (kind, lits, bound) in enumerate(patterns):
                broken = model.NewBoolVar(f"{c.id}_broken{index}")
                if kind == "sum":
                    model.Add(sum(lits) <= bound + broken)
                else:
                    model.AddBoolOr(lits + [broken])
                out.append(broken)
            return out

        finish(c, hard, measures)

    def compile_transition(c: Constraint):
        pairs = [(int(a), int(b)) for a, b in c.args["pairs"]]
        holds = [
            (held(ids, [a], f"{c.id}_{g}_{a}"), held(ids, [b], f"{c.id}_{g}_{b}"))
            for g, (_, ids) in enumerate(groups_in_model(c.args, "each")) if ids
            for a, b in pairs
        ]
        if not holds:
            return

        def hard(lit):
            for first, then in holds:
                model.Add(first + then <= 1).OnlyEnforceIf(lit)

        def measures():
            out = []
            for index, (first, then) in enumerate(holds):
                both = model.NewBoolVar(f"{c.id}_both{index}")
                model.Add(first + then <= 1 + both)
                out.append(both)
            return out

        finish(c, hard, measures)

    COMPILERS = {
        "count": compile_count,
        "share": compile_share,
        "stretch": compile_stretch,
        "transition": compile_transition,
    }

    for c in active:
        compiler = COMPILERS.get(c.type)
        if compiler is None:
            raise OptimizationError(text.UNKNOWN_RULE_TYPE.format(type=c.type))
        compiler(c)

    if anchor_assignment and anchor_weight > 0:
        objective_terms.append(anchor_weight * sum(
            x[e, s] for e in entities for s in anchor_assignment.get(e, ()) if 0 <= s < k
        ))

    if hint_assignment:
        for e in entities:
            if e in hint_assignment:
                held = set(hint_assignment[e])
                for s in range(k):
                    model.AddHint(x[e, s], int(s in held))

    if assumption_lits:
        model.AddAssumptions(assumption_lits)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.time_limit_seconds
    # Pinned to a single worker: CP-SAT's parallel portfolio search is
    # inherently non-deterministic across separate solve() calls (workers
    # race and whichever finds/improves a solution first wins), even with a
    # fixed random_seed. Identical inputs (same data, rules and seed) must
    # always produce the exact same solution. Do not raise this above 1
    # without also fixing reproducibility some other way.
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = config.random_seed

    wall_time = 0.0
    phase_one_status = None
    if slack_terms:
        # Phase 1 of the lexicographic solve: bend the flexible rules as
        # little as possible. A single weighted objective would need a
        # big-M that swamps the float weights of the real goals; fixing
        # the minimum and re-solving keeps both exact.
        model.Minimize(sum(slack_terms))
        solver.parameters.max_time_in_seconds = max(1.0, config.time_limit_seconds * 0.5)
        first = solver.Solve(model)
        wall_time += solver.WallTime()
        if first in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            model.Add(sum(slack_terms) <= int(round(solver.ObjectiveValue())))
            model.ClearHints()
            for var in x.values():
                model.AddHint(var, solver.Value(var))
        else:
            # No bounded bend found in time. Going on would optimize the
            # soft goals with the bend unconstrained -- an assignment that
            # breaks the flexible rules by any amount. Report failure.
            phase_one_status = first
        solver.parameters.max_time_in_seconds = max(1.0, config.time_limit_seconds - wall_time)

    if phase_one_status is not None:
        status = phase_one_status
    else:
        if objective_terms:
            model.Maximize(sum(objective_terms))
        elif slack_terms:
            model.ClearObjective()
        status = solver.Solve(model)
        wall_time += solver.WallTime()
    status_name = solver.StatusName(status)

    assignment: dict = {}
    notes: list[str] = []
    conflicting_ids: list[str] = []
    is_feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    if is_feasible:
        for e in entities:
            assignment[e] = [s for s in range(k) if solver.Value(x[e, s]) == 1]
    else:
        if status == cp_model.INFEASIBLE and assumption_lits:
            try:
                conflicting_var_indices = solver.SufficientAssumptionsForInfeasibility()
                conflicting_ids = [
                    constraint_id_by_var_index[i]
                    for i in conflicting_var_indices
                    if i in constraint_id_by_var_index
                ]
            except Exception:
                conflicting_ids = []
        notes.append(text.NO_SOLUTION)

    return OptimizationResult(
        status_name=status_name,
        is_feasible=is_feasible,
        assignment=assignment,
        objective_value=solver.ObjectiveValue() if is_feasible and objective_terms else None,
        wall_time_seconds=wall_time,
        infeasibility_notes=notes,
        conflicting_constraint_ids=conflicting_ids,
    )
