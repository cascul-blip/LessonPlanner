"""Application entry point: choose folder -> lock -> open database -> window."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import config, lock
from ..db import Database
from . import theme
from .main_window import MainWindow
from .options_dialog import choose_initial_folder


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setDesktopFileName("lessonplanner")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "resources" / "icon.png")))
    theme.follow_system(app)

    folder = config.db_folder()
    if folder is None or not folder.is_dir():
        folder = choose_initial_folder()
        if folder is None:
            return 0
        config.set_db_folder(folder)

    file_lock = lock.Lock(config.lock_path(folder))
    holder = file_lock.acquire()
    try:
        db = Database(config.db_path(folder))
    except Exception as exc:
        file_lock.release()
        QMessageBox.critical(None, "Lesson Planner", f"Could not open the database:\n{exc}")
        return 1

    window = MainWindow(folder, db, file_lock, holder)
    window.show()
    try:
        return app.exec()
    finally:
        file_lock.release()


if __name__ == "__main__":
    sys.exit(main())
