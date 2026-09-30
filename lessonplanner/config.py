"""Per-machine settings. Only the database folder lives here; everything else
is stored in the database so it syncs between computers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from platformdirs import user_config_dir

APP_NAME = "LessonPlanner"
DB_FILENAME = "lessonplanner.db"
LOCK_FILENAME = "lessonplanner.lock"

# Overrides the config file; handy for tests and for pointing the MCP server
# somewhere explicit.
ENV_DB_FOLDER = "LESSONPLANNER_DB_FOLDER"


def config_path() -> Path:
    return Path(user_config_dir(APP_NAME, appauthor=False)) / "config.json"


def load() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def db_folder() -> Path | None:
    env = os.environ.get(ENV_DB_FOLDER)
    if env:
        return Path(env).expanduser()
    folder = load().get("db_folder")
    return Path(folder).expanduser() if folder else None


def set_db_folder(folder: Path) -> None:
    cfg = load()
    cfg["db_folder"] = str(folder)
    save(cfg)


def db_path(folder: Path) -> Path:
    return folder / DB_FILENAME


def lock_path(folder: Path) -> Path:
    return folder / LOCK_FILENAME
