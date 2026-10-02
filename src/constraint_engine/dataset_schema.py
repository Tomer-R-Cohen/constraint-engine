"""Turn a raw spreadsheet table into an entity table the solver can use.

Every column is addressed by its own header -- the engine knows no field by
name. What this module works out is what *kind* of thing each column holds
(yes/no flag, a handful of categories, numbers), because that decides which
rules can be written about it, and it normalizes those columns so rules mean
what they say.

What it deliberately does not do is guess meaning. It can tell that a column
holds yes/no values; what the column signifies is a question for the user.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

import pandas as pd

from constraint_engine import text

ColumnKind = Literal["flag", "category", "number"]

# Values that mean yes/no in the spreadsheets this engine sees. Deliberately
# generous: the usual 1/0, TRUE/FALSE and yes/no, tick marks, and the Hebrew
# forms used by the Shibutzit sample data.
_TRUE_TOKENS = {"1", "true", "yes", "y", "v", "✓", "+", "x", "כן", "א"}
_FALSE_TOKENS = {"0", "false", "no", "n", "-", "", "לא"}
_BOOLISH = _TRUE_TOKENS | _FALSE_TOKENS

# Above this many distinct values a text column is free text (names, notes,
# comments), not a category anyone can write a rule about.
MAX_CATEGORY_VALUES = 12

# Columns whose header looks like commentary rather than data. Matched
# loosely and only used to skip; a false negative just means one useless
# column shows up in the list.
_NOTE_HEADER = re.compile(r"comment|note|remark|הערה|הערות", re.IGNORECASE)


@dataclass
class ColumnInfo:
    """One spreadsheet column that rules can be written about."""

    name: str  # the header, which is also the column name in the entity table
    kind: ColumnKind
    values: list[str] = field(default_factory=list)  # category only
    true_count: int = 0  # flag only
    filled_count: int = 0  # non-empty cells, so sparse columns are visible


@dataclass
class DatasetSchema:
    columns: list[ColumnInfo] = field(default_factory=list)

    def get(self, name: str) -> Optional[ColumnInfo]:
        return next((c for c in self.columns if c.name == name), None)

    def names(self) -> list[str]:
        return [c.name for c in self.columns]

    def to_dicts(self) -> list[dict]:
        return [asdict(c) for c in self.columns]


def _norm(v: Any) -> str:
    return str(v).strip().lower()


def _is_blank(v: Any) -> bool:
    return v is None or (isinstance(v, float) and v != v) or str(v).strip().lower() in ("", "nan", "none", "nat")


def classify_series(s: pd.Series) -> tuple[Optional[ColumnKind], list[str], int]:
    """Work out what kind of column this is from its values alone.

    Returns (kind, distinct_values, true_count). kind is None for columns
    nothing useful can be done with: empty, constant, or free text with too
    many distinct values to constrain on.
    """
    non_blank = [v for v in s.tolist() if not _is_blank(v)]
    if not non_blank:
        return None, [], 0

    normed = [_norm(v) for v in non_blank]

    # Flag: every filled cell is a yes/no token, and the column actually
    # splits the rows. A column where nobody is flagged, or everybody is,
    # describes no subgroup.
    if set(normed) <= _BOOLISH:
        true_count = sum(1 for v in normed if v in _TRUE_TOKENS)
        if 0 < true_count < len(s):
            return "flag", [], true_count

    distinct = list(dict.fromkeys(str(v).strip() for v in non_blank))
    # One distinct value is a constant, not a variable.
    if len(distinct) < 2:
        return None, [], 0

    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_blank):
        return "number", [], 0

    if len(distinct) <= MAX_CATEGORY_VALUES:
        return "category", distinct, 0

    return None, [], 0


def describe_columns(raw_df: pd.DataFrame, skip: set[str] = frozenset()) -> DatasetSchema:
    """Describe every column rules can be written about.

    `skip` holds headers to leave out (typically the id column).
    """
    schema = DatasetSchema()
    for source in raw_df.columns:
        header = str(source).strip()
        if source in skip:
            continue
        # pandas names blank headers "Unnamed: 4"; those are layout, not data.
        if not header or header.startswith("Unnamed:") or _NOTE_HEADER.search(header):
            continue
        kind, values, true_count = classify_series(raw_df[source])
        if kind is None:
            continue
        filled = int(sum(1 for v in raw_df[source].tolist() if not _is_blank(v)))
        schema.columns.append(ColumnInfo(name=source, kind=kind, values=values, true_count=true_count, filled_count=filled))
    return schema


def _is_unique_integer_column(series: pd.Series) -> bool:
    """True if the non-null values of `series` are all-integer and unique."""
    non_null = series.dropna()
    if non_null.empty:
        return False
    as_numeric = pd.to_numeric(non_null, errors="coerce")
    if as_numeric.isna().any():
        return False
    if not (as_numeric == as_numeric.round()).all():
        return False
    return as_numeric.is_unique


def guess_id_column(raw_df: pd.DataFrame) -> Optional[str]:
    """A best-effort guess at the column that identifies each row.

    Prefers a blank-header column (pandas "Unnamed: N", often a row-number
    column) holding unique integers, then the first column of unique
    integers. None when nothing qualifies; rows are then numbered 1..n.
    """
    columns = list(raw_df.columns)
    unnamed = [c for c in columns if isinstance(c, str) and c.startswith("Unnamed: ")]
    for c in unnamed + columns:
        if _is_unique_integer_column(raw_df[c]):
            return c
    return None


def prepare_entities(raw_df: pd.DataFrame, schema: DatasetSchema, id_column: Optional[str] = None) -> pd.DataFrame:
    """The entity table: one row per entity, indexed by its id.

    Flag columns are normalized to real booleans so a group selector means
    what it says -- a column of "yes"/"" strings would otherwise read as
    all-true, since any non-empty string is truthy in Python. That bug
    would silently put every entity in the group. Numbers become numeric and
    categories trimmed strings; other columns are kept as they are.
    """
    out = raw_df.copy()
    for col in schema.columns:
        series = raw_df[col.name]
        if col.kind == "flag":
            out[col.name] = [(not _is_blank(v)) and _norm(v) in _TRUE_TOKENS for v in series.tolist()]
        elif col.kind == "number":
            out[col.name] = pd.to_numeric(series, errors="coerce")
        else:
            out[col.name] = ["" if _is_blank(v) else str(v).strip() for v in series.tolist()]

    if id_column is None:
        out.index = pd.RangeIndex(1, len(out) + 1)
    else:
        ids = raw_df[id_column]
        if ids.isna().any() or not ids.is_unique:
            raise ValueError(text.ID_COLUMN_NOT_UNIQUE.format(column=id_column))
        if _is_unique_integer_column(ids):
            ids = pd.to_numeric(ids).astype(int)
        out.index = pd.Index(ids.tolist())
    out.index.name = None
    return out
