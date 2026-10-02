import pandas as pd

from constraint_engine.excel_loader import load_workbook


def test_fully_blank_rows_are_never_loaded_as_entities(tmp_path):
    path = tmp_path / "entities.xlsx"
    source = pd.DataFrame(
        [
            {"id": 1, "first": "a", "last": "a"},
            {"id": None, "first": None, "last": None},
            {"id": 2, "first": "b", "last": "b"},
        ]
    )
    source.to_excel(path, index=False, startrow=3)

    workbook = load_workbook(
        str(path),
        header_row_1indexed=4,
        first_data_row_1indexed=5,
        last_data_row_1indexed=7,
    )

    assert workbook.raw_df["id"].tolist() == [1, 2]
    assert any("blank rows" in note for note in workbook.notes)


def test_data_starts_after_the_header_by_default(tmp_path):
    path = tmp_path / "entities.xlsx"
    pd.DataFrame([{"id": 1}, {"id": 2}]).to_excel(path, index=False)
    assert load_workbook(str(path)).raw_df["id"].tolist() == [1, 2]
