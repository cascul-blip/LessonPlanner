"""Lock file that keeps two computers from editing the synced database at once.

The lock is per computer: the GUI and the MCP server running on the same
machine share it. Sync latency means this is best-effort, not a hard guarantee.
"""

from __future__ import annotations

import getpass
import json
import os
import socket
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

HEARTBEAT_SECONDS = 60
STALE_AFTER = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def this_host() -> str:
    return socket.gethostname()


@dataclass
class LockInfo:
    host: str
    user: str
    pid: int
    started: str
    heartbeat: str

    @property
    def heartbeat_time(self) -> datetime:
        return datetime.fromisoformat(self.heartbeat)

    def is_stale(self, now: datetime | None = None) -> bool:
        return (now or _now()) - self.heartbeat_time > STALE_AFTER

    def is_this_host(self) -> bool:
        return self.host == this_host()

    def describe(self) -> str:
        local = self.heartbeat_time.astimezone().strftime("%a %b %d %I:%M %p")
        return f"{self.user} on {self.host} (last active {local})"


def read(path: Path) -> LockInfo | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LockInfo(**{k: data[k] for k in LockInfo.__dataclass_fields__})
    except (OSError, ValueError, KeyError, TypeError):
        return None


def blocking_lock(path: Path) -> LockInfo | None:
    """The lock that stops this computer from writing, if any."""
    info = read(path)
    if info is None or info.is_this_host() or info.is_stale():
        return None
    return info


class Lock:
    def __init__(self, path: Path):
        self.path = path
        self.started = _now().isoformat()
        self.owned = False

    def _write(self) -> None:
        info = LockInfo(this_host(), getpass.getuser(), os.getpid(), self.started,
                        _now().isoformat())
        tmp = self.path.with_suffix(".lock.tmp")
        tmp.write_text(json.dumps(asdict(info), indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def acquire(self, force: bool = False) -> LockInfo | None:
        """Take the lock. Returns the foreign holder instead if another
        computer holds a live lock (unless `force`)."""
        holder = None if force else blocking_lock(self.path)
        if holder is not None:
            self.owned = False
            return holder
        self._write()
        self.owned = True
        return None

    def heartbeat(self) -> LockInfo | None:
        """Refresh the lock. Returns the new holder if another computer took
        it over, in which case this instance no longer owns it."""
        if not self.owned:
            return None
        current = read(self.path)
        if current is not None and not current.is_this_host() and not current.is_stale():
            self.owned = False
            return current
        self._write()
        return None

    def release(self) -> None:
        if not self.owned:
            return
        current = read(self.path)
        if current is not None and current.is_this_host() and current.pid == os.getpid():
            try:
                self.path.unlink()
            except OSError:
                pass
        self.owned = False
