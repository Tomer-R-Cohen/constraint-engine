"""Plain-English read-backs of spec rules, built by code from templates.

The user confirms what will be enforced by reading these, so they come from
the rule's typed fields and the templates in text.py -- never from LLM
prose. The same rule always reads the same way.
"""

from __future__ import annotations

from typing import Optional

from constraint_engine import text
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
)


def _sentence(s: str) -> str:
    return s[:1].upper() + s[1:]


def _value(v) -> str:
    if isinstance(v, bool):
        return text.YES if v else text.NO
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _join(items, word: str = text.AND) -> str:
    items = [_value(i) for i in items]
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {word} {items[-1]}"


def _plural(noun: str) -> str:
    return noun if noun.endswith("s") else noun + "s"


def band(lo, hi) -> tuple[str, bool]:
    """The band in words, and whether the noun after it is singular."""
    if not lo and hi == 0:
        return text.BAND_NONE, False
    if lo is not None and lo == hi:
        return text.BAND_EXACTLY.format(n=_value(lo)), lo == 1
    if lo and hi is not None:
        return text.BAND_BETWEEN.format(lo=_value(lo), hi=_value(hi)), False
    if hi is not None:
        return text.BAND_AT_MOST.format(n=_value(hi)), hi == 1
    return text.BAND_AT_LEAST.format(n=_value(lo)), lo == 1


def _entity_filter(selector: Optional[EntitySelector]) -> str:
    if selector is None:
        return ""
    if selector.members is not None:
        return text.FILTER_MEMBERS.format(members=_join(selector.members))
    if selector.column is not None and selector.value is not None:
        return text.FILTER_VALUE.format(column=selector.column, value=_value(selector.value))
    if selector.column is not None:
        return text.FILTER_FLAG.format(column=selector.column)
    return ""


def _slot_filter(selector: SlotSelector) -> str:
    if selector.ids is not None:
        return text.SLOT_FILTER_IDS.format(ids=_join(selector.ids))
    if selector.where:
        conditions = [
            text.SLOT_CONDITION.format(attribute=attribute,
                                       values=_join(values if isinstance(values, list) else [values], text.OR))
            for attribute, values in selector.where.items()
        ]
        return text.SLOT_FILTER_WHERE.format(conditions=_join(conditions))
    return ""


def _slot_subject(selector: SlotSelector, spec: ProblemSpec) -> str:
    v = spec.vocabulary
    if selector.ids is not None and len(selector.ids) == 1:
        return text.SUBJECT_ONE_SLOT.format(slot=v.slot, id=selector.ids[0])
    if selector.ids is not None:
        return text.SUBJECT_EACH_OF_SLOTS.format(slots=v.slots, ids=_join(selector.ids))
    return text.SUBJECT_EVERY_SLOT.format(slot=v.slot, filter=_slot_filter(selector))


def _single_member(selector: Optional[EntitySelector]):
    if selector is not None and selector.members is not None and len(selector.members) == 1:
        return selector.members[0]
    return None


def _item_subject(selector: EntitySelector, per_item, spec: ProblemSpec) -> str:
    """Who a per-item phrase is about: one item, each item, or each group."""
    if isinstance(per_item, PerColumn):
        if per_item.column is not None:
            return text.SUBJECT_EACH_COLUMN.format(column=per_item.column)
        return text.SUBJECT_EACH_OF_COLUMNS.format(columns=_join(per_item.flag_columns))
    member = _single_member(selector)
    if member is not None:
        return _value(member)
    return text.SUBJECT_EACH_ENTITY.format(entity=spec.vocabulary.entity, filter=_entity_filter(selector))


def _status(rule) -> str:
    if not rule.active:
        return text.RB_INACTIVE
    if rule.mode == "hard":
        return text.RB_HARD
    return text.RB_SOFT.format(level=text.PRIORITY_NAMES[rule.level])


def _single_slot(spec: ProblemSpec) -> bool:
    return tuple(spec.settings.slots_per_entity) == (1, 1)


# ---- count ----

def _fixed(rule: CountRule, spec: ProblemSpec) -> Optional[str]:
    """"Ana has shift mon-am" / "Ana never has shift mon-am"."""
    member = _single_member(rule.items)
    if (member is None or rule.slots.ids is None or len(rule.slots.ids) != 1 or rule.sum is not None
            or rule.even is not None or rule.per_item != "each"):
        return None
    one = _single_slot(spec)
    args = {"entity": _value(member), "slot": spec.vocabulary.slot, "id": rule.slots.ids[0]}
    if rule.min == 1 and rule.max in (None, 1):
        return (text.RB_FIXED_ONE if one else text.RB_FIXED_MANY).format(**args)
    if not rule.min and rule.max == 0:
        return (text.RB_NEVER_ONE if one else text.RB_NEVER_MANY).format(**args)
    return None


def _count_band(rule: CountRule, spec: ProblemSpec) -> str:
    v = spec.vocabulary
    words, singular = band(rule.min, rule.max)
    slot_filter, item_filter = _slot_filter(rule.slots), _entity_filter(rule.items)
    slot_filter_used = item_filter_used = False
    if rule.sum is not None:
        noun = rule.sum.item_column or rule.sum.slot_attribute
    elif rule.per_item == "each":
        noun = (v.slot if singular else v.slots) + slot_filter
        slot_filter_used = True
    else:
        noun = (v.entity if singular else v.entities) + item_filter
        item_filter_used = True

    subject = None
    if rule.per_item != "all":
        subject = _item_subject(rule.items, rule.per_item, spec)
        item_filter_used = item_filter_used or rule.per_item == "each"
    tail, scope = "", ""
    if rule.per_slot == "each":
        if subject is None:
            subject = _slot_subject(rule.slots, spec)
        else:
            scope = text.SCOPE_EVERY_SLOT.format(slot=v.slot, filter="" if slot_filter_used else slot_filter)
        slot_filter_used = True
    elif isinstance(rule.per_slot, PerAttribute):
        if subject is None:
            subject = text.SUBJECT_EVERY_GROUP.format(attribute=rule.per_slot.attribute)
        else:
            tail += text.PER.format(attribute=rule.per_slot.attribute)
    if slot_filter and not slot_filter_used:
        tail += text.ACROSS.format(slots=v.slots, filter=slot_filter)
    if item_filter and not item_filter_used:
        tail += text.COUNTING_ITEMS.format(entities=v.entities, filter=item_filter)

    if subject is None:
        return text.RB_COUNT_TOTAL.format(band=words, noun=noun, tail=tail)
    if scope:
        return text.RB_COUNT_SCOPED.format(scope=scope, subject=subject, band=words, noun=noun, tail=tail)
    return text.RB_COUNT_HAS.format(subject=subject, band=words, noun=noun, tail=tail)


def _count_even(rule: CountRule, spec: ProblemSpec) -> str:
    v = spec.vocabulary
    slot_filter, item_filter = _slot_filter(rule.slots), _entity_filter(rule.items)
    gap = text.GAP.format(gap=_value(rule.max_gap)) if rule.max_gap is not None else ""
    measured = rule.sum.item_column or rule.sum.slot_attribute if rule.sum is not None else None
    if rule.even == "slots":
        if isinstance(rule.per_slot, PerAttribute):
            across = text.EVEN_ACROSS_GROUPS.format(units=_plural(rule.per_slot.attribute))
        else:
            across = text.EVEN_ACROSS_SLOTS.format(slots=v.slots, filter=slot_filter)
        if rule.per_item == "each":
            what = text.EVEN_ITEMS_SLOTS.format(entity=v.entity, filter=item_filter, slots=measured or v.slots)
        elif rule.per_item == "all":
            what = measured or (v.entities + item_filter)
        elif rule.per_item.column is not None:
            what = text.EVEN_OF_EACH.format(what=measured or v.entities, column=rule.per_item.column)
        else:
            what = _item_subject(rule.items, rule.per_item, spec)
        return text.RB_EVEN_SPREAD.format(what=what, across=across, gap=gap)
    who = (v.entities + item_filter) if rule.per_item == "all" else _item_subject(rule.items, rule.per_item, spec)
    amount = (text.AMOUNT_SUM.format(noun=measured) if measured
              else text.AMOUNT_NUMBER.format(noun=v.slots + slot_filter))
    if rule.per_slot == "each":
        scope = text.IN_EVERY_SLOT.format(slot=v.slot)
    elif isinstance(rule.per_slot, PerAttribute):
        scope = text.PER.format(attribute=rule.per_slot.attribute)
    else:
        scope = ""
    return text.RB_EVEN_SIMILAR.format(who=who, amount=amount, scope=scope, gap=gap)


def _count(rule: CountRule, spec: ProblemSpec) -> str:
    fixed = _fixed(rule, spec)
    if fixed:
        return fixed
    parts = []
    if rule.even is not None:
        parts.append(_sentence(_count_even(rule, spec)))
    if rule.min is not None or rule.max is not None:
        parts.append(_sentence(_count_band(rule, spec)))
    return " ".join(parts)


# ---- share / stretch / transition ----

def _share(rule: ShareRule, spec: ProblemSpec) -> str:
    v = spec.vocabulary
    one = _single_slot(spec)
    words, _ = band(rule.min, rule.max)
    if rule.with_column is not None:
        template = text.RB_SHARE_COLUMN_ONE if one else text.RB_SHARE_COLUMN_MANY
        subject = text.SUBJECT_EACH_ENTITY.format(entity=v.entity, filter=_entity_filter(rule.items))
        return template.format(subject=subject, slot=v.slot, band=words, entities=v.entities, column=rule.with_column)
    others = rule.with_
    if len(others) == 1 and (rule.min or 0) >= 1 and rule.max is None:
        template = text.RB_SHARE_TOGETHER_ONE if one else text.RB_SHARE_TOGETHER_MANY
        return template.format(a=_value(rule.item), b=_value(others[0]), slot=v.slot)
    if len(others) == 1 and not rule.min and rule.max == 0:
        template = text.RB_SHARE_APART_ONE if one else text.RB_SHARE_APART_MANY
        return template.format(a=_value(rule.item), b=_value(others[0]), slot=v.slot)
    template = text.RB_SHARE_LIST_ONE if one else text.RB_SHARE_LIST_MANY
    return template.format(entity=_value(rule.item), slot=v.slot, band=words, others=_join(others))


def _stretch(rule: StretchRule, spec: ProblemSpec) -> str:
    v = spec.vocabulary
    words, one = band(rule.min, rule.max)
    slot_filter = _slot_filter(rule.slots)
    counting = text.STRETCH_COUNTING.format(slots=v.slots, filter=slot_filter) if slot_filter else ""
    if rule.ignore_edges:
        edge = text.STRETCH_IGNORE_EDGES
    else:
        edge = text.STRETCH_EDGE if rule.min else ""
    within = text.STRETCH_WITHIN.format(attribute=rule.within_each) if rule.within_each else ""
    template = text.RB_STRETCH_WORK if rule.of == "work" else text.RB_STRETCH_OFF
    return template.format(subject=_item_subject(rule.items, rule.per_item, spec), band=words,
                           unit=rule.per if one else _plural(rule.per), units=_plural(rule.per),
                           within=within, counting=counting, edge=edge)


def _transition(rule: TransitionRule, spec: ProblemSpec) -> str:
    window = (text.WINDOW_NEXT.format(unit=rule.per) if rule.next == 1
              else text.WINDOW_NEXT_N.format(n=rule.next, units=_plural(rule.per)))
    return text.RB_TRANSITION.format(subject=_item_subject(rule.items, rule.per_item, spec),
                                     slot=spec.vocabulary.slot, after=_slot_filter(rule.after),
                                     forbid=_slot_filter(rule.not_followed_by), window=window)


def describe_rule(rule, spec: ProblemSpec) -> str:
    """One rule in plain English, ending with whether it is mandatory."""
    if isinstance(rule, CountRule):
        body = _count(rule, spec)
    elif isinstance(rule, ShareRule):
        body = _share(rule, spec)
    elif isinstance(rule, StretchRule):
        body = _stretch(rule, spec)
    elif isinstance(rule, TransitionRule):
        body = _transition(rule, spec)
    else:  # pragma: no cover - the spec's union is closed
        raise TypeError(f"no read-back for {type(rule).__name__}")
    return f"{_sentence(body)} {_status(rule)}"


def describe_settings(spec: ProblemSpec) -> str:
    v = spec.vocabulary
    lo, hi = spec.settings.slots_per_entity
    words, one = band(lo, hi)
    return _sentence(text.RB_SLOTS_PER_ENTITY.format(entity=v.entity, band=words, what=v.slot if one else v.slots))


def describe_spec(spec: ProblemSpec) -> list[str]:
    """The settings line, then one line per rule, in spec order."""
    return [describe_settings(spec)] + [describe_rule(rule, spec) for rule in spec.rules]
