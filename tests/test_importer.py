from datetime import date
from pathlib import Path

import pytest

from lessonplanner.importer import import_workbook, split_cell

REAL_XLSX = Path.home() / "Nextcloud/Documents/LessonPlan.xlsx"


def test_split_cell():
    assert split_cell("Lesson 18\r\nRead p52-53\r\nAnswer p52 Q7\r\np53 Q1") == (
        "Lesson 18", "", "Read p52-53\nAnswer p52 Q7\np53 Q1")
    assert split_cell("Lesson 10\r\nTest 1\r\nRead p32-34") == ("Lesson 10", "Test 1", "Read p32-34")
    assert split_cell("Lesson 6\nQuiz 2\nLab 2\nComplete Lab 2") == (
        "Lesson 6", "Quiz 2\nLab 2", "Complete Lab 2")
    assert split_cell("Lesson 1\nHW: Read p5-10") == ("Lesson 1", "", "Read p5-10")
    assert split_cell("Lesosn 2") == ("Lesson 2", "", "")
    assert split_cell("Test Review") == ("Test Review", "", "")
    assert split_cell("Test") == ("", "Test", "")


@pytest.mark.skipif(not REAL_XLSX.exists(), reason="real workbook not available")
def test_import_real_workbook(db):
    report = import_workbook(db, REAL_XLSX)
    assert report.imported > 100
    assert db.no_school_days() == {date(2026, 9, 7): "Labor Day"}
    bio = db.class_by_name("Biology").id
    e = db.get_entry(bio, date(2026, 9, 28))
    assert (e.lesson, e.homework) == ("Lesson 18", "Read p52-53\nAnswer p52 Q7\np53 Q1")
    assert db.get_entry(db.class_by_name("Physics").id, date(2026, 9, 22)).special == "Test 1"
    # importing again leaves existing data alone
    assert import_workbook(db, REAL_XLSX).imported == 0
