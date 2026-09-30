from datetime import date

from lessonplanner import schoolcal

WEEK1 = date(2026, 9, 7)


def test_week_numbers():
    assert schoolcal.week_number(date(2026, 9, 28), WEEK1) == 4
    assert schoolcal.week_number(date(2026, 9, 30), WEEK1) == 4
    assert schoolcal.week_monday(5, WEEK1) == date(2026, 10, 5)
    assert schoolcal.week_label(date(2026, 9, 28), WEEK1) == "Week 4 · Sep 28"


def test_current_week_on_weekend_is_upcoming():
    assert schoolcal.current_monday(date(2026, 9, 30)) == date(2026, 9, 28)
    assert schoolcal.current_monday(date(2026, 10, 3)) == date(2026, 10, 5)
    assert schoolcal.current_monday(date(2026, 10, 4)) == date(2026, 10, 5)


def test_school_day_navigation_skips_weekends_and_holidays():
    off = {date(2026, 10, 5)}
    assert schoolcal.next_school_day(date(2026, 10, 2), off) == date(2026, 10, 6)
    assert schoolcal.prev_school_day(date(2026, 10, 6), off) == date(2026, 10, 2)
