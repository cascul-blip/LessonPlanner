from datetime import date

import pytest

from lessonplanner import schedule
from lessonplanner.db import Entry


def lessons(db, class_id):
    return {
        e.date: e.lesson
        for e in db.entries_between(date(2026, 1, 1), date(2027, 12, 31))
        if e.class_id == class_id
    }


def seed(db, class_id, days, prefix="Lesson"):
    for i, d in enumerate(days, 1):
        db.save_entry(Entry(class_id, d, f"{prefix} {i}"))


THU, FRI = date(2026, 10, 1), date(2026, 10, 2)
MON, TUE = date(2026, 10, 5), date(2026, 10, 6)


def test_insert_pushes_across_week_boundary(db):
    seed(db, 1, [THU, FRI, MON])
    seed(db, 2, [THU, FRI], prefix="Other")
    moved = schedule.insert_lesson(db, 1, THU)
    assert moved == 3
    assert lessons(db, 1) == {FRI: "Lesson 1", MON: "Lesson 2", TUE: "Lesson 3"}
    assert lessons(db, 2) == {THU: "Other 1", FRI: "Other 2"}  # other classes untouched


def test_remove_pulls_back_and_round_trips(db):
    seed(db, 1, [THU, FRI, MON])
    original = lessons(db, 1)
    schedule.insert_lesson(db, 1, THU)
    schedule.remove_lesson(db, 1, THU)  # removes the empty slot
    assert lessons(db, 1) == original
    schedule.remove_lesson(db, 1, FRI)
    assert lessons(db, 1) == {THU: "Lesson 1", FRI: "Lesson 3"}


def test_gaps_are_preserved(db):
    seed(db, 1, [THU, MON])  # Friday intentionally empty
    schedule.insert_lesson(db, 1, THU)
    assert lessons(db, 1) == {FRI: "Lesson 1", TUE: "Lesson 2"}


def test_no_school_shifts_every_class_and_round_trips(db):
    seed(db, 1, [THU, FRI, MON])
    seed(db, 2, [FRI, MON], prefix="Other")
    schedule.mark_no_school(db, FRI, "Snow day")
    assert db.no_school_days() == {FRI: "Snow day"}
    assert lessons(db, 1) == {THU: "Lesson 1", MON: "Lesson 2", TUE: "Lesson 3"}
    assert lessons(db, 2) == {MON: "Other 1", TUE: "Other 2"}
    # later inserts skip the no-school day
    schedule.insert_lesson(db, 1, THU)
    assert lessons(db, 1) == {MON: "Lesson 1", TUE: "Lesson 2", date(2026, 10, 7): "Lesson 3"}
    schedule.remove_lesson(db, 1, THU)
    schedule.unmark_no_school(db, FRI)
    assert db.no_school_days() == {}
    assert lessons(db, 1) == {THU: "Lesson 1", FRI: "Lesson 2", MON: "Lesson 3"}
    assert lessons(db, 2) == {FRI: "Other 1", MON: "Other 2"}


def test_rejects_non_school_days(db):
    with pytest.raises(schedule.ScheduleError):
        schedule.insert_lesson(db, 1, date(2026, 10, 3))  # Saturday
    schedule.mark_no_school(db, FRI)
    with pytest.raises(schedule.ScheduleError):
        schedule.remove_lesson(db, 1, FRI)


def test_empty_entries_are_deleted(db):
    db.save_entry(Entry(1, THU, "Lesson 1"))
    db.save_entry(Entry(1, THU, "  "))
    assert lessons(db, 1) == {}


def test_class_name_matching(db):
    assert db.class_by_name("87 Math").name == "Math 87"
    assert db.class_by_name("biology").name == "Biology"
