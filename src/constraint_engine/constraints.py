"""Unified rule representation.

Every rule the solver can apply is a `Constraint`: a catalog `type`, a
type-specific `args` dict, and a per-instance hard/soft flag. No rule type
is inherently hard or soft. The optimizer, the independent verifier and the
pre-solve checks all work over one list of these.

Entities are the rows of the data frame and are identified by its index.
Slots are numbered 0..num_slots-1.

Rule types and their args:

    capacity          {"group": <selector>, "min": int|None, "max": int|None}
                      How many of the group may land in each slot.
    balance           {"group": <selector>, "weight": float}
                      Spread the group as evenly as possible over the slots.
    together          {"entity_a": id, "entity_b": id}
    separate          {"entity_a": id, "entity_b": id}
    at_least_one_of   {"entity": id, "candidates": [id, ...]}
                      The entity shares a slot with at least one candidate.
    fixed             {"entity": id, "slot": int}
    partner_requests  {"requests": {id: [id, ...]}, "weight_mutual": float,
                       "weight_two": float}
                      Soft goal: each requester shares a slot with a mutual
                      request, and with at least two requested partners.

Soft rules may carry "weight" in args (partner_requests carries its two
weights instead).

Group selectors:

    {"kind": "all"}                                   every entity
    {"kind": "column", "column": c}                   rows where column c is true
    {"kind": "column_value", "column": c, "value": v} rows where column c == v
    {"kind": "members", "members": [id, ...]}         an explicit list
    {"kind": "column_all_values", "column": c}        balance only: each distinct
                                                      value of c, under one rule
    {"kind": "columns", "columns": [c, ...]}          balance only: each flag
                                                      column, under one rule
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

ConstraintType = Literal[
    "capacity", "balance", "together", "separate", "at_least_one_of", "fixed", "partner_requests"
]
ConstraintSource = Literal["builtin_default", "chat", "manual"]

# Weight a soft rule gets when its args carry none.
DEFAULT_WEIGHT = {
    "capacity": 1.0,
    "balance": 1.0,
    "together": 5.0,
    "separate": 5.0,
    "at_least_one_of": 5.0,
    "fixed": 2.0,
}
DEFAULT_WEIGHT_MUTUAL = 5.0
DEFAULT_WEIGHT_TWO = 3.0


@dataclass
class Constraint:
    type: ConstraintType
    hard: bool
    args: dict
    label: str
    source: ConstraintSource = "manual"
    active: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


def resolve_group_members(df: pd.DataFrame, group: dict) -> list:
    """Return the ids (index values) of the entities a selector picks."""
    kind = group.get("kind")
    if kind == "all":
        return df.index.tolist()
    if kind == "column":
        column = df[group["column"]]
        return column.index[column.fillna(False).astype(bool)].tolist()
    if kind == "column_value":
        column = df[group["column"]]
        return column.index[column == group["value"]].tolist()
    if kind == "members":
        known = set(df.index)
        return [m for m in group["members"] if m in known]
    raise ValueError(f"unknown group kind: {kind!r}")


def subgroups(df: pd.DataFrame, group: dict) -> list[dict]:
    """Split a multi-group selector into the single groups it covers.

    "column_all_values"/"columns" put several groups under one rule (e.g.
    "balance by school" is one rule, not one per school). Every other
    selector is its own single group.
    """
    kind = group.get("kind")
    if kind == "column_all_values":
        column = group["column"]
        return [{"kind": "column_value", "column": column, "value": v} for v in df[column].dropna().unique()]
    if kind == "columns":
        return [{"kind": "column", "column": c} for c in group["columns"]]
    return [group]
