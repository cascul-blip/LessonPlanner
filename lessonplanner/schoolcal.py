"""School calendar: school days, week numbers and week <-> date math."""

from __future__ import annotations

from collections.abc import Container
from datetime import date, timedelta

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def current_monday(today: date | None = None) -> date:
    """Monday of the current week; on weekends, the upcoming week."""
    today = today or date.today()
    if today.weekday() >= 5:
        today += timedelta(days=7 - today.weekday())
    return monday_of(today)


def week_number(monday: date, week1_monday: date) -> int:
    return (monday_of(monday) - week1_monday).days // 7 + 1


def week_monday(number: int, week1_monday: date) -> date:
    return week1_monday + timedelta(weeks=number - 1)


def week_days(monday: date) -> list[date]:
    return [monday + timedelta(days=i) for i in range(5)]


def week_label(monday: date, week1_monday: date) -> str:
    return f"Week {week_number(monday, week1_monday)} · {monday.strftime('%b')} {monday.day}"


def is_school_day(day: date, no_school: Container[date]) -> bool:
    return day.weekday() < 5 and day not in no_school


def next_school_day(day: date, no_school: Container[date]) -> date:
    day += timedelta(days=1)
    while not is_school_day(day, no_school):
        day += timedelta(days=1)
    return day


def prev_school_day(day: date, no_school: Container[date]) -> date:
    day -= timedelta(days=1)
    while not is_school_day(day, no_school):
        day -= timedelta(days=1)
    return day
