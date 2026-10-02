"""Plain-English read-backs of spec rules, built by code from templates.

The user confirms what will be enforced by reading these, so they come from
the rule's typed fields and the templates in text.py -- never from LLM
prose. The same rule always reads the same way.
"""

from __future__ import annotations

from typing import Optional

from constraint_engine import text
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
)


def _sentence(s: str) -> str:
    return s[:1].upper() + s[1:]


def _value(v) -> str:
    if isinstance(v, bool):
        return text.YES if v else text.NO
    return str(v)


def _join(items, word: str = text.AND) -> str:
    items = [_value(i) for i in items]
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {word} {items[-1]}"


def band(lo: Optional[int], hi: Optional[int]) -> tuple[str, bool]:
    """The band in words, and whether the noun after it is singular."""
    if not lo and hi == 0:
        return text.BAND_NONE, False
    if lo is not None and lo == hi:
        return text.BAND_EXACTLY.format(n=lo), lo == 1
    if lo and hi is not None:
        return text.BAND_BETWEEN.format(lo=lo, hi=hi), False
    if hi is not None:
        return text.BAND_AT_MOST.format(n=hi), hi == 1
    return text.BAND_AT_LEAST.format(n=lo), lo == 1


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


def _entity_subject(selector: EntitySelector, spec: ProblemSpec) -> str:
    if selector.members is not None and len(selector.members) == 1:
        return _value(selector.members[0])
    return text.SUBJECT_EACH_ENTITY.format(entity=spec.vocabulary.entity, filter=_entity_filter(selector))


def _status(rule) -> str:
    if not rule.active:
        return text.RB_INACTIVE
    if rule.mode == "hard":
        return text.RB_HARD
    return text.RB_SOFT.format(level=text.PRIORITY_NAMES[rule.level])


def describe_rule(rule, spec: ProblemSpec, request_count: Optional[int] = None) -> str:
    """One rule in plain English, ending with whether it is mandatory."""
    v = spec.vocabulary
    single = tuple(spec.settings.slots_per_entity) == (1, 1)
    if isinstance(rule, CapacityRule):
        words, one = band(rule.min, rule.max)
        who = (v.entity if one else v.entities) + _entity_filter(rule.entities)
        body = text.RB_CAPACITY.format(subject=_slot_subject(rule.slots, spec), band=words, who=who)
    elif isinstance(rule, LoadRule):
        words, one = band(rule.min, rule.max)
        what = (v.slot if one else v.slots) + _slot_filter(rule.slots)
        per = text.PER.format(attribute=rule.per) if rule.per else ""
        body = text.RB_LOAD.format(subject=_entity_subject(rule.entities, spec), band=words, what=what, per=per)
    elif isinstance(rule, BalanceRule):
        if rule.by_column is not None:
            body = text.RB_BALANCE_BY_COLUMN.format(entities=v.entities, slots=v.slots, column=rule.by_column)
        elif rule.flag_columns is not None:
            body = text.RB_BALANCE_FLAGS.format(entities=v.entities, slots=v.slots, columns=_join(rule.flag_columns))
        else:
            body = text.RB_BALANCE_GROUP.format(who=v.entities + _entity_filter(rule.entities), slots=v.slots)
    elif isinstance(rule, TogetherRule):
        template = text.RB_TOGETHER_ONE if single else text.RB_TOGETHER_MANY
        body = template.format(a=_value(rule.entity_a), b=_value(rule.entity_b), slot=v.slot)
    elif isinstance(rule, SeparateRule):
        template = text.RB_SEPARATE_ONE if single else text.RB_SEPARATE_MANY
        body = template.format(a=_value(rule.entity_a), b=_value(rule.entity_b), slot=v.slot)
    elif isinstance(rule, AtLeastOneOfRule):
        template = text.RB_AT_LEAST_ONE_ONE if single else text.RB_AT_LEAST_ONE_MANY
        body = template.format(entity=_value(rule.entity), slot=v.slot, candidates=_join(rule.candidates, text.OR))
    elif isinstance(rule, FixedRule):
        template = text.RB_FIXED_ONE if single else text.RB_FIXED_MANY
        body = template.format(entity=_value(rule.entity), slot=v.slot, id=rule.slot)
    elif isinstance(rule, PartnerRequestsRule):
        count = request_count if request_count is not None else sum(1 for asked in rule.requests.values() if asked)
        body = text.RB_PARTNERS.format(entity=v.entity, entities=v.entities, count=count)
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
