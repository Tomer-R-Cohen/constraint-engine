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

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Optional

import pandas as pd

from constraint_engine import text
from constraint_engine.constraints import DEFAULT_WEIGHT, DEFAULT_WEIGHT_MUTUAL, DEFAULT_WEIGHT_TWO, Constraint
from constraint_engine.dataset_schema import describe_columns, prepare_entities
from constraint_engine.decision_support import generate_portfolio, negotiation_question
from constraint_engine.optimizer import SolverConfig
from constraint_engine.readback import describe_rule
from constraint_engine.spec import (
    AtLeastOneOfRule,
    BalanceRule,
    CapacityRule,
    EntitySelector,
    FixedRule,
    LoadRule,
    PartnerRequestsRule,
    ProblemSpec,
    SeparateRule,
    SlotSelector,
    TogetherRule,
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

    def weight_args(self, rule, args: dict) -> dict:
        if rule.mode == "soft":
            factor = PRIORITY_FACTOR[rule.level]
            if rule.type == "partner_requests":
                args["weight_mutual"] = DEFAULT_WEIGHT_MUTUAL * factor
                args["weight_two"] = DEFAULT_WEIGHT_TWO * factor
            else:
                args["weight"] = DEFAULT_WEIGHT[rule.type] * factor
        return args

    def rule(self, rule) -> Optional[Constraint]:
        before = len(self.problems)
        rid = rule.id
        args: dict[str, Any]
        request_count = None
        if isinstance(rule, CapacityRule):
            args = {"group": self.entity_group(rid, rule.entities), "min": rule.min, "max": rule.max}
            chosen = self.slots(rid, rule.slots)
            if chosen is not None:
                args["slots"] = chosen
        elif isinstance(rule, LoadRule):
            args = {"group": self.entity_group(rid, rule.entities), "min": rule.min, "max": rule.max}
            chosen = self.slots(rid, rule.slots)
            if rule.per is not None:
                args["slot_groups"] = self.per_groups(rid, rule.per, chosen)
            elif chosen is not None:
                args["slots"] = chosen
        elif isinstance(rule, BalanceRule):
            if rule.by_column is not None:
                ok = self.column(rid, rule.by_column, flag=False)
                args = {"group": {"kind": "column_all_values", "column": rule.by_column} if ok else None}
            elif rule.flag_columns is not None:
                ok = all([self.column(rid, c, flag=True) for c in rule.flag_columns])
                args = {"group": {"kind": "columns", "columns": list(rule.flag_columns)} if ok else None}
            else:
                args = {"group": self.entity_group(rid, rule.entities)}
        elif isinstance(rule, (TogetherRule, SeparateRule)):
            a, b = self.entity(rid, rule.entity_a), self.entity(rid, rule.entity_b)
            if a is not None and a == b:
                self.problem(rid, text.SPEC_SAME_ENTITY_TWICE.format(entity=rule.entity_a))
            args = {"entity_a": a, "entity_b": b}
        elif isinstance(rule, AtLeastOneOfRule):
            args = {"entity": self.entity(rid, rule.entity),
                    "candidates": [self.entity(rid, c) for c in rule.candidates]}
        elif isinstance(rule, FixedRule):
            if rule.slot not in self.slot_index:
                self.problem(rid, text.SPEC_UNKNOWN_SLOT.format(slot=rule.slot))
            args = {"entity": self.entity(rid, rule.entity), "slot": self.slot_index.get(rule.slot)}
        elif isinstance(rule, PartnerRequestsRule):
            requests = {}
            for requester, asked in rule.requests.items():
                e = self.entity(rid, requester)
                wanted = [self.entity(rid, other) for other in asked]
                if e is not None:
                    requests[e] = [w for w in wanted if w is not None]
            args = {"requests": requests}
            request_count = sum(1 for asked in requests.values() if asked)
        else:  # pragma: no cover - the spec's union is closed
            raise TypeError(f"cannot compile {type(rule).__name__}")
        if len(self.problems) > before:
            return None
        return Constraint(
            type=rule.type, hard=rule.mode == "hard", args=self.weight_args(rule, args),
            label=describe_rule(rule, self.spec, request_count), source="chat", active=rule.active, id=rule.id,
        )


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
