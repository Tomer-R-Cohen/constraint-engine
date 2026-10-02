"""The shipped sample files load as described in the test messages."""

from pathlib import Path

from constraint_engine.workspace import Workspace

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def kinds(loaded):
    return {c["name"]: c["kind"] for c in loaded["columns"]}


def test_samples_load_with_their_id_columns():
    ws = Workspace()
    staff = ws.load_data(str(SAMPLES / "staff.csv"), id_column="Name")
    assert staff["items"] == 8 and kinds(staff)["Night qualified"] == "flag"

    lessons = ws.load_data(str(SAMPLES / "lessons.csv"), id_column="Lesson")
    assert lessons["items"] == 66
    assert {"Class", "Subject", "Teacher"} <= set(kinds(lessons))

    month = ws.load_data(str(SAMPLES / "staff_4weeks.csv"), id_column="Name")
    assert month["items"] == 25
    assert kinds(month)["Vacation week"] == "category" and kinds(month)["No nights please"] == "flag"

    students = ws.load_data(str(SAMPLES / "students.csv"), id_column="Student")
    assert students["items"] == 24
