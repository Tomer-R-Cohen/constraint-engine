"""The problem spec: one versioned JSON document describing a whole problem.

A spec names the slots (with attributes such as day and shift), says how
the entity table is identified, lists the rules, and carries the solve
settings. It holds no data: the entity rows come from the loaded
spreadsheet, and `compiler.py` checks the spec against them.

Rules are typed: each rule type is its own model with its own fields, so an
agent fills a fixed form instead of writing anything free-form, and a wrong
field is rejected when the rule is added, not discovered at solve time.

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
    model_config = ConfigDict(extra="forbid")


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

    @model_validator(mode="after")
    def _band(self):
        if self.min is None and self.max is None:
            raise ValueError(text.SPEC_BAND_EMPTY)
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(text.SPEC_BAND_REVERSED)
        return self


class CapacityRule(_RuleBase, _Band):
    """In each selected slot, how many of the selected entities."""

    type: Literal["capacity"]
    entities: EntitySelector = Field(default_factory=EntitySelector)
    slots: SlotSelector = Field(default_factory=SlotSelector)


class LoadRule(_RuleBase, _Band):
    """For each selected entity, how many of the selected slots it holds --
    counted separately for each value of the slot attribute `per`, if given
    ("at most 1 shift per day")."""

    type: Literal["load"]
    entities: EntitySelector = Field(default_factory=EntitySelector)
    slots: SlotSelector = Field(default_factory=SlotSelector)
    per: Optional[str] = None


class BalanceRule(_RuleBase):
    """Spread entities evenly over the slots. Exactly one of: `entities`
    (one group), `by_column` (each value of a category column, as one rule),
    `flag_columns` (each flag column, as one rule)."""

    type: Literal["balance"]
    entities: Optional[EntitySelector] = None
    by_column: Optional[str] = None
    flag_columns: Optional[list[str]] = None

    @model_validator(mode="after")
    def _one_target(self):
        given = [v for v in (self.entities, self.by_column, self.flag_columns) if v is not None]
        if len(given) != 1:
            raise ValueError(text.SPEC_BALANCE_ONE_TARGET)
        return self


class TogetherRule(_RuleBase):
    """The two entities share a slot."""

    type: Literal["together"]
    entity_a: EntityRef
    entity_b: EntityRef


class SeparateRule(_RuleBase):
    """The two entities never share a slot."""

    type: Literal["separate"]
    entity_a: EntityRef
    entity_b: EntityRef


class AtLeastOneOfRule(_RuleBase):
    """The entity shares a slot with at least one of the candidates."""

    type: Literal["at_least_one_of"]
    entity: EntityRef
    candidates: list[EntityRef] = Field(min_length=1)


class FixedRule(_RuleBase):
    """The entity holds this slot (and possibly others)."""

    type: Literal["fixed"]
    entity: EntityRef
    slot: str


class PartnerRequestsRule(_RuleBase):
    """Soft goal: each requester shares a slot with a mutual request and
    with at least two of the entities it asked for."""

    type: Literal["partner_requests"]
    mode: Literal["soft"] = "soft"
    requests: dict[str, list[EntityRef]]


Rule = Annotated[
    Union[CapacityRule, LoadRule, BalanceRule, TogetherRule, SeparateRule, AtLeastOneOfRule, FixedRule,
          PartnerRequestsRule],
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
