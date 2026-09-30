"""MCP server (stdio) so an AI agent can read and edit the lesson plans.

It opens the same database as the app, uses the same shifting rules, and
refuses to write while another computer holds the lock.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import date

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import config, lock, schedule, schoolcal
from .db import FIELDS, Database, Entry

server = MCPServer(
    "lesson-planner",
    instructions=(
        "Weekly school lesson plans. Each class has one entry per school day (Mon-Fri) with "
        "three fields: lesson (what is taught), special (optional: quizzes, tests, labs, pop "
        "quizzes, anything out of the ordinary) and homework. Dates are ISO (YYYY-MM-DD). "
        "Use insert_lesson/remove_lesson to push a class's schedule later/earlier, and "
        "mark_no_school for days when no class meets; these shift all later lessons "
        "automatically. Call current_week first to orient yourself."
    ),
)


class PlannerError(ToolError):
    """Shown to the agent as the tool's error message."""


def _folder():
    folder = config.db_folder()
    if folder is None or not folder.is_dir():
        raise PlannerError("No database folder is configured. Open the Lesson Planner app once "
                           f"to choose it, or set {config.ENV_DB_FOLDER}.")
    return folder


@contextmanager
def _open(write: bool = False):
    folder = _folder()
    if write:
        holder = lock.blocking_lock(config.lock_path(folder))
        if holder is not None:
            raise PlannerError("The lesson database is open for editing on another computer "
                               f"({holder.describe()}); changes are not allowed right now.")
    db = Database(config.db_path(folder))
    try:
        yield db
    except schedule.ScheduleError as exc:
        raise PlannerError(str(exc)) from None
    finally:
        db.close()


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise PlannerError(f"Invalid date {value!r}; use YYYY-MM-DD.") from None


def _class_id(db: Database, name: str) -> int:
    cls = db.class_by_name(name)
    if cls is None:
        names = ", ".join(c.name for c in db.classes())
        raise PlannerError(f"Unknown class {name!r}. Classes: {names}")
    return cls.id


def _entry_dict(e: Entry) -> dict:
    return {f: getattr(e, f) for f in FIELDS}


def _week(db: Database, monday: date) -> dict:
    days = schoolcal.week_days(monday)
    entries = {(e.class_id, e.date): e for e in db.entries_between(days[0], days[-1])}
    no_school = db.no_school_days()
    classes = db.classes()
    out_days = []
    for day in days:
        item = {"date": day.isoformat(), "weekday": f"{day:%A}"}
        if day in no_school:
            item["no_school"] = no_school[day] or True
        else:
            item["classes"] = {
                c.name: _entry_dict(entries[(c.id, day)])
                for c in classes if (c.id, day) in entries
            }
        out_days.append(item)
    return {
        "week": schoolcal.week_number(monday, db.week1_monday()),
        "monday": monday.isoformat(),
        "days": out_days,
    }


@server.tool()
def current_week() -> dict:
    """Today's date plus the current school week (on weekends, the upcoming week)."""
    with _open() as db:
        monday = schoolcal.current_monday()
        return {"today": date.today().isoformat(),
                "week": schoolcal.week_number(monday, db.week1_monday()),
                "monday": monday.isoformat(),
                "week1_monday": db.week1_monday().isoformat()}


@server.tool()
def list_classes() -> list[str]:
    """Names of the active classes, in display order."""
    with _open() as db:
        return [c.name for c in db.classes()]


@server.tool()
def get_week(week: int | None = None, date_in_week: str | None = None) -> dict:
    """All lessons for one school week, given a week number or any date in the week.
    With neither, returns the current week. Empty cells are omitted."""
    with _open() as db:
        if week is not None:
            monday = schoolcal.week_monday(week, db.week1_monday())
        elif date_in_week:
            monday = schoolcal.monday_of(_date(date_in_week))
        else:
            monday = schoolcal.current_monday()
        return _week(db, monday)


@server.tool()
def get_entry(class_name: str, day: str) -> dict:
    """The lesson, special and homework for one class on one date."""
    with _open() as db:
        return {"class": class_name, "date": day,
                **_entry_dict(db.get_entry(_class_id(db, class_name), _date(day)))}


@server.tool()
def set_entry(class_name: str, day: str, lesson: str | None = None,
              special: str | None = None, homework: str | None = None) -> dict:
    """Write one class's plan for one date. Omitted fields are left unchanged; pass an
    empty string to clear a field. Use newlines for multiple lines. Does not shift
    other days."""
    with _open(write=True) as db:
        d = _date(day)
        if not schoolcal.is_school_day(d, db.no_school_days()):
            raise PlannerError(f"{day} is not a school day.")
        entry = db.get_entry(_class_id(db, class_name), d)
        for field, value in (("lesson", lesson), ("special", special), ("homework", homework)):
            if value is not None:
                setattr(entry, field, value.strip())
        db.save_entry(entry)
        return {"class": class_name, "date": day, **_entry_dict(entry)}


@server.tool()
def insert_lesson(class_name: str, day: str) -> str:
    """Open an empty slot for a class on a date: that class's lessons from this date on
    each move one school day later (e.g. the class was pushed back a day). Other classes
    are unaffected. Fill the empty slot afterwards with set_entry if needed."""
    with _open(write=True) as db:
        moved = schedule.insert_lesson(db, _class_id(db, class_name), _date(day))
        return f"{class_name}: moved {moved} lesson(s) one school day later; {day} is now empty."


@server.tool()
def remove_lesson(class_name: str, day: str) -> str:
    """Delete a class's lesson on a date and pull that class's later lessons one school
    day earlier (e.g. a lesson is skipped)."""
    with _open(write=True) as db:
        moved = schedule.remove_lesson(db, _class_id(db, class_name), _date(day))
        return f"{class_name}: removed {day} and moved {moved} lesson(s) one school day earlier."


@server.tool()
def mark_no_school(day: str, reason: str = "No school") -> str:
    """Cancel school on a date (snow day, holiday...). Every class's lessons from that date
    on move one school day later."""
    with _open(write=True) as db:
        moved = schedule.mark_no_school(db, _date(day), reason)
        return f"No school on {day} ({reason}); moved {moved} lesson(s) later."


@server.tool()
def unmark_no_school(day: str) -> str:
    """Undo mark_no_school: school is held on that date after all, and every class's later
    lessons move one school day earlier."""
    with _open(write=True) as db:
        moved = schedule.unmark_no_school(db, _date(day))
        return f"{day} is a school day again; moved {moved} lesson(s) earlier."


@server.tool()
def list_no_school_days() -> dict[str, str]:
    """All dates marked as no school, with reasons."""
    with _open() as db:
        return {d.isoformat(): r for d, r in sorted(db.no_school_days().items())}


@server.tool()
def find_lessons(query: str, class_name: str | None = None) -> list[dict]:
    """Search lesson/special/homework text (case-insensitive substring), e.g. 'Quiz 4'
    or 'Lab'. Optionally limit to one class."""
    with _open() as db:
        names = {c.id: c.name for c in db.classes(include_inactive=True)}
        only = _class_id(db, class_name) if class_name else None
        return [
            {"class": names[e.class_id], "date": e.date.isoformat(), **_entry_dict(e)}
            for e in db.search(query) if only is None or e.class_id == only
        ][:200]


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    sys.exit(main())
