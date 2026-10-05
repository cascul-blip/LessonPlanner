"""Main window: week tabs, read-only banner, menus and background timers."""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtPrintSupport import QPrintDialog
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox,
    QPushButton, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)
from shiboken6 import isValid

from .. import backup, config, export, lock, schedule, schoolcal
from ..db import Database, Entry
from ..importer import import_workbook
from ..render import week_html
from .options_dialog import OptionsDialog
from .week_view import WeekView

POLL_MS = 3000
TABLET_EXPORT_DELAY_MS = 30_000


class MainWindow(QMainWindow):
    def __init__(self, folder: Path, db: Database, file_lock: lock.Lock,
                 holder: lock.LockInfo | None):
        super().__init__()
        self.folder = folder
        self.db = db
        self.lock = file_lock
        self.read_only = False
        self.views: dict[date, WeekView] = {}
        self.extra_weeks: set[date] = set()
        self._tab_weeks: list[date] = []
        self._data_version = db.data_version()
        self._db_stat = self._stat()

        self.setWindowTitle("Lesson Planner")
        self.resize(1400, 900)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_banner())
        self.tabs = QTabWidget(documentMode=True)
        add_week = QToolButton(text="+", toolTip="Add the next week")
        add_week.clicked.connect(self.add_next_week)
        self.tabs.setCornerWidget(add_week, Qt.Corner.TopRightCorner)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self._build_menus()

        self.rebuild_tabs(select=schoolcal.current_monday())
        self.set_read_only(holder)

        self._poll_timer = QTimer(self, interval=POLL_MS, timeout=self.poll)
        self._poll_timer.start()
        self._heartbeat_timer = QTimer(self, interval=lock.HEARTBEAT_SECONDS * 1000,
                                       timeout=self.heartbeat)
        self._heartbeat_timer.start()
        self._tablet_timer = QTimer(self, singleShot=True, interval=TABLET_EXPORT_DELAY_MS,
                                    timeout=self.export_tablet)
        self._backup_timer = QTimer(self, singleShot=True, timeout=self.daily_backup)
        self.daily_backup()
        self.schedule_tablet_export()

    # --- layout -------------------------------------------------------------

    def _build_banner(self) -> QWidget:
        self.banner = QFrame()
        self.banner.setStyleSheet(
            "QFrame { background: #f7d774; } QLabel { color: #222; }"
            " QPushButton { color: #222; background: #fff3c4; border: 1px solid #b08d1a;"
            " padding: 3px 10px; border-radius: 3px; }")
        row = QHBoxLayout(self.banner)
        row.setContentsMargins(10, 6, 10, 6)
        self.banner_label = QLabel()
        self.banner_label.setWordWrap(True)
        self.take_over_button = QPushButton("Take over anyway…")
        self.take_over_button.clicked.connect(self.take_over)
        row.addWidget(self.banner_label, 1)
        row.addWidget(self.take_over_button)
        self.banner.hide()
        return self.banner

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.print_action = self._action(file_menu, "&Print week…", self.print_week,
                                         QKeySequence.StandardKey.Print)
        self._action(file_menu, "&Export week to PDF…", self.export_pdf, "Ctrl+E")
        file_menu.addSeparator()
        self.import_action = self._action(file_menu, "&Import from Excel…", self.import_excel)
        self._action(file_menu, "&Options…", self.open_options, "Ctrl+,")
        file_menu.addSeparator()
        self._action(file_menu, "&Quit", self.close, QKeySequence.StandardKey.Quit)

        view_menu = self.menuBar().addMenu("&View")
        self._action(view_menu, "&This week", self.go_to_current_week, "Ctrl+T")
        self._action(view_menu, "&Add next week", self.add_next_week, "Ctrl+N")
        self._action(view_menu, "&Reload", lambda: self.refresh_all(force=True),
                     QKeySequence.StandardKey.Refresh)

    def _action(self, menu: QMenu, text: str, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        menu.addAction(action)
        return action

    # --- weeks / tabs -----------------------------------------------------------

    def week_list(self) -> list[date]:
        mondays = {schoolcal.monday_of(d) for d in self.db.dates_with_entries()}
        mondays |= self.extra_weeks | {schoolcal.current_monday()}
        return sorted(mondays, reverse=True)  # newest on the left

    def current_view(self) -> WeekView | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, WeekView) else None

    def _view(self, monday: date) -> WeekView:
        view = self.views.get(monday)
        if view is None:
            view = WeekView(self.db, monday)
            view.set_read_only(self.read_only)
            view.entryChanged.connect(self.save_entry)
            view.cellMenuRequested.connect(self.cell_menu)
            view.noSchoolMenuRequested.connect(self.no_school_menu)
            self.views[monday] = view
        return view

    def _tab_text(self, monday: date) -> str:
        text = schoolcal.week_label(monday, self.db.week1_monday())
        return f"{text}  (this week)" if monday == schoolcal.current_monday() else text

    def rebuild_tabs(self, select: date | None = None) -> None:
        current = self.current_view()
        select = select or (current.monday if current else schoolcal.current_monday())
        weeks = self.week_list()
        if weeks != self._tab_weeks:
            self.tabs.blockSignals(True)
            self.tabs.clear()
            for monday in weeks:
                self.tabs.addTab(self._view(monday), self._tab_text(monday))
            self.tabs.blockSignals(False)
            self._tab_weeks = weeks
        else:
            for i, monday in enumerate(weeks):
                self.tabs.setTabText(i, self._tab_text(monday))
        if select in weeks:
            self.tabs.setCurrentIndex(weeks.index(select))

    def go_to_current_week(self) -> None:
        self.rebuild_tabs(select=schoolcal.current_monday())

    def add_next_week(self) -> None:
        latest = max(self.week_list())
        new = latest + timedelta(weeks=1)
        self.extra_weeks.add(new)
        self.rebuild_tabs(select=new)

    def flush_all(self) -> None:
        for view in self.views.values():
            view.flush()

    def refresh_all(self, force: bool = False) -> None:
        for view in self.views.values():
            view.db = self.db
            if view.loaded:
                view.reload(force)
        self.rebuild_tabs()

    def _after_change(self, message: str | None = None) -> None:
        self.refresh_all(force=True)  # pending edits were flushed before the change
        self._data_version = self.db.data_version()
        self.schedule_tablet_export()
        if message:
            self.statusBar().showMessage(message, 6000)

    # --- editing ------------------------------------------------------------------

    def save_entry(self, entry: Entry) -> None:
        if self.read_only:
            return
        self.db.save_entry(entry)
        self._data_version = self.db.data_version()
        if schoolcal.monday_of(entry.date) not in self._tab_weeks:
            self.rebuild_tabs()
        self.schedule_tablet_export()
        self.statusBar().showMessage("Saved", 1500)

    def _class_name(self, class_id: int) -> str:
        return next((c.name for c in self.db.classes(include_inactive=True) if c.id == class_id),
                    "?")

    def cell_menu(self, class_id: int, day: date, pos: QPoint, std_menu: QMenu) -> None:
        name = self._class_name(class_id)
        menu = QMenu(self)
        title = menu.addAction(f"{name} — {day:%a %b} {day.day}")
        title.setEnabled(False)
        menu.addSeparator()
        writable = not self.read_only
        for text, slot in (
            ("Insert lesson here (push later lessons forward)",
             lambda: self.insert_lesson(class_id, day)),
            ("Remove this lesson (pull later lessons back)",
             lambda: self.remove_lesson(class_id, day)),
            ("Clear this cell", lambda: self.clear_cell(class_id, day)),
        ):
            menu.addAction(text, slot).setEnabled(writable)
        menu.addSeparator()
        menu.addAction(f"Mark {day:%A} as No School (all classes)…",
                       lambda: self.mark_no_school(day)).setEnabled(writable)
        menu.addSeparator()
        for action in std_menu.actions():
            menu.addAction(action)
        menu.exec(pos)
        menu.deleteLater()
        if isValid(std_menu):  # the chosen action may have rebuilt the grid that owned it
            std_menu.deleteLater()

    def no_school_menu(self, day: date, pos: QPoint) -> None:
        menu = QMenu(self)
        writable = not self.read_only
        menu.addAction("Edit reason…", lambda: self.edit_no_school_reason(day)).setEnabled(writable)
        menu.addAction("Remove No School (pull all classes back a day)",
                       lambda: self.unmark_no_school(day)).setEnabled(writable)
        menu.exec(pos)
        menu.deleteLater()

    def _confirm(self, text: str) -> bool:
        return QMessageBox.question(self, "Lesson Planner", text) == \
            QMessageBox.StandardButton.Yes

    def _run(self, op, *args) -> int | None:
        self.flush_all()
        try:
            return op(self.db, *args)
        except schedule.ScheduleError as exc:
            QMessageBox.warning(self, "Lesson Planner", str(exc))
            return None

    def insert_lesson(self, class_id: int, day: date) -> None:
        moved = self._run(schedule.insert_lesson, class_id, day)
        if moved is not None:
            self._after_change(f"{self._class_name(class_id)}: moved {moved} lesson(s) forward")
            view = self.views.get(schoolcal.monday_of(day))
            cell = view.cells.get((class_id, day)) if view else None
            if cell:
                cell.edits["lesson"].setFocus()

    def remove_lesson(self, class_id: int, day: date) -> None:
        self.flush_all()
        entry = self.db.get_entry(class_id, day)
        if not entry.is_empty():
            first = (entry.lesson or entry.special or entry.homework).splitlines()[0]
            if not self._confirm(f"Remove “{first}” from {self._class_name(class_id)} on "
                                 f"{day:%a %b} {day.day} and pull its later lessons back "
                                 "one school day?"):
                return
        moved = self._run(schedule.remove_lesson, class_id, day)
        if moved is not None:
            self._after_change(f"{self._class_name(class_id)}: moved {moved} lesson(s) back")

    def clear_cell(self, class_id: int, day: date) -> None:
        self.flush_all()
        if self.db.get_entry(class_id, day).is_empty():
            return
        if self._confirm(f"Clear {self._class_name(class_id)} on {day:%a %b} {day.day}? "
                         "Other days are not moved."):
            self.db.save_entry(Entry(class_id, day))
            self._after_change("Cleared")

    def mark_no_school(self, day: date) -> None:
        reason, ok = QInputDialog.getText(
            self, "No School",
            f"No school on {day:%A %b} {day.day}.\nEvery class's lessons from this day on "
            "will move one school day later.\n\nReason:", text="No school")
        if ok:
            moved = self._run(schedule.mark_no_school, day, reason.strip())
            if moved is not None:
                self._after_change(f"No school {day:%a %b} {day.day}: moved {moved} lesson(s)")

    def edit_no_school_reason(self, day: date) -> None:
        current = self.db.no_school_days().get(day, "")
        reason, ok = QInputDialog.getText(self, "No School", "Reason:", text=current)
        if ok:
            self._run(schedule.mark_no_school, day, reason.strip())
            self._after_change()

    def unmark_no_school(self, day: date) -> None:
        if self._confirm(f"Hold school on {day:%A %b} {day.day} after all? Every class's later "
                         "lessons move one school day earlier."):
            moved = self._run(schedule.unmark_no_school, day)
            if moved is not None:
                self._after_change(f"Moved {moved} lesson(s) back")

    # --- lock / read-only ---------------------------------------------------------

    def set_read_only(self, holder: lock.LockInfo | None) -> None:
        self.read_only = holder is not None
        for view in self.views.values():
            view.set_read_only(self.read_only)
        self.import_action.setEnabled(not self.read_only)
        if holder is None:
            self.banner.hide()
            return
        self.banner_label.setText(
            f"<b>Read-only.</b> The lesson database is open on another computer: "
            f"{holder.describe()}. Close it there to edit here.")
        self.banner.show()

    def take_over(self) -> None:
        if self._confirm("Take over the database? Only do this if the other computer is not "
                         "actually using Lesson Planner (for example it crashed or was left "
                         "open and asleep)."):
            self.lock.acquire(force=True)
            self.set_read_only(None)
            self.daily_backup()

    def heartbeat(self) -> None:
        if self.lock.owned:
            holder = self.lock.heartbeat()
            if holder is not None:
                self.flush_all()
                self.set_read_only(holder)
            return
        holder = self.lock.acquire()  # succeeds once the other computer lets go
        if holder is None:
            self.set_read_only(None)
            self.statusBar().showMessage("The other computer closed the planner; editing is "
                                         "enabled.", 10000)
            self.daily_backup()
        else:
            self.set_read_only(holder)

    # --- external changes ------------------------------------------------------------

    def _stat(self):
        try:
            st = os.stat(self.db.path)
            return st.st_ino, st.st_dev
        except OSError:
            return None

    def poll(self) -> None:
        """Pick up changes from the MCP server or from Nextcloud replacing the file."""
        stat = self._stat()
        if stat is not None and stat != self._db_stat:
            # the sync client swapped in a new file; reopen it
            self._db_stat = stat
            self.flush_all()
            self.db.close()
            self.db = Database(self.db.path)
            self._data_version = -1
        version = self.db.data_version()
        if version != self._data_version:
            self._data_version = version
            self.refresh_all()
            self.schedule_tablet_export()

    # --- backup / export ---------------------------------------------------------

    def daily_backup(self) -> None:
        if self.lock.owned:
            try:
                created = backup.run_daily_backup(self.db.conn, self.folder,
                                                  self.db.backup_retention_days())
                if created:
                    self.statusBar().showMessage(f"Backed up to {created.name}", 5000)
            except (OSError, Exception) as exc:  # a failed backup must not stop the app
                self.statusBar().showMessage(f"Backup failed: {exc}", 10000)
        self._backup_timer.start(backup.seconds_until_midnight() * 1000)

    def schedule_tablet_export(self) -> None:
        self._tablet_timer.start()

    def export_tablet(self) -> None:
        if not self.lock.owned:
            return
        try:
            written = export.export_tablet(self.db, self.folder)
            if written:
                self.statusBar().showMessage(
                    f"Updated {len(written)} tablet PDF(s) in {export.TABLET_FOLDER}/", 4000)
        except Exception as exc:
            self.statusBar().showMessage(f"Tablet export failed: {exc}", 10000)

    def print_week(self) -> None:
        view = self.current_view()
        if view is None:
            return
        self.flush_all()
        printer = export.make_printer()
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            export.paint_html(week_html(self.db, view.monday), printer)

    def export_pdf(self) -> None:
        view = self.current_view()
        if view is None:
            return
        self.flush_all()
        default = Path.home() / export.tablet_pdf_name(view.monday, self.db.week1_monday())
        path, _ = QFileDialog.getSaveFileName(self, "Export week to PDF", str(default),
                                              "PDF files (*.pdf)")
        if path:
            export.export_week_pdf(self.db, view.monday, Path(path))
            self.statusBar().showMessage(f"Saved {path}", 5000)

    def import_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import from Excel", str(Path.home()),
                                              "Excel files (*.xlsx *.xlsm)")
        if not path:
            return
        self.flush_all()
        try:
            report = import_workbook(self.db, Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "Import", f"Import failed:\n{exc}")
            return
        self._after_change()
        box = QMessageBox(QMessageBox.Icon.Information, "Import",
                          report.summary().split("\n", 1)[0], parent=self)
        box.setDetailedText(report.summary())
        box.exec()

    def open_options(self) -> None:
        self.flush_all()
        dialog = OptionsDialog(self.db, self.folder, self.read_only, self)
        if dialog.exec():
            self._after_change()
            if dialog.folder_changed:
                QMessageBox.information(self, "Options", "Restart Lesson Planner to use the "
                                        f"new folder:\n{config.db_folder()}")

    def closeEvent(self, event) -> None:
        # an overdue timer can still fire once after this returns
        for timer in (self._poll_timer, self._heartbeat_timer, self._backup_timer):
            timer.stop()
        self.flush_all()
        self.hide()  # the tablet export below can take a few seconds
        if self._tablet_timer.isActive():
            self._tablet_timer.stop()
            self.export_tablet()
        self.lock.release()
        self.db.close()
        super().closeEvent(event)
