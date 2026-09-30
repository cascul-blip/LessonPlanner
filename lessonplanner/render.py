"""Week view as print-oriented HTML (the subset QTextDocument understands)."""

from __future__ import annotations

from datetime import date
from html import escape

from . import schoolcal
from .db import Database


def _lines(text: str) -> str:
    return "<br>".join(escape(line) for line in text.splitlines())


def week_html(db: Database, monday: date) -> str:
    classes = db.classes()
    days = schoolcal.week_days(monday)
    entries = {(e.class_id, e.date): e for e in db.entries_between(days[0], days[-1])}
    no_school = db.no_school_days()
    week = schoolcal.week_number(monday, db.week1_monday())
    friday = days[-1]

    col_width = 92 // max(len(classes), 1)
    out = [
        "<html><body style='font-family: sans-serif; font-size: 9pt; color: #000;'>",
        f"<h3 style='margin: 0 0 4px 0;'>Week {week} &ndash; "
        f"{monday:%b} {monday.day} to {friday:%b} {friday.day}, {friday.year}</h3>",
        "<table width='100%' border='1' cellspacing='0' cellpadding='3' "
        "style='border-collapse: collapse; border-color: #555;'>",
        "<tr><th width='8%' style='background: #ddd;'></th>",
    ]
    out += [f"<th width='{col_width}%' style='background: #ddd;'>{escape(c.name)}</th>"
            for c in classes]
    out.append("</tr>")

    for day in days:
        out.append(f"<tr><td valign='top' style='background: #eee;'><b>{day:%a}</b><br>"
                   f"{day:%b} {day.day}</td>")
        if day in no_school:
            reason = escape(no_school[day] or "No school")
            out.append(f"<td colspan='{len(classes)}' align='center' valign='middle' "
                       f"style='background: #eee;'><i>No School &ndash; {reason}</i></td></tr>")
            continue
        for c in classes:
            e = entries.get((c.id, day))
            parts = []
            if e is not None:
                if e.lesson.strip():
                    parts.append(f"<b>{_lines(e.lesson)}</b>")
                if e.special.strip():
                    parts.append(
                        "<table width='100%' border='1' cellspacing='0' cellpadding='2' "
                        "style='border-collapse: collapse; border-color: #000; margin: 2px 0;'>"
                        f"<tr><td style='background: #ffe9a8;'><b>&#9733; {_lines(e.special)}"
                        "</b></td></tr></table>"
                    )
                if e.homework.strip():
                    parts.append(f"<i>HW:</i> {_lines(e.homework)}")
            out.append(f"<td valign='top'>{'<br>'.join(parts)}</td>")
        out.append("</tr>")
    out.append("</table></body></html>")
    return "\n".join(out)
