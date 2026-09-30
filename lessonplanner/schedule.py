"""Operations that shift lessons along the school calendar.

Shared by the GUI and the MCP server. Every operation runs in one transaction.
"""

from __future__ import annotations

from datetime import date

from . import schoolcal
from .db import Database, Entry


class ScheduleError(ValueError):
    pass


def _class_entries_from(db: Database, class_id: int, start: date) -> list[Entry]:
    rows = db.conn.execute(
        "SELECT date, lesson, special, homework FROM entries "
        "WHERE class_id=? AND date>=? ORDER BY date",
        (class_id, start.isoformat()),
    )
    return [
        Entry(class_id, date.fromisoformat(r["date"]), r["lesson"], r["special"], r["homework"])
        for r in rows
    ]


def _all_class_ids(db: Database) -> list[int]:
    return [c.id for c in db.classes(include_inactive=True)]


def _move(db: Database, entries: list[Entry], new_dates: list[date]) -> None:
    """Rewrite entries at new dates. Caller holds the transaction."""
    for e in entries:
        db.conn.execute(
            "DELETE FROM entries WHERE class_id=? AND date=?", (e.class_id, e.date.isoformat())
        )
    for e, new in zip(entries, new_dates):
        db._save_entry(Entry(e.class_id, new, e.lesson, e.special, e.homework))


def _require_school_day(day: date, no_school) -> None:
    if not schoolcal.is_school_day(day, no_school):
        raise ScheduleError(f"{day.isoformat()} is not a school day")


def _push_forward(db: Database, class_id: int, start: date, no_school) -> int:
    entries = _class_entries_from(db, class_id, start)
    _move(db, entries, [schoolcal.next_school_day(e.date, no_school) for e in entries])
    return len(entries)


def insert_lesson(db: Database, class_id: int, day: date) -> int:
    """Open an empty slot at `day`: this class's lessons from `day` on move
    one school day later. Returns the number of lessons moved."""
    no_school = db.no_school_days()
    _require_school_day(day, no_school)
    with db.conn:
        return _push_forward(db, class_id, day, no_school)


def remove_lesson(db: Database, class_id: int, day: date) -> int:
    """Delete this class's lesson at `day` and pull its later lessons one
    school day earlier. Returns the number of lessons moved."""
    no_school = db.no_school_days()
    _require_school_day(day, no_school)
    with db.conn:
        db.conn.execute(
            "DELETE FROM entries WHERE class_id=? AND date=?", (class_id, day.isoformat())
        )
        later = _class_entries_from(db, class_id, schoolcal.next_school_day(day, no_school))
        _move(db, later, [schoolcal.prev_school_day(e.date, no_school) for e in later])
        return len(later)


def mark_no_school(db: Database, day: date, reason: str = "") -> int:
    """Cancel school on `day`; every class's lessons from that day on move one
    school day later. Returns the number of lessons moved."""
    no_school = db.no_school_days()
    if day in no_school:
        with db.conn:
            db.conn.execute("UPDATE no_school SET reason=? WHERE date=?", (reason, day.isoformat()))
        return 0
    _require_school_day(day, no_school)
    no_school[day] = reason
    moved = 0
    with db.conn:
        for class_id in _all_class_ids(db):
            moved += _push_forward(db, class_id, day, no_school)
        db.conn.execute(
            "INSERT INTO no_school(date, reason) VALUES (?, ?)", (day.isoformat(), reason)
        )
    return moved


def unmark_no_school(db: Database, day: date) -> int:
    """Restore school on `day`; every class's later lessons move one school
    day earlier. Returns the number of lessons moved."""
    no_school = db.no_school_days()
    if day not in no_school:
        return 0
    del no_school[day]
    moved = 0
    with db.conn:
        db.conn.execute("DELETE FROM no_school WHERE date=?", (day.isoformat(),))
        after = schoolcal.next_school_day(day, no_school)
        for class_id in _all_class_ids(db):
            later = _class_entries_from(db, class_id, after)
            _move(db, later, [schoolcal.prev_school_day(e.date, no_school) for e in later])
            moved += len(later)
    return moved
