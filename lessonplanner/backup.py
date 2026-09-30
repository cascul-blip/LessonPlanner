"""Daily database backups named lessons_MMDDYYYY.db, kept next to the database."""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

BACKUP_RE = re.compile(r"^lessons_(\d{2})(\d{2})(\d{4})\.db$")


def backup_name(day: date) -> str:
    return f"lessons_{day.strftime('%m%d%Y')}.db"


def backup_date(name: str) -> date | None:
    m = BACKUP_RE.match(name)
    if not m:
        return None
    month, day, year = map(int, m.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def run_daily_backup(conn: sqlite3.Connection, folder: Path, retention_days: int,
                     today: date | None = None) -> Path | None:
    """Back up today's database if not done yet and prune old backups.
    Returns the new backup path, or None if one already existed."""
    today = today or date.today()
    target = folder / backup_name(today)
    created = None
    if not target.exists():
        tmp = target.with_suffix(".tmp")
        dest = sqlite3.connect(str(tmp))
        try:
            conn.backup(dest)
        finally:
            dest.close()
        tmp.replace(target)
        created = target
    prune(folder, retention_days, today)
    return created


def prune(folder: Path, retention_days: int, today: date | None = None) -> list[Path]:
    today = today or date.today()
    cutoff = today - timedelta(days=retention_days)
    removed = []
    for path in folder.glob("lessons_*.db"):
        day = backup_date(path.name)
        if day is not None and day < cutoff:
            path.unlink()
            removed.append(path)
    return removed


def seconds_until_midnight(now: datetime | None = None) -> int:
    now = now or datetime.now()
    tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    return int((tomorrow - now).total_seconds()) + 5
