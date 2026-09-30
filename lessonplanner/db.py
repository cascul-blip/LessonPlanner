"""SQLite storage.

The database sits in a Nextcloud-synced folder, so it uses the rollback
journal (not WAL, whose -wal/-shm side files would sync separately) and every
change is committed immediately.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DEFAULT_CLASSES = [
    "Math 87",
    "Algebra 1",
    "Algebra 2",
    "Consumer Math",
    "Science 8",
    "Biology",
    "Physics",
]
DEFAULT_SETTINGS = {
    "week1_monday": "2026-09-07",
    "backup_retention_days": "30",
}
FIELDS = ("lesson", "special", "homework")

SCHEMA = """
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    date TEXT NOT NULL,
    lesson TEXT NOT NULL DEFAULT '',
    special TEXT NOT NULL DEFAULT '',
    homework TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE (class_id, date)
);
CREATE INDEX IF NOT EXISTS entries_date ON entries(date);
CREATE TABLE IF NOT EXISTS no_school (
    date TEXT PRIMARY KEY,
    reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
SCHEMA_VERSION = 1


@dataclass
class ClassInfo:
    id: int
    name: str
    sort_order: int
    active: bool


@dataclass
class Entry:
    class_id: int
    date: date
    lesson: str = ""
    special: str = ""
    homework: str = ""

    def is_empty(self) -> bool:
        return not (self.lesson.strip() or self.special.strip() or self.homework.strip())


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(SCHEMA)
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                for key, value in DEFAULT_SETTINGS.items():
                    self.conn.execute(
                        "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
                    )
                if not self.conn.execute("SELECT 1 FROM classes").fetchone():
                    for i, name in enumerate(DEFAULT_CLASSES):
                        self.conn.execute(
                            "INSERT INTO classes(name, sort_order) VALUES (?, ?)", (name, i)
                        )
                self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def data_version(self) -> int:
        """Changes whenever another connection (e.g. the MCP server) commits."""
        return self.conn.execute("PRAGMA data_version").fetchone()[0]

    # --- settings -------------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else DEFAULT_SETTINGS.get(key)

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def week1_monday(self) -> date:
        return date.fromisoformat(self.get_setting("week1_monday"))

    def backup_retention_days(self) -> int:
        return int(self.get_setting("backup_retention_days"))

    # --- classes --------------------------------------------------------

    def classes(self, include_inactive: bool = False) -> list[ClassInfo]:
        sql = "SELECT id, name, sort_order, active FROM classes"
        if not include_inactive:
            sql += " WHERE active=1"
        sql += " ORDER BY sort_order, id"
        return [
            ClassInfo(r["id"], r["name"], r["sort_order"], bool(r["active"]))
            for r in self.conn.execute(sql)
        ]

    def class_by_name(self, name: str) -> ClassInfo | None:
        wanted = _normalize_class_name(name)
        for c in self.classes(include_inactive=True):
            if _normalize_class_name(c.name) == wanted:
                return c
        return None

    def add_class(self, name: str) -> int:
        with self.conn:
            order = self.conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM classes"
            ).fetchone()[0]
            cur = self.conn.execute(
                "INSERT INTO classes(name, sort_order) VALUES (?, ?)", (name, order)
            )
            return cur.lastrowid

    def update_class(self, class_id: int, *, name: str | None = None,
                     sort_order: int | None = None, active: bool | None = None) -> None:
        with self.conn:
            if name is not None:
                self.conn.execute("UPDATE classes SET name=? WHERE id=?", (name, class_id))
            if sort_order is not None:
                self.conn.execute(
                    "UPDATE classes SET sort_order=? WHERE id=?", (sort_order, class_id)
                )
            if active is not None:
                self.conn.execute(
                    "UPDATE classes SET active=? WHERE id=?", (int(active), class_id)
                )

    # --- entries --------------------------------------------------------

    def get_entry(self, class_id: int, day: date) -> Entry:
        row = self.conn.execute(
            "SELECT lesson, special, homework FROM entries WHERE class_id=? AND date=?",
            (class_id, day.isoformat()),
        ).fetchone()
        if row is None:
            return Entry(class_id, day)
        return Entry(class_id, day, row["lesson"], row["special"], row["homework"])

    def entries_between(self, start: date, end: date) -> list[Entry]:
        rows = self.conn.execute(
            "SELECT class_id, date, lesson, special, homework FROM entries "
            "WHERE date BETWEEN ? AND ? ORDER BY date",
            (start.isoformat(), end.isoformat()),
        )
        return [
            Entry(r["class_id"], date.fromisoformat(r["date"]), r["lesson"], r["special"],
                  r["homework"])
            for r in rows
        ]

    def save_entry(self, entry: Entry) -> None:
        """Insert/update the entry, or delete it when all fields are empty."""
        with self.conn:
            self._save_entry(entry)

    def _save_entry(self, entry: Entry) -> None:
        if entry.is_empty():
            self.conn.execute(
                "DELETE FROM entries WHERE class_id=? AND date=?",
                (entry.class_id, entry.date.isoformat()),
            )
            return
        self.conn.execute(
            "INSERT INTO entries(class_id, date, lesson, special, homework, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(class_id, date) DO UPDATE SET "
            "lesson=excluded.lesson, special=excluded.special, homework=excluded.homework, "
            "updated_at=excluded.updated_at",
            (entry.class_id, entry.date.isoformat(), entry.lesson, entry.special,
             entry.homework, _now()),
        )

    def dates_with_entries(self) -> list[date]:
        return [
            date.fromisoformat(r[0])
            for r in self.conn.execute("SELECT DISTINCT date FROM entries ORDER BY date")
        ]

    def search(self, query: str) -> list[Entry]:
        like = f"%{query}%"
        rows = self.conn.execute(
            "SELECT class_id, date, lesson, special, homework FROM entries "
            "WHERE lesson LIKE ? OR special LIKE ? OR homework LIKE ? ORDER BY date",
            (like, like, like),
        )
        return [
            Entry(r["class_id"], date.fromisoformat(r["date"]), r["lesson"], r["special"],
                  r["homework"])
            for r in rows
        ]

    # --- no-school days -------------------------------------------------

    def no_school_days(self) -> dict[date, str]:
        return {
            date.fromisoformat(r["date"]): r["reason"]
            for r in self.conn.execute("SELECT date, reason FROM no_school")
        }


def _normalize_class_name(name: str) -> str:
    """'Math 87' and '87 Math' are the same class."""
    return " ".join(sorted(name.lower().split()))
