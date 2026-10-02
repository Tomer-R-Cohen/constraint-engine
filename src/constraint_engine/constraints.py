"""The rule representation: four general building blocks.

Every rule is a `Constraint`: a block `type`, block-specific `args`, and a
per-instance hard/soft flag. No block is inherently hard or soft.

Items (what is placed) are the rows of the data frame, identified by its
index. Slots (where they go) are numbered 0..num_slots-1. An assignment maps
each item to the sorted list of slots it holds; how many it may hold is
`SolverConfig.slots_per_entity`. "Shares a slot" means two items hold at
least one slot in common.

Blocks and their args:

    count       How many placements (or how much of a weight) fall in each
                cell of a grid of item groups x slot groups.
                {"items": <selector>,          which items (default: all)
                 "item_groups": <grouping>,    "all" | "each" | {"column": c}
                                               | {"columns": [flag, ...]}
                 "slots": [int, ...],          which slots (default: all)
                 "slot_groups": "each" | "all" | [[int, ...], ...],
                 "slot_group_labels": [str, ...],   names for listed groups
                 "weights": {"items": {id: num}} | {"slots": [num, ...]},
                 "min": num, "max": num,       every cell within the range
                 "even": "slots" | "items",    cells as equal as possible,
                                               compared along slot groups
                                               (within each item group) or
                                               along item groups
                 "max_gap": num}               hard even: largest gap allowed
    share       {"cases": [{"item": id, "with": [id, ...], "min": int,
                            "max": int}, ...]}
                Each case: the item shares a slot with min..max of `with`.
                Together = min 1 of [b]; apart = max 0 of [b].
    stretch     {"items": <selector>, "item_groups": "each" | {"column": c},
                 "sequences": [[[int, ...], ...], ...],
                 "of": "work" | "off", "min": int, "max": int,
                 "ignore_edges": bool}
                Each sequence is a list of time units in order, each unit a
                list of slots. A group works a unit if any of its items
                holds any of its slots. Every stretch of worked (of="work")
                or unworked (of="off") units is min..max long. A stretch
                touching either end of a sequence is never too short; with
                ignore_edges it is not checked at all (timetable gaps: the
                time before the first lesson is not a gap).
    transition  {"items": <selector>, "item_groups": "each" | {"column": c},
                 "pairs": [[int, int], ...]}
                No group holds both slots of any pair.

Soft rules carry "weight" in args.

Item selectors:

    {"kind": "all"}                                   every item
    {"kind": "column", "column": c}                   rows where flag column c is true
    {"kind": "column_value", "column": c, "value": v} rows where column c == v
    {"kind": "members", "members": [id, ...]}         an explicit list
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

ConstraintType = Literal["count", "share", "stretch", "transition"]
ConstraintSource = Literal["builtin_default", "chat", "manual"]

# Weight a soft rule gets when its args carry none.
DEFAULT_WEIGHT = {
    "count": 1.0,
    "share": 5.0,
    "stretch": 2.0,
    "transition": 2.0,
}


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
    """Return the ids (index values) of the items a selector picks."""
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


def item_groups(df: pd.DataFrame, args: dict) -> list[tuple[str, list]]:
    """(label, item ids) for each item group a rule compares or counts."""
    members = resolve_group_members(df, args.get("items", {"kind": "all"}))
    grouping = args.get("item_groups", "all")
    if grouping == "all":
        return [("", members)]
    if grouping == "each":
        return [(str(e), [e]) for e in members]
    if "column" in grouping:
        column = grouping["column"]
        values = df.loc[members, column]
        order = list(dict.fromkeys(v for v in values.tolist() if not pd.isna(v)))
        return [(f"{column} = {v}", values.index[values == v].tolist()) for v in order]
    if "columns" in grouping:
        chosen = set(members)
        return [(c, [e for e in resolve_group_members(df, {"kind": "column", "column": c}) if e in chosen])
                for c in grouping["columns"]]
    raise ValueError(f"unknown item grouping: {grouping!r}")


def slot_groups(args: dict, num_slots: int, names=None) -> list[tuple[str, list[int]]]:
    """(label, slot indexes) for each slot group a rule counts.

    `names` labels single slots ("mon-am"); slots are numbered from 1
    otherwise.
    """
    chosen = args.get("slots")
    chosen = list(range(num_slots)) if chosen is None else sorted({int(s) for s in chosen})
    grouping = args.get("slot_groups", "each")

    def name(s: int) -> str:
        return str(names[s]) if names else str(s + 1)

    if grouping == "each":
        return [(name(s), [s]) for s in chosen]
    if grouping == "all":
        return [("", chosen)]
    labels = args.get("slot_group_labels") or [str(i + 1) for i in range(len(grouping))]
    return [(label, sorted({int(s) for s in group})) for label, group in zip(labels, grouping)]


def rule_slot_indexes(args: dict) -> list[int]:
    """Every slot index a rule's args name, to check they exist."""
    named = list(args.get("slots") or ())
    groups = args.get("slot_groups")
    if isinstance(groups, list):
        named += [s for group in groups for s in group]
    named += [s for sequence in args.get("sequences") or () for unit in sequence for s in unit]
    named += [s for pair in args.get("pairs") or () for s in pair]
    return [int(s) for s in named]


def placement_weight(args: dict):
    """How much one placement of item e in slot s counts toward a count
    rule: 1, or the item's or slot's weight."""
    weights = args.get("weights")
    if not weights:
        return lambda e, s: 1
    if "items" in weights:
        by_item = weights["items"]
        return lambda e, s: by_item.get(e, 0)
    by_slot = weights["slots"]
    return lambda e, s: by_slot[s]
