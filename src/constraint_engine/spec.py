"""The problem spec: one versioned JSON document describing a whole problem.

A spec names the slots (with attributes such as day and shift), says how
the entity table is identified, lists the rules, and carries the solve
settings. It holds no data: the entity rows come from the loaded
spreadsheet, and `compiler.py` checks the spec against them.

Rules are typed: four building blocks (count, share, stretch, transition),
each its own model with its own fields, so an agent fills a fixed form
instead of writing anything free-form, and a wrong field is rejected when
the rule is added, not discovered at solve time.

Selectors:

    EntitySelector  {}                               every entity
                    {"column": c}                    entities whose flag column c is true
                    {"column": c, "value": v}        entities whose column c equals v
                    {"members": [id, ...]}           exactly these entities
    SlotSelector    {}                               every slot
                    {"ids": [id, ...]}               exactly these slots
                    {"where": {attr: v | [v, ...]}}  slots whose attributes match
                                                     (a list means any of)

Priorities are ordinal levels, not weights: a soft rule is a "low",
"medium" or "high" preference, and code turns that into a weight.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from constraint_engine import text

SPEC_VERSION = 1

Scalar = Union[str, int, float, bool]
EntityRef = Union[str, int]
Priority = Literal["low", "medium", "high"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)


class EntitySelector(_Model):
    column: Optional[str] = None
    value: Optional[Scalar] = None
    members: Optional[list[EntityRef]] = None

    @model_validator(mode="after")
    def _one_kind(self):
        if self.members is not None and (self.column is not None or self.value is not None):
            raise ValueError(text.SPEC_SELECTOR_MEMBERS_OR_COLUMN)
        if self.value is not None and self.column is None:
            raise ValueError(text.SPEC_VALUE_NEEDS_COLUMN)
        return self


class SlotSelector(_Model):
    ids: Optional[list[str]] = None
    where: Optional[dict[str, Union[Scalar, list[Scalar]]]] = None

    @model_validator(mode="after")
    def _one_kind(self):
        if self.ids is not None and self.where is not None:
            raise ValueError(text.SPEC_SLOTS_IDS_OR_WHERE)
        return self


class Slot(_Model):
    id: str
    attributes: dict[str, Scalar] = Field(default_factory=dict)


class Vocabulary(_Model):
    """The nouns read-backs use, so a roster reads "employee"/"shift" and a
    placement "student"/"class"."""

    entity: str = "entity"
    entities: str = "entities"
    slot: str = "slot"
    slots: str = "slots"


class EntitiesSource(_Model):
    # Where the rows come from, for the record (e.g. "staff.xlsx#Sheet1").
    source: Optional[str] = None
    # Column whose values identify each row; rows are numbered 1..n if None.
    id_column: Optional[str] = None


class Settings(_Model):
    slots_per_entity: tuple[int, int] = (1, 1)
    # None: interchangeable exactly when each entity holds one slot.
    slots_interchangeable: Optional[bool] = None
    seed: int = 42
    time_limit_seconds: float = 30.0

    @model_validator(mode="after")
    def _band(self):
        lo, hi = self.slots_per_entity
        if not 0 <= lo <= hi:
            raise ValueError(text.SPEC_BAD_SLOTS_PER_ENTITY)
        return self


# ---- rules ----

class _RuleBase(_Model):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    mode: Literal["hard", "soft"] = "hard"
    # Soft rules only; defaults to "medium".
    priority: Optional[Priority] = None
    active: bool = True

    @model_validator(mode="after")
    def _priority_is_for_soft_rules(self):
        if self.mode == "hard" and self.priority is not None:
            raise ValueError(text.SPEC_PRIORITY_ON_HARD_RULE)
        return self

    @property
    def level(self) -> Priority:
        return self.priority or "medium"


class _Band(_Model):
    min: Optional[int] = Field(default=None, ge=0)
    max: Optional[int] = Field(default=None, ge=0)

    def _check_band(self, required: bool = True):
        if required and self.min is None and self.max is None:
            raise ValueError(text.SPEC_BAND_EMPTY)
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(text.SPEC_BAND_REVERSED)


class PerColumn(_Model):
    """Group items by a column: one group per value of `column`, or one
    group per flag column in `flag_columns`."""

    column: Optional[str] = None
    flag_columns: Optional[list[str]] = None

    @model_validator(mode="after")
    def _one_kind(self):
        if (self.column is None) == (self.flag_columns is None):
            raise ValueError(text.SPEC_PER_COLUMN_ONE_KIND)
        return self


class PerAttribute(_Model):
    """Group slots by an attribute: one group per value (e.g. per day)."""

    attribute: str


class SumOf(_Model):
    """Add up a number instead of counting: an item column (hours someone
    can give, a student's size) or a slot attribute (a shift's hours)."""

    item_column: Optional[str] = None
    slot_attribute: Optional[str] = None

    @model_validator(mode="after")
    def _one_kind(self):
        if (self.item_column is None) == (self.slot_attribute is None):
            raise ValueError(text.SPEC_SUM_ONE_KIND)
        return self


class CountRule(_RuleBase):
    """Count placements of the selected items in the selected slots (or add
    up `sum`), per group, and keep every group's count within min..max, or
    keep the groups `even` (compared along slot groups or along item
    groups, at most `max_gap` apart when mandatory).

    per_item: "all" (one group), "each" (every item on its own), or a
    PerColumn. per_slot: "all", "each" (every slot on its own), or a
    PerAttribute. Examples: per_item "all" + per_slot "each" = how many per
    slot; per_item "each" + per_slot "all" = how many slots per item;
    per_item "each" + per_slot {"attribute": "day"} = per item per day."""

    type: Literal["count"]
    items: EntitySelector = Field(default_factory=EntitySelector)
    slots: SlotSelector = Field(default_factory=SlotSelector)
    per_item: Union[Literal["all", "each"], PerColumn]
    per_slot: Union[Literal["all", "each"], PerAttribute]
    sum: Optional[SumOf] = None
    min: Optional[float] = Field(default=None, ge=0)
    max: Optional[float] = Field(default=None, ge=0)
    even: Optional[Literal["slots", "items"]] = None
    max_gap: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _target(self):
        if self.min is None and self.max is None and self.even is None:
            raise ValueError(text.SPEC_COUNT_NEEDS_TARGET)
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(text.SPEC_BAND_REVERSED)
        if self.max_gap is not None and self.even is None:
            raise ValueError(text.SPEC_GAP_NEEDS_EVEN)
        return self


class ShareRule(_RuleBase, _Band):
    """An item shares a slot with min..max of the listed items: together is
    min 1 of [b], apart is max 0 of [b]. Either one `item` with a `with`
    list, or every selected item with the items named in its
    `with_column` (comma-separated ids, e.g. friend requests)."""

    type: Literal["share"]
    item: Optional[EntityRef] = None
    with_: Optional[list[EntityRef]] = Field(default=None, alias="with")
    items: Optional[EntitySelector] = None
    with_column: Optional[str] = None

    @model_validator(mode="after")
    def _one_form(self):
        self._check_band()
        single = self.item is not None or self.with_ is not None
        by_column = self.with_column is not None
        if single == by_column or (single and (self.item is None or self.with_ is None or self.items is not None)):
            raise ValueError(text.SPEC_SHARE_ONE_FORM)
        return self


class StretchRule(_RuleBase, _Band):
    """Stretch lengths over time. `per` is the slot attribute that makes the
    time units (e.g. "day"), ordered as they first appear in the slot list;
    with `within_each`, the units restart for each value of that attribute
    (periods within each day). An item -- or a group of items, with
    per_item -- works a unit if it holds any selected slot in it. Every
    stretch of worked (of="work") or unworked (of="off") units is min..max
    long. A stretch at either end is never too short; with ignore_edges it
    is not checked at all (a gap is only a gap between two lessons)."""

    type: Literal["stretch"]
    items: EntitySelector = Field(default_factory=EntitySelector)
    per_item: Union[Literal["each"], PerColumn] = "each"
    slots: SlotSelector = Field(default_factory=SlotSelector)
    per: str
    within_each: Optional[str] = None
    of: Literal["work", "off"] = "work"
    ignore_edges: bool = False

    @model_validator(mode="after")
    def _band_given(self):
        self._check_band()
        return self


class TransitionRule(_RuleBase):
    """Rest between slots: an item (or group, with per_item) holding a slot
    matched by `after` holds no slot matched by `not_followed_by` in the
    next `next` time units (units made by the slot attribute `per`)."""

    type: Literal["transition"]
    items: EntitySelector = Field(default_factory=EntitySelector)
    per_item: Union[Literal["each"], PerColumn] = "each"
    after: SlotSelector
    not_followed_by: SlotSelector
    per: str
    next: int = Field(default=1, ge=1)


Rule = Annotated[
    Union[CountRule, ShareRule, StretchRule, TransitionRule],
    Field(discriminator="type"),
]


class ProblemSpec(_Model):
    spec_version: Literal[1] = SPEC_VERSION
    name: str = ""
    vocabulary: Vocabulary = Field(default_factory=Vocabulary)
    entities: EntitiesSource = Field(default_factory=EntitiesSource)
    slots: list[Slot] = Field(min_length=1)
    settings: Settings = Field(default_factory=Settings)
    rules: list[Rule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self):
        for kind, ids in (("slot", [s.id for s in self.slots]), ("rule", [r.id for r in self.rules])):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            if duplicates:
                raise ValueError(text.SPEC_DUPLICATE_IDS.format(kind=kind, ids=duplicates))
        return self

    def rule(self, rule_id: str):
        return next((r for r in self.rules if r.id == rule_id), None)


# ---- persistence and fingerprints ----

def load_spec(document: Union[str, dict]) -> ProblemSpec:
    """Parse a spec from JSON text or an already-parsed dict."""
    if isinstance(document, str):
        return ProblemSpec.model_validate_json(document)
    return ProblemSpec.model_validate(document)


def dump_spec(spec: ProblemSpec) -> str:
    return spec.model_dump_json(indent=2)


def _digest(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def spec_hash(spec: ProblemSpec) -> str:
    """Stable fingerprint of everything that decides the answer."""
    return _digest(spec.model_dump(mode="json"))


def data_hash(df) -> str:
    """Stable fingerprint of the entity table (ids, columns and values)."""
    return _digest({
        "index": [repr(v) for v in df.index],
        "columns": [str(c) for c in df.columns],
        "values": [[repr(v) for v in row] for row in df.itertuples(index=False)],
    })
