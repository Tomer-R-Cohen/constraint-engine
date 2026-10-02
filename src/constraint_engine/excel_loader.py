"""Excel workbook loading utilities.

Loads a sheet into a raw (unmapped) DataFrame without ever writing to the
file on disk.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pandas as pd

from constraint_engine import text


class ExcelLoadError(Exception):
    """Raised when a workbook cannot be loaded or parsed as expected."""


@dataclass
class LoadedWorkbook:
    """Container for a loaded workbook's data and metadata."""

    path: str
    sheet_names: list[str]
    active_sheet: str
    raw_df: pd.DataFrame
    header_row_1indexed: int
    first_data_row_1indexed: int
    last_data_row_1indexed: int | None = None
    index_column: str | None = None
    notes: list[str] = field(default_factory=list)


def list_sheets(path: str) -> list[str]:
    """Return the list of sheet names in an Excel workbook.

    Raises:
        ExcelLoadError: if the file cannot be opened.
    """
    if not os.path.exists(path):
        raise ExcelLoadError(text.FILE_NOT_FOUND.format(path=path))
    try:
        with pd.ExcelFile(path, engine="openpyxl") as xls:
            return list(xls.sheet_names)
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise ExcelLoadError(text.FILE_OPEN_ERROR.format(path=path, error=exc)) from exc


def load_workbook(
    path: str,
    sheet_name: str | None = None,
    header_row_1indexed: int = 1,
    first_data_row_1indexed: int | None = None,
    last_data_row_1indexed: int | None = None,
    index_column: str | None = None,
) -> LoadedWorkbook:
    """Load an Excel workbook into a raw (unmapped) DataFrame.

    The workbook file is opened read-only via pandas/openpyxl; it is never
    written back to disk by this function or any caller.

    Args:
        path: Path to the .xlsx file.
        sheet_name: Sheet to load; defaults to the first sheet if None.
        header_row_1indexed: 1-indexed physical row holding column headers.
        first_data_row_1indexed: 1-indexed physical row where data starts;
            defaults to the row right after the header.
        last_data_row_1indexed: optional 1-indexed last data row (inclusive).
        index_column: name of the column used to detect blank spacer rows
            (rows whose value in this column is empty are dropped). If None,
            no blank-row filtering by index is performed here.

    Returns:
        A LoadedWorkbook with the raw DataFrame (headers applied, blank
        spacer rows removed if index_column is given) and metadata.

    Raises:
        ExcelLoadError: on any I/O or parsing failure.
    """
    notes: list[str] = []
    sheets = list_sheets(path)
    active_sheet = sheet_name or sheets[0]
    if active_sheet not in sheets:
        raise ExcelLoadError(text.SHEET_NOT_FOUND.format(sheet=active_sheet, sheets=sheets))

    if first_data_row_1indexed is None:
        first_data_row_1indexed = header_row_1indexed + 1
    header_idx0 = header_row_1indexed - 1
    try:
        df = pd.read_excel(
            path,
            sheet_name=active_sheet,
            header=header_idx0,
            engine="openpyxl",
        )
    except Exception as exc:
        raise ExcelLoadError(text.SHEET_READ_ERROR.format(sheet=active_sheet, error=exc)) from exc

    # Row N (1-indexed physical) maps to DataFrame position (N - header_row - 1)
    first_pos = first_data_row_1indexed - header_row_1indexed - 1
    if first_pos < 0:
        first_pos = 0
    if last_data_row_1indexed is not None:
        last_pos = last_data_row_1indexed - header_row_1indexed - 1
        df = df.iloc[first_pos : last_pos + 1].copy()
    else:
        df = df.iloc[first_pos:].copy()

    # A user-selected range commonly includes spacer/trailing rows. They
    # must never become anonymous entities merely because no id column was
    # chosen.
    before_blank_rows = len(df)
    df = df.dropna(how="all").copy()
    removed_blank_rows = before_blank_rows - len(df)
    if removed_blank_rows:
        notes.append(text.REMOVED_BLANK_ROWS.format(count=removed_blank_rows))
    df.reset_index(drop=True, inplace=True)

    if index_column is not None and index_column in df.columns:
        before = len(df)
        df = df[df[index_column].notna()].copy()
        df.reset_index(drop=True, inplace=True)
        removed = before - len(df)
        if removed:
            notes.append(text.REMOVED_ROWS_WITHOUT_ID.format(count=removed, column=index_column))

    # Drop entirely-unnamed / empty columns (e.g. blank column A).
    unnamed_cols = [c for c in df.columns if str(c).startswith("Unnamed")]
    all_na_unnamed = [c for c in unnamed_cols if df[c].isna().all()]
    if all_na_unnamed:
        df = df.drop(columns=all_na_unnamed)
        notes.append(text.REMOVED_EMPTY_COLUMNS.format(columns=all_na_unnamed))

    return LoadedWorkbook(
        path=path,
        sheet_names=sheets,
        active_sheet=active_sheet,
        raw_df=df,
        header_row_1indexed=header_row_1indexed,
        first_data_row_1indexed=first_data_row_1indexed,
        last_data_row_1indexed=last_data_row_1indexed,
        index_column=index_column,
        notes=notes,
    )
