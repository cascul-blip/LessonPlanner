"""Grid for one week: days down the side, classes across the top."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QScrollArea, QWidget

from .. import schoolcal
from ..db import Database, Entry
from .cell_widget import CellWidget

MIN_COLUMN_WIDTH = 170


class NoSchoolBanner(QLabel):
    menuRequested = Signal(object, QPoint)  # date, global pos

    def __init__(self, day: date, reason: str):
        super().__init__(f"No School — {reason or 'no reason given'}")
        self.date = day
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(48)
        self.setStyleSheet("QLabel { background: palette(alternate-base); font-style: italic;"
                           " border: 1px dashed palette(mid); border-radius: 4px; }")

    def contextMenuEvent(self, event):
        self.menuRequested.emit(self.date, event.globalPos())


class WeekView(QScrollArea):
    entryChanged = Signal(object)                     # Entry
    cellMenuRequested = Signal(object, object, QPoint, object)
    noSchoolMenuRequested = Signal(object, QPoint)

    def __init__(self, db: Database, monday: date, parent=None):
        super().__init__(parent)
        self.db = db
        self.monday = monday
        self.read_only = False
        self.cells: dict[tuple[int, date], CellWidget] = {}
        self._structure = None
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

    @property
    def loaded(self) -> bool:
        return self._structure is not None

    def showEvent(self, event):
        # weeks are built the first time their tab is shown
        if not self.loaded:
            self.reload()
        super().showEvent(event)

    def _current_structure(self):
        days = schoolcal.week_days(self.monday)
        no_school = self.db.no_school_days()
        return (tuple((c.id, c.name) for c in self.db.classes()),
                tuple((d, no_school[d]) for d in days if d in no_school))

    def reload(self, force: bool = False) -> None:
        """Refresh contents, rebuilding the grid only if its shape changed.
        Cells being edited keep their text unless `force`."""
        structure = self._current_structure()
        if structure != self._structure:
            self._build(structure)
        days = schoolcal.week_days(self.monday)
        entries = {(e.class_id, e.date): e for e in self.db.entries_between(days[0], days[-1])}
        for key, cell in self.cells.items():
            cell.set_entry(entries.get(key) or Entry(*key), force)

    def flush(self) -> None:
        for cell in self.cells.values():
            cell.flush()

    def set_read_only(self, read_only: bool) -> None:
        self.read_only = read_only
        for cell in self.cells.values():
            cell.set_read_only(read_only)

    def _build(self, structure) -> None:
        self.flush()
        self._structure = structure
        classes, no_school_rows = structure
        no_school = dict(no_school_rows)
        self.cells.clear()

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setSpacing(6)
        grid.setContentsMargins(8, 8, 8, 8)

        header_font = QFont(self.font())
        header_font.setBold(True)
        header_font.setPointSizeF(header_font.pointSizeF() * 1.1)
        for col, (_cid, name) in enumerate(classes, start=1):
            label = QLabel(name)
            label.setFont(header_font)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, 0, col)
            grid.setColumnMinimumWidth(col, MIN_COLUMN_WIDTH)
            grid.setColumnStretch(col, 1)

        today = date.today()
        for row, day in enumerate(schoolcal.week_days(self.monday), start=1):
            day_label = QLabel(f"<b>{day:%A}</b><br>{day:%b} {day.day}")
            day_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            if day == today:
                day_label.setStyleSheet("QLabel { color: palette(highlight); }")
            grid.addWidget(day_label, row, 0)
            if day in no_school:
                banner = NoSchoolBanner(day, no_school[day])
                banner.menuRequested.connect(self.noSchoolMenuRequested)
                grid.addWidget(banner, row, 1, 1, len(classes))
                continue
            for col, (cid, _name) in enumerate(classes, start=1):
                cell = CellWidget(cid, day)
                cell.set_read_only(self.read_only)
                cell.changed.connect(self.entryChanged)
                cell.menuRequested.connect(self.cellMenuRequested)
                grid.addWidget(cell, row, col)
                self.cells[(cid, day)] = cell
        grid.setRowStretch(6, 1)
        self.setWidget(grid_host)
