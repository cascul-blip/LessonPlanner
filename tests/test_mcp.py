import asyncio
import json
from datetime import datetime, timezone

import pytest

from lessonplanner import config
from lessonplanner.db import Database
from lessonplanner.mcp_server import server


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV_DB_FOLDER, str(tmp_path))
    Database(tmp_path / config.DB_FILENAME).close()
    return tmp_path


def call(name, **args):
    return asyncio.run(server.call_tool(name, args))


def text(result):
    return result.content[0].text


def test_set_and_shift(folder):
    call("set_entry", class_name="Biology", day="2026-10-01", lesson="Lesson 21", special="Lab 6")
    call("insert_lesson", class_name="biology", day="2026-10-01")
    week = json.loads(text(call("get_week", date_in_week="2026-10-01")))
    assert week["week"] == 4
    friday = week["days"][4]
    assert friday["classes"]["Biology"] == {"lesson": "Lesson 21", "special": "Lab 6",
                                            "homework": ""}


def test_writes_refused_when_other_computer_holds_lock(folder):
    now = datetime.now(timezone.utc).isoformat()
    (folder / config.LOCK_FILENAME).write_text(json.dumps(
        {"host": "school-pc", "user": "t", "pid": 1, "started": now, "heartbeat": now}))
    with pytest.raises(Exception, match="another computer"):
        call("set_entry", class_name="Biology", day="2026-10-01", lesson="x")
    assert "Biology" in str(call("list_classes").content)  # reads still work
