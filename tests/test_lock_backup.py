import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

from lessonplanner import backup, lock


def write_foreign(path, minutes_ago):
    hb = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    path.write_text(json.dumps(
        {"host": "other-pc", "user": "x", "pid": 1, "started": hb, "heartbeat": hb}))


def test_foreign_live_lock_blocks(tmp_path):
    p = tmp_path / "x.lock"
    write_foreign(p, 1)
    lk = lock.Lock(p)
    holder = lk.acquire()
    assert holder is not None and holder.host == "other-pc"
    assert not lk.owned
    assert lock.blocking_lock(p) is not None


def test_stale_and_forced_takeover(tmp_path):
    p = tmp_path / "x.lock"
    write_foreign(p, 30)
    lk = lock.Lock(p)
    assert lk.acquire() is None and lk.owned
    write_foreign(p, 1)
    assert lk.heartbeat() is not None and not lk.owned  # someone else took over
    assert lk.acquire(force=True) is None and lk.owned


def test_same_host_shares_and_release(tmp_path):
    p = tmp_path / "x.lock"
    a = lock.Lock(p)
    assert a.acquire() is None
    assert lock.blocking_lock(p) is None  # same computer (e.g. MCP server) may write
    a.release()
    assert not p.exists()


def test_backup_and_prune(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "lessonplanner.db"))
    conn.execute("CREATE TABLE t(x)")
    conn.commit()
    old = tmp_path / "lessons_08012026.db"
    old.write_text("")
    keep = tmp_path / "lessons_09152026.db"
    keep.write_text("")
    created = backup.run_daily_backup(conn, tmp_path, 30, today=date(2026, 9, 30))
    assert created.name == "lessons_09302026.db"
    assert backup.run_daily_backup(conn, tmp_path, 30, today=date(2026, 9, 30)) is None
    assert not old.exists() and keep.exists()
    assert sqlite3.connect(str(created)).execute("SELECT count(*) FROM t").fetchone() == (0,)
