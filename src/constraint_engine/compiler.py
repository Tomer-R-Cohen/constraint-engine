"""From a problem spec plus its data to solver inputs, and back.

`compile_spec` checks every reference in the spec against the entity table
(columns, values, entity ids, slot ids and attributes) and turns each spec
rule into exactly one engine `Constraint` with the same id, so conflicts,
checks and options all point back at the user's rules. Every problem found
is reported at once, in plain English, before any solve.

`solve_spec` runs a round of options and returns them in spec terms (slot
ids, not indexes), stamped with what produced them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Optional

import pandas as pd

from constraint_engine import text
from constraint_engine.constraints import DEFAULT_WEIGHT, Constraint, resolve_group_members
from constraint_engine.dataset_schema import describe_columns, prepare_entities
from constraint_engine.decision_support import generate_portfolio, negotiation_question
from constraint_engine.optimizer import SolverConfig
from constraint_engine.readback import describe_rule
from constraint_engine.spec import (
    CountRule,
    EntitySelector,
    PerAttribute,
    PerColumn,
    ProblemSpec,
    ShareRule,
    SlotSelector,
    StretchRule,
    TransitionRule,
    data_hash,
    spec_hash,
)

# What each priority level multiplies a rule type's default weight by. Ordinal
# levels a person can reason about, a factor of three apart.
PRIORITY_FACTOR = {"low": 1 / 3, "medium": 1.0, "high": 3.0}


class SpecError(Exception):
    """The spec does not fit the data. `problems` lists every reason."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


@dataclass
class CompiledProblem:
    spec: ProblemSpec
    df: pd.DataFrame
    config: SolverConfig
    constraints: list[Constraint]
    slot_ids: list[str]

    def named(self, assignment: dict) -> dict:
        """{entity: [slot index]} -> {entity: [slot id]}."""
        return {e: [self.slot_ids[s] for s in slots] for e, slots in assignment.items()}

    def indexed(self, assignment: dict) -> dict:
        """{entity: [slot id]} -> {entity: [slot index]}."""
        index = {slot_id: i for i, slot_id in enumerate(self.slot_ids)}
        return {e: sorted(index[s] for s in slots) for e, slots in assignment.items()}


def entity_table(raw_df: pd.DataFrame, spec: ProblemSpec) -> pd.DataFrame:
    """The spec's entity table from a raw sheet: columns normalized by kind,
    rows indexed by the spec's id column."""
    id_column = spec.entities.id_column
    if id_column is not None and id_column not in raw_df.columns:
        raise SpecError([text.SPEC_UNKNOWN_ID_COLUMN.format(column=id_column, columns=_join(raw_df.columns))])
    schema = describe_columns(raw_df, skip={id_column} if id_column else set())
    return prepare_entities(raw_df, schema, id_column=id_column)


def _join(items) -> str:
    return ", ".join(str(i) for i in items)


def _split_names(cell) -> list[str]:
    """Ids listed in one cell: "Ana, Ben; Cy" -> ["Ana", "Ben", "Cy"]."""
    if cell is None or (isinstance(cell, float) and cell != cell):
        return []
    return [part.strip() for part in re.split(r"[,;\n]", str(cell)) if part.strip()]


def _same(a, b) -> bool:
    """Spec values arrive as JSON; data values as pandas gave them. "3" in a
    spec means the 3 in the sheet."""
    return a == b or str(a) == str(b)


class _Compiler:
    def __init__(self, spec: ProblemSpec, df: pd.DataFrame):
        self.spec = spec
        self.df = df
        self.problems: list[str] = []
        self.slot_index = {slot.id: i for i, slot in enumerate(spec.slots)}
        self.attributes = sorted({a for slot in spec.slots for a in slot.attributes})
        self._ids = {str(e): e for e in df.index}

    def problem(self, rule_id: str, message: str) -> None:
        self.problems.append(text.SPEC_PROBLEM.format(rule=rule_id, message=message))

    # ---- references ----

    def entity(self, rule_id: str, ref) -> Any:
        if ref in self.df.index:
            return ref
        if str(ref) in self._ids:
            return self._ids[str(ref)]
        self.problem(rule_id, text.SPEC_UNKNOWN_ENTITY.format(entity=ref))
        return None

    def column(self, rule_id: str, column: str, flag: bool) -> bool:
        if column not in self.df.columns:
            self.problem(rule_id, text.SPEC_UNKNOWN_COLUMN.format(column=column, columns=_join(self.df.columns)))
            return False
        if flag:
            values = set(self.df[column].dropna().tolist())
            if not values <= {True, False}:
                sample = _join(sorted(map(str, values))[:8])
                self.problem(rule_id, text.SPEC_NOT_A_FLAG.format(column=column, values=sample))
                return False
        return True

    def entity_group(self, rule_id: str, selector: Optional[EntitySelector]) -> Optional[dict]:
        if selector is None or (selector.column is None and selector.members is None):
            return {"kind": "all"}
        if selector.members is not None:
            members = [self.entity(rule_id, m) for m in selector.members]
            return {"kind": "members", "members": [m for m in members if m is not None]}
        if selector.value is None:
            return {"kind": "column", "column": selector.column} if self.column(rule_id, selector.column, flag=True) else None
        if not self.column(rule_id, selector.column, flag=False):
            return None
        present = self.df[selector.column].dropna().unique().tolist()
        match = next((v for v in present if _same(v, selector.value)), None)
        if match is None:
            self.problem(rule_id, text.SPEC_UNKNOWN_VALUE.format(
                column=selector.column, value=selector.value, values=_join(sorted(map(str, present))[:12])))
            return None
        return {"kind": "column_value", "column": selector.column, "value": match}

    def slots(self, rule_id: str, selector: SlotSelector) -> Optional[list[int]]:
        """Selected slot indexes, or None for every slot."""
        if selector.ids is not None:
            chosen = []
            for slot_id in selector.ids:
                if slot_id in self.slot_index:
                    chosen.append(self.slot_index[slot_id])
                else:
                    self.problem(rule_id, text.SPEC_UNKNOWN_SLOT.format(slot=slot_id))
            return sorted(set(chosen))
        if selector.where:
            for attribute in selector.where:
                if attribute not in self.attributes:
                    self.problem(rule_id, text.SPEC_UNKNOWN_ATTRIBUTE.format(
                        attribute=attribute, attributes=_join(self.attributes) or "-"))
                    return []
            chosen = [
                i for i, slot in enumerate(self.spec.slots)
                if all(
                    attribute in slot.attributes
                    and any(_same(slot.attributes[attribute], v) for v in (wanted if isinstance(wanted, list) else [wanted]))
                    for attribute, wanted in selector.where.items()
                )
            ]
            if not chosen:
                self.problem(rule_id, text.SPEC_NO_SLOTS_SELECTED)
            return chosen
        return None

    def per_groups(self, rule_id: str, attribute: str, chosen: Optional[list[int]]) -> list[list[int]]:
        if attribute not in self.attributes:
            self.problem(rule_id, text.SPEC_UNKNOWN_ATTRIBUTE.format(attribute=attribute, attributes=_join(self.attributes) or "-"))
            return []
        groups: dict[Any, list[int]] = {}
        for i in (range(len(self.spec.slots)) if chosen is None else chosen):
            slot = self.spec.slots[i]
            if attribute not in slot.attributes:
                self.problem(rule_id, text.SPEC_SLOT_MISSING_ATTRIBUTE.format(slot=slot.id, attribute=attribute))
                continue
            groups.setdefault(slot.attributes[attribute], []).append(i)
        return list(groups.values())

    # ---- rules ----

    def item_grouping(self, rule_id: str, per_item):
        if isinstance(per_item, str):
            return per_item
        if per_item.column is not None:
            return {"column": per_item.column} if self.column(rule_id, per_item.column, flag=False) else None
        ok = all([self.column(rule_id, c, flag=True) for c in per_item.flag_columns])
        return {"columns": list(per_item.flag_columns)} if ok else None

    def units(self, rule_id: str, per: str, keep: Optional[list[int]], within_each: Optional[str] = None):
        """Time units in slot-list order, each the slots of one value of
        `per` (restricted to `keep`); one sequence, or one per value of
        `within_each`."""
        if within_each is None:
            return [[[s for s in unit if keep is None or s in keep] for unit in self.per_groups(rule_id, per, None)]]
        sequences = []
        for outer in self.per_groups(rule_id, within_each, None):
            inner: dict[Any, list[int]] = {}
            for i in outer:
                slot = self.spec.slots[i]
                if per not in slot.attributes:
                    self.problem(rule_id, text.SPEC_SLOT_MISSING_ATTRIBUTE.format(slot=slot.id, attribute=per))
                    continue
                inner.setdefault(slot.attributes[per], []).append(i)
            sequences.append([[s for s in unit if keep is None or s in keep] for unit in inner.values()])
        return sequences

    def weights(self, rule_id: str, rule: CountRule, group: Optional[dict]):
        if rule.sum is None:
            return None
        if rule.sum.item_column is not None:
            column = rule.sum.item_column
            if not self.column(rule_id, column, flag=False) or group is None:
                return None
            members = resolve_group_members(self.df, group)
            values = pd.to_numeric(self.df.loc[members, column], errors="coerce")
            bad = [str(e) for e, v in values.items() if pd.isna(v) or v < 0]
            if bad:
                self.problem(rule_id, text.SPEC_NOT_NUMERIC.format(column=column, bad=_join(bad[:8])))
                return None
            return {"items": {e: float(v) for e, v in values.items()}}
        attribute = rule.sum.slot_attribute
        if attribute not in self.attributes:
            self.problem(rule_id, text.SPEC_UNKNOWN_ATTRIBUTE.format(attribute=attribute, attributes=_join(self.attributes) or "-"))
            return None
        values = []
        for slot in self.spec.slots:
            value = slot.attributes.get(attribute, 0)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                self.problem(rule_id, text.SPEC_SLOT_NOT_NUMERIC.format(slot=slot.id, attribute=attribute))
                return None
            values.append(float(value))
        return {"slots": values}

    def rule(self, rule) -> Optional[Constraint]:
        before = len(self.problems)
        rid = rule.id
        args: dict[str, Any]
        if isinstance(rule, CountRule):
            group = self.entity_group(rid, rule.items)
            chosen = self.slots(rid, rule.slots)
            args = {"items": group, "item_groups": self.item_grouping(rid, rule.per_item)}
            if isinstance(rule.per_slot, PerAttribute):
                attribute = rule.per_slot.attribute
                groups = self.per_groups(rid, attribute, chosen)
                args["slot_groups"] = groups
                args["slot_group_labels"] = [
                    f"{attribute} {self.spec.slots[g[0]].attributes.get(attribute)}" if g else "" for g in groups
                ]
            else:
                args["slot_groups"] = rule.per_slot
                if chosen is not None:
                    args["slots"] = chosen
            weights = self.weights(rid, rule, group)
            if weights:
                args["weights"] = weights
            for key in ("min", "max", "even", "max_gap"):
                if getattr(rule, key) is not None:
                    args[key] = getattr(rule, key)
        elif isinstance(rule, ShareRule):
            if rule.with_column is None:
                item = self.entity(rid, rule.item)
                others = [self.entity(rid, o) for o in rule.with_]
                if item is not None and item in others:
                    self.problem(rid, text.SPEC_SAME_ENTITY_TWICE.format(entity=rule.item))
                cases = [{"item": item, "with": others}]
            else:
                cases = []
                group = self.entity_group(rid, rule.items)
                if self.column(rid, rule.with_column, flag=False) and group is not None:
                    for e in resolve_group_members(self.df, group):
                        named = _split_names(self.df.at[e, rule.with_column])
                        resolved = [self.entity(rid, name) for name in named]
                        resolved = [o for o in resolved if o is not None and o != e]
                        if resolved:
                            cases.append({"item": e, "with": resolved})
            for case in cases:
                case.update({"min": rule.min, "max": rule.max})
            args = {"cases": cases}
        elif isinstance(rule, StretchRule):
            chosen = self.slots(rid, rule.slots)
            args = {"items": self.entity_group(rid, rule.items), "item_groups": self.item_grouping(rid, rule.per_item),
                    "sequences": self.units(rid, rule.per, chosen, rule.within_each),
                    "of": rule.of, "min": rule.min, "max": rule.max, "ignore_edges": rule.ignore_edges}
        elif isinstance(rule, TransitionRule):
            after = self.slots(rid, rule.after)
            followed = self.slots(rid, rule.not_followed_by)
            first = None if after is None else set(after)
            then = None if followed is None else set(followed)
            (units,) = self.units(rid, rule.per, None)
            pairs = [
                [a, b]
                for i, unit in enumerate(units)
                for later in units[i + 1:i + 1 + rule.next]
                for a in unit if first is None or a in first
                for b in later if then is None or b in then
            ]
            args = {"items": self.entity_group(rid, rule.items), "item_groups": self.item_grouping(rid, rule.per_item),
                    "pairs": pairs}
        else:  # pragma: no cover - the spec's union is closed
            raise TypeError(f"cannot compile {type(rule).__name__}")
        if len(self.problems) > before:
            return None
        if rule.mode == "soft":
            args["weight"] = DEFAULT_WEIGHT[rule.type] * PRIORITY_FACTOR[rule.level]
        return Constraint(type=rule.type, hard=rule.mode == "hard", args=args, label=describe_rule(rule, self.spec),
                          source="chat", active=rule.active, id=rule.id)


def compile_spec(spec: ProblemSpec, df: pd.DataFrame) -> CompiledProblem:
    """Check the spec against the entity table and build the solver inputs.

    Raises:
        SpecError: listing every reference that does not fit the data.
    """
    compiler = _Compiler(spec, df)
    if df.index.has_duplicates:
        compiler.problems.append(text.SPEC_DUPLICATE_ENTITIES)
    constraints = [c for c in (compiler.rule(rule) for rule in spec.rules) if c is not None]
    lo, hi = spec.settings.slots_per_entity
    if hi > len(spec.slots):
        compiler.problems.append(text.SPEC_TOO_MANY_SLOTS_PER_ENTITY.format(max=hi, count=len(spec.slots)))
    if spec.settings.slots_interchangeable and (lo, hi) != (1, 1):
        compiler.problems.append(text.INTERCHANGEABLE_NEEDS_SINGLE_SLOT)
    if compiler.problems:
        raise SpecError(compiler.problems)
    slot_ids = [slot.id for slot in spec.slots]
    config = SolverConfig(
        num_slots=len(slot_ids),
        slots_per_entity=(lo, hi),
        slots_interchangeable=spec.settings.slots_interchangeable,
        slot_names=slot_ids,
        time_limit_seconds=spec.settings.time_limit_seconds,
        random_seed=spec.settings.seed,
    )
    return CompiledProblem(spec, df, config, constraints, slot_ids)


def check_spec(spec: ProblemSpec, df: pd.DataFrame) -> list[str]:
    """Every problem compile_spec would raise, as a list (empty if none)."""
    try:
        compile_spec(spec, df)
    except SpecError as error:
        return error.problems
    return []


def _engine_version() -> str:
    try:
        return version("constraint-engine")
    except PackageNotFoundError:  # pragma: no cover - running from a source tree
        return "unknown"


def solve_spec(spec: ProblemSpec, df: pd.DataFrame, *, time_budget_seconds: Optional[float] = None,
               anchor: Optional[dict] = None, emphasis: str = "balanced") -> dict:
    """One round of options for the spec, in spec terms.

    The result records the spec and data fingerprints, engine version, seed
    and settings, so an answer can be stored and later matched to exactly
    what produced it instead of being re-solved.
    """
    problem = compile_spec(spec, df)
    budget = spec.settings.time_limit_seconds if time_budget_seconds is None else time_budget_seconds
    options, conflicts = generate_portfolio(
        problem.df, problem.config, problem.constraints, time_budget_seconds=budget,
        anchor=problem.indexed(anchor) if anchor else None, emphasis=emphasis,
    )
    payload = []
    for option in options:
        item = option.to_dict()
        item["assignment"] = problem.named(option.assignment)
        payload.append(item)
    return {
        "spec_hash": spec_hash(spec),
        "data_hash": data_hash(df),
        "engine_version": _engine_version(),
        "seed": spec.settings.seed,
        "settings": spec.settings.model_dump(mode="json"),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "none" if not options else ("perfect" if all(o.verification.is_valid for o in options) else "compromise"),
        "conflicting_rule_ids": conflicts,
        "options": payload,
        "question": negotiation_question(options),
    }
