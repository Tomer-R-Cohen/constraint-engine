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

import pandas as pd
from ortools.sat.python import cp_model

from constraint_engine import text
from constraint_engine.constraints import (
    DEFAULT_WEIGHT,
    DEFAULT_WEIGHT_MUTUAL,
    DEFAULT_WEIGHT_TWO,
    Constraint,
    load_slot_groups,
    resolve_group_members,
    selected_slots,
    subgroups,
)


class OptimizationError(Exception):
    """Raised when the optimizer cannot be run (e.g. bad configuration)."""


@dataclass
class SolverConfig:
    """Run parameters. Rules and weights live in the Constraint list passed
    to optimize(), not here."""

    num_slots: int = 6
    # How many slots each entity holds, (min, max). (1, 1) is placement:
    # every entity in exactly one slot. Rostering widens it and adds `load`
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
        if c.type == "fixed":
            slot = c.args["slot"]
            if slot < 0 or slot >= k:
                raise OptimizationError(
                    text.FIXED_TO_MISSING_SLOT.format(entity=c.args["entity"], slot=slot + 1, num_slots=k)
                )
        if c.type in ("capacity", "load", "run", "transition"):
            named = (list(c.args.get("slots") or ())
                     + [s for group in (c.args.get("slot_groups") or c.args.get("units") or ()) for s in group]
                     + [s for pair in c.args.get("pairs") or () for s in pair])
            for slot in named:
                if slot < 0 or slot >= k:
                    raise OptimizationError(
                        text.RULE_NAMES_MISSING_SLOT.format(label=c.label, slot=slot + 1, num_slots=k)
                    )

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

    def group_members(group: dict) -> list:
        return [m for m in resolve_group_members(df, group) if m in entity_set]

    def slot_counts_for_group(group: dict, slots=None):
        members = group_members(group)
        return [sum(x[e, s] for e in members) for s in (range(k) if slots is None else slots)]

    def band_shortfall(expr, lo, hi, name: str):
        """Units by which `expr` falls outside [lo, hi], as one expression."""
        units = []
        if lo is not None:
            under = model.NewIntVar(0, max(0, int(lo)), f"{name}_under")
            model.Add(expr + under >= lo)
            units.append(under)
        if hi is not None:
            over = model.NewIntVar(0, max(n, k), f"{name}_over")
            model.Add(expr - over <= hi)
            units.append(over)
        return sum(units)

    def add_spread_var(counts, name_prefix):
        max_v = model.NewIntVar(0, n, f"{name_prefix}_max")
        min_v = model.NewIntVar(0, n, f"{name_prefix}_min")
        model.AddMaxEquality(max_v, counts)
        model.AddMinEquality(min_v, counts)
        spread = model.NewIntVar(0, n, f"{name_prefix}_spread")
        model.Add(spread == max_v - min_v)
        return spread

    def is_flexible(c: Constraint) -> bool:
        return c.hard and c.id in flexible_ids

    # ---- per-type compilers ----

    def compile_capacity(c: Constraint):
        counts = slot_counts_for_group(c.args["group"], selected_slots(c.args, k))
        lo = c.args.get("min")
        hi = c.args.get("max")
        if is_flexible(c):
            for index, expr in enumerate(counts):
                slack_terms.append(band_shortfall(expr, lo, hi, f"{c.id}_{index}"))
        elif c.hard:
            lit = enable_lit(c)
            for expr in counts:
                if lo is not None:
                    model.Add(expr >= lo).OnlyEnforceIf(lit)
                if hi is not None:
                    model.Add(expr <= hi).OnlyEnforceIf(lit)
        else:
            weight = c.args.get("weight", DEFAULT_WEIGHT[c.type])
            if weight <= 0:
                return
            # A preference for the band: penalize every unit outside it.
            objective_terms.append(
                -weight * sum(band_shortfall(expr, lo, hi, f"{c.id}_{index}") for index, expr in enumerate(counts))
            )

    def compile_load(c: Constraint):
        lo = c.args.get("min")
        hi = c.args.get("max")
        members = group_members(c.args["group"])
        loads = {
            (e, index): sum(x[e, s] for s in slots)
            for e in members
            for index, slots in enumerate(load_slot_groups(c.args, k))
        }
        if is_flexible(c):
            for (e, index), expr in loads.items():
                slack_terms.append(band_shortfall(expr, lo, hi, f"{c.id}_{e}_{index}"))
        elif c.hard:
            lit = enable_lit(c)
            for expr in loads.values():
                if lo is not None:
                    model.Add(expr >= lo).OnlyEnforceIf(lit)
                if hi is not None:
                    model.Add(expr <= hi).OnlyEnforceIf(lit)
        else:
            weight = c.args.get("weight", DEFAULT_WEIGHT[c.type])
            if weight <= 0:
                return
            objective_terms.append(
                -weight * sum(band_shortfall(expr, lo, hi, f"{c.id}_{e}_{index}") for (e, index), expr in loads.items())
            )

    def worked_literals(e, units: list[list[int]], of: str, prefix: str) -> list:
        """One literal per time unit: true when the entity works the unit
        (holds any of its slots), or, for of="off", when it does not."""
        literals = []
        for index, unit in enumerate(units):
            w = model.NewBoolVar(f"{prefix}_works_{e}_{index}")
            if unit:
                model.AddMaxEquality(w, [x[e, s] for s in unit])
            else:
                model.Add(w == 0)  # nothing to hold: never worked
            literals.append(w.Not() if of == "off" else w)
        return literals

    def run_patterns(literals: list, lo, hi) -> list[tuple[str, list, int]]:
        """Each way a stretch can break the band, as (kind, literals, bound):
        ("sum", window, hi) -- a window of hi+1 units all in the stretch;
        ("clause", lits, 0) -- a stretch shorter than lo with a known unit
        on both sides, written as the clause that forbids it."""
        patterns = []
        n_units = len(literals)
        if hi is not None:
            for start in range(n_units - hi):
                patterns.append(("sum", literals[start:start + hi + 1], hi))
        if lo is not None and lo >= 2:
            for start in range(1, n_units):
                for length in range(1, lo):
                    end = start + length
                    if end >= n_units:
                        break
                    clause = [literals[start - 1]] + [lit.Not() for lit in literals[start:end]] + [literals[end]]
                    patterns.append(("clause", clause, 0))
        return patterns

    def compile_run(c: Constraint):
        units = [list(unit) for unit in c.args["units"]]
        lo, hi = c.args.get("min"), c.args.get("max")
        of = c.args.get("of", "work")
        patterns = [p for e in group_members(c.args["group"]) for p in run_patterns(worked_literals(e, units, of, c.id), lo, hi)]
        if not patterns:
            return
        lit = enable_lit(c) if c.hard and not is_flexible(c) else None
        penalties = []
        for index, (kind, lits, bound) in enumerate(patterns):
            if lit is not None:
                if kind == "sum":
                    model.Add(sum(lits) <= bound).OnlyEnforceIf(lit)
                else:
                    model.AddBoolOr(lits).OnlyEnforceIf(lit)
                continue
            broken = model.NewBoolVar(f"{c.id}_broken_{index}")
            if kind == "sum":
                model.Add(sum(lits) <= bound + broken)
            else:
                model.AddBoolOr(lits + [broken])
            penalties.append(broken)
        if is_flexible(c):
            slack_terms.extend(penalties)
        elif not c.hard:
            weight = c.args.get("weight", DEFAULT_WEIGHT[c.type])
            if weight > 0:
                objective_terms.append(-weight * sum(penalties))

    def compile_transition(c: Constraint):
        pairs = [(int(a), int(b)) for a, b in c.args["pairs"]]
        members = group_members(c.args["group"])
        if not pairs or not members:
            return
        lit = enable_lit(c) if c.hard and not is_flexible(c) else None
        penalties = []
        for e in members:
            for a, b in pairs:
                if lit is not None:
                    model.Add(x[e, a] + x[e, b] <= 1).OnlyEnforceIf(lit)
                    continue
                both = model.NewBoolVar(f"{c.id}_both_{e}_{a}_{b}")
                model.Add(x[e, a] + x[e, b] <= 1 + both)
                penalties.append(both)
        if is_flexible(c):
            slack_terms.extend(penalties)
        elif not c.hard:
            weight = c.args.get("weight", DEFAULT_WEIGHT[c.type])
            if weight > 0:
                objective_terms.append(-weight * sum(penalties))

    def compile_balance(c: Constraint):
        weight = c.args.get("weight", DEFAULT_WEIGHT[c.type])
        if not c.hard and weight <= 0:
            return
        # A multi-group selector gets one spread var per sub-group; the
        # rule's total is their sum -- same math as separate weighted rules,
        # just presented (and toggled, and referenced by id) as one rule.
        groups = subgroups(df, c.args["group"])
        spreads = [add_spread_var(slot_counts_for_group(g), f"{c.id}_{i}") for i, g in enumerate(groups)]
        if not spreads:
            return
        if is_flexible(c):
            slack_terms.extend(spreads)
        elif c.hard:
            lit = enable_lit(c)
            for spread in spreads:
                model.Add(spread == 0).OnlyEnforceIf(lit)
        else:
            objective_terms.append(-weight * sum(spreads))

    def compile_separate(c: Constraint):
        a, b = c.args["entity_a"], c.args["entity_b"]
        if a not in entity_set or b not in entity_set:
            return
        if is_flexible(c):
            slack_terms.append(get_same_slot_var(a, b))
        elif c.hard:
            lit = enable_lit(c)
            for s in range(k):
                model.Add(x[a, s] + x[b, s] <= 1).OnlyEnforceIf(lit)
        else:
            weight = c.args.get("weight", DEFAULT_WEIGHT[c.type])
            objective_terms.append(-weight * get_same_slot_var(a, b))

    def compile_together(c: Constraint):
        a, b = c.args["entity_a"], c.args["entity_b"]
        if a not in entity_set or b not in entity_set:
            return
        if is_flexible(c):
            slack_terms.append(1 - get_same_slot_var(a, b))
        elif c.hard:
            lit = enable_lit(c)
            if single:
                for s in range(k):
                    model.Add(x[a, s] == x[b, s]).OnlyEnforceIf(lit)
            else:
                model.Add(get_same_slot_var(a, b) == 1).OnlyEnforceIf(lit)
        else:
            weight = c.args.get("weight", DEFAULT_WEIGHT[c.type])
            objective_terms.append(weight * get_same_slot_var(a, b))

    def compile_at_least_one_of(c: Constraint):
        e = c.args["entity"]
        candidates = [m for m in c.args["candidates"] if m in entity_set and m != e]
        if e not in entity_set or not candidates:
            return
        co_vars = [get_same_slot_var(e, m) for m in candidates]
        if is_flexible(c):
            met = model.NewBoolVar(f"{c.id}_met")
            model.Add(sum(co_vars) >= 1).OnlyEnforceIf(met)
            model.Add(sum(co_vars) == 0).OnlyEnforceIf(met.Not())
            slack_terms.append(1 - met)
        elif c.hard:
            lit = enable_lit(c)
            model.Add(sum(co_vars) >= 1).OnlyEnforceIf(lit)
        else:
            weight = c.args.get("weight", DEFAULT_WEIGHT[c.type])
            satisfied = model.NewBoolVar(f"{c.id}_satisfied")
            model.Add(sum(co_vars) >= 1).OnlyEnforceIf(satisfied)
            model.Add(sum(co_vars) == 0).OnlyEnforceIf(satisfied.Not())
            objective_terms.append(weight * satisfied)

    def compile_fixed(c: Constraint):
        e = c.args["entity"]
        s = c.args["slot"]
        if e not in entity_set:
            return
        if is_flexible(c):
            slack_terms.append(1 - x[e, s])
        elif c.hard:
            lit = enable_lit(c)
            model.Add(x[e, s] == 1).OnlyEnforceIf(lit)
        else:
            weight = c.args.get("weight", DEFAULT_WEIGHT[c.type])
            objective_terms.append(weight * x[e, s])

    def compile_partner_requests(c: Constraint):
        requests = c.args.get("requests", {})
        weight_mutual = c.args.get("weight_mutual", DEFAULT_WEIGHT_MUTUAL)
        weight_two = c.args.get("weight_two", DEFAULT_WEIGHT_TWO)
        for e in entities:
            requested = [r for r in requests.get(e, []) if r in entity_set and r != e]
            if not requested:
                continue
            mutuals = [r for r in requested if e in requests.get(r, [])]
            if mutuals and weight_mutual > 0:
                co_vars = [get_same_slot_var(e, m) for m in mutuals]
                hm = model.NewBoolVar(f"{c.id}_mutual_{e}")
                model.Add(sum(co_vars) >= 1).OnlyEnforceIf(hm)
                model.Add(sum(co_vars) == 0).OnlyEnforceIf(hm.Not())
                objective_terms.append(weight_mutual * hm)
            if weight_two > 0:
                co_vars_all = [get_same_slot_var(e, r) for r in requested]
                cnt = model.NewIntVar(0, len(co_vars_all), f"{c.id}_count_{e}")
                model.Add(cnt == sum(co_vars_all))
                tf = model.NewBoolVar(f"{c.id}_two_{e}")
                model.Add(cnt >= 2).OnlyEnforceIf(tf)
                model.Add(cnt <= 1).OnlyEnforceIf(tf.Not())
                objective_terms.append(weight_two * tf)

    COMPILERS = {
        "capacity": compile_capacity,
        "load": compile_load,
        "run": compile_run,
        "transition": compile_transition,
        "balance": compile_balance,
        "separate": compile_separate,
        "together": compile_together,
        "at_least_one_of": compile_at_least_one_of,
        "fixed": compile_fixed,
        "partner_requests": compile_partner_requests,
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
