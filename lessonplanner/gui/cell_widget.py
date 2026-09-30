"""One class on one day: Lesson / Special / Homework editors with autosave."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QPlainTextEdit, QVBoxLayout

from ..db import FIELDS, Entry
from .theme import SPECIAL_ACCENT

AUTOSAVE_MS = 1000
FIELD_LABELS = {"lesson": "Lesson", "special": "Special", "homework": "Homework"}
MIN_LINES = {"lesson": 1, "special": 1, "homework": 2}

CELL_STYLE = f"""
CellWidget {{ background: palette(base); border: 1px solid palette(mid); border-radius: 4px; }}
CellWidget[special="true"] {{ border: 2px solid {SPECIAL_ACCENT}; }}
QPlainTextEdit {{ border: none; background: transparent; }}
QPlainTextEdit[field="special"][filled="true"] {{
    background: rgba(224, 161, 0, 0.22); border-radius: 3px;
}}
QLabel {{ color: palette(placeholder-text); font-size: 8pt; }}
QLabel[field="special"][filled="true"] {{ color: {SPECIAL_ACCENT}; font-weight: bold; }}
"""


class FieldEdit(QPlainTextEdit):
    """Plain text editor that grows with its content."""

    focusLost = Signal()

    def __init__(self, field: str, parent=None):
        super().__init__(parent)
        self.field = field
        self.setProperty("field", field)
        self.setTabChangesFocus(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self._fit()

    def _fit(self, *_):
        lines = max(int(self.document().documentLayout().documentSize().height()),
                    MIN_LINES[self.field])
        fm = QFontMetrics(self.font())
        margins = self.contentsMargins()
        doc_margin = self.document().documentMargin()
        self.setFixedHeight(lines * fm.lineSpacing() + int(2 * doc_margin)
                            + margins.top() + margins.bottom() + 2)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focusLost.emit()


class CellWidget(QFrame):
    """Emits `changed(entry)` after edits settle and `menuRequested` on right-click."""

    changed = Signal(object)
    menuRequested = Signal(object, object, QPoint, object)  # class_id, date, global pos, std menu

    def __init__(self, class_id: int, day: date, parent=None):
        super().__init__(parent)
        self.class_id = class_id
        self.date = day
        self._dirty = False
        self.setStyleSheet(CELL_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 4)
        layout.setSpacing(0)
        self.edits: dict[str, FieldEdit] = {}
        self.labels: dict[str, QLabel] = {}
        for field in FIELDS:
            label = QLabel(FIELD_LABELS[field])
            label.setProperty("field", field)
            edit = FieldEdit(field)
            if field == "lesson":
                bold = QFont(edit.font())
                bold.setBold(True)
                edit.setFont(bold)
            edit.textChanged.connect(self._on_text_changed)
            edit.focusLost.connect(self.flush)
            edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            edit.customContextMenuRequested.connect(
                lambda pos, e=edit: self._context_menu(e, pos))
            layout.addWidget(label)
            layout.addWidget(edit)
            self.labels[field] = label
            self.edits[field] = edit
        layout.addStretch()

        self._timer = QTimer(self, singleShot=True, interval=AUTOSAVE_MS)
        self._timer.timeout.connect(self.flush)
        self._update_special_style()

    # --- data -------------------------------------------------------------

    def entry(self) -> Entry:
        values = {f: self.edits[f].toPlainText().rstrip() for f in FIELDS}
        return Entry(self.class_id, self.date, **values)

    def set_entry(self, entry: Entry, force: bool = False) -> None:
        """Show `entry` unless the user is in the middle of editing this cell."""
        if not force and (self._dirty or self.has_focus()):
            return
        for field in FIELDS:
            edit = self.edits[field]
            value = getattr(entry, field)
            if edit.toPlainText() != value:
                edit.blockSignals(True)
                edit.setPlainText(value)
                edit.blockSignals(False)
                edit._fit()
        self._dirty = False
        self._update_special_style()

    def has_focus(self) -> bool:
        return any(e.hasFocus() for e in self.edits.values())

    def set_read_only(self, read_only: bool) -> None:
        for edit in self.edits.values():
            edit.setReadOnly(read_only)

    def flush(self) -> None:
        self._timer.stop()
        if self._dirty:
            self._dirty = False
            self.changed.emit(self.entry())

    # --- internals ----------------------------------------------------------

    def _on_text_changed(self) -> None:
        self._dirty = True
        self._timer.start()
        self._update_special_style()

    def _update_special_style(self) -> None:
        filled = bool(self.edits["special"].toPlainText().strip())
        if self.property("special") == filled:
            return
        self.setProperty("special", filled)
        for w in (self.edits["special"], self.labels["special"]):
            w.setProperty("filled", filled)
        font = QFont(self.edits["special"].font())
        font.setBold(filled)
        self.edits["special"].setFont(font)
        # re-polish so the property-based style rules apply
        for w in (self, self.edits["special"], self.labels["special"]):
            w.style().unpolish(w)
            w.style().polish(w)

    def _context_menu(self, edit: FieldEdit, pos: QPoint) -> None:
        self.flush()
        std = edit.createStandardContextMenu()
        self.menuRequested.emit(self.class_id, self.date, edit.mapToGlobal(pos), std)
