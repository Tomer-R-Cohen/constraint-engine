"""Shortcuts for building engine rules in Python.

Each returns an ordinary `Constraint` of one of the four building blocks;
they exist so code and tests read like the rule they mean. The spec
(spec.py) is the way rules arrive from users; these are for code.
"""

from __future__ import annotations

from typing import Optional

from constraint_engine.constraints import Constraint

ALL = {"kind": "all"}


def flag(column: str) -> dict:
    """Items whose yes/no column is yes."""
    return {"kind": "column", "column": column}


def value(column: str, v) -> dict:
    """Items whose column equals v."""
    return {"kind": "column_value", "column": column, "value": v}


def members(*ids) -> dict:
    return {"kind": "members", "members": list(ids)}


def _rule(type_: str, label: str, hard: bool, weight: Optional[float], args: dict) -> Constraint:
    if weight is not None:
        args["weight"] = weight
    return Constraint(type=type_, hard=hard, label=label or type_, args=args)


def count(label: str = "", *, items: dict = ALL, item_groups="all", slots=None, slot_groups="each",
          min=None, max=None, even=None, max_gap=None, weights=None, hard: bool = True,
          weight: Optional[float] = None, **extra) -> Constraint:
    args = {"items": items, "item_groups": item_groups, "slot_groups": slot_groups, **extra}
    for key, v in (("slots", slots), ("min", min), ("max", max), ("even", even), ("max_gap", max_gap),
                   ("weights", weights)):
        if v is not None:
            args[key] = v
    return _rule("count", label, hard, weight, args)


def per_slot(label: str = "", **kwargs) -> Constraint:
    """How many of the items each slot gets ("2-3 per class")."""
    return count(label, item_groups="all", slot_groups="each", **kwargs)


def per_item(label: str = "", **kwargs) -> Constraint:
    """How many slots each item gets ("3-6 shifts each"); pass slot_groups
    to count per group of slots ("at most 1 per day")."""
    kwargs.setdefault("slot_groups", "all")
    return count(label, item_groups="each", **kwargs)


def spread(label: str = "", *, item_groups="all", **kwargs) -> Constraint:
    """Spread each item group as evenly as possible over the slots."""
    kwargs.setdefault("hard", False)
    return count(label, item_groups=item_groups, slot_groups="each", even="slots", **kwargs)


def fixed(item, slot: int, label: str = "", **kwargs) -> Constraint:
    """The item holds this slot."""
    return count(label or f"{item} in {slot}", items=members(item), item_groups="each", slots=[slot],
                 slot_groups="all", min=1, **kwargs)


def share(item, others: list, label: str = "", *, min=None, max=None, hard: bool = True,
          weight: Optional[float] = None) -> Constraint:
    return _rule("share", label, hard, weight, {"cases": [{"item": item, "with": list(others), "min": min, "max": max}]})


def together(a, b, label: str = "", **kwargs) -> Constraint:
    return share(a, [b], label or f"{a} with {b}", min=1, **kwargs)


def apart(a, b, label: str = "", **kwargs) -> Constraint:
    return share(a, [b], label or f"{a} apart from {b}", max=0, **kwargs)


def with_one_of(item, others: list, label: str = "", **kwargs) -> Constraint:
    return share(item, others, label or f"{item} with one of {others}", min=1, **kwargs)


def stretch(sequences: list, label: str = "", *, items: dict = ALL, item_groups="each", of: str = "work",
            min=None, max=None, ignore_edges: bool = False, hard: bool = True,
            weight: Optional[float] = None) -> Constraint:
    return _rule("stretch", label, hard, weight, {"items": items, "item_groups": item_groups, "sequences": sequences,
                                                   "of": of, "min": min, "max": max, "ignore_edges": ignore_edges})


def transition(pairs: list, label: str = "", *, items: dict = ALL, item_groups="each", hard: bool = True,
               weight: Optional[float] = None) -> Constraint:
    return _rule("transition", label, hard, weight, {"items": items, "item_groups": item_groups,
                                                      "pairs": [list(p) for p in pairs]})
