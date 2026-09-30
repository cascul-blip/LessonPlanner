"""Options: database folder, calendar, backups and the class list."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from .. import config
from ..db import Database

ID_ROLE = Qt.ItemDataRole.UserRole


class OptionsDialog(QDialog):
    def __init__(self, db: Database, folder: Path, read_only: bool, parent=None):
        super().__init__(parent)
        self.db = db
        self.folder_changed = False
        self.setWindowTitle("Options")
        self.resize(520, 560)
        layout = QVBoxLayout(self)

        # --- storage (per computer) ---
        storage = QGroupBox("Database folder (this computer)")
        row = QHBoxLayout(storage)
        self.folder_edit = QLineEdit(str(folder))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder_edit)
        row.addWidget(browse)
        layout.addWidget(storage)

        # --- shared settings (stored in the database) ---
        shared = QGroupBox("School year (shared)")
        form = QFormLayout(shared)
        self.week1 = QDateEdit(calendarPopup=True)
        self.week1.setDisplayFormat("ddd MMM d, yyyy")
        w1 = db.week1_monday()
        self.week1.setDate(QDate(w1.year, w1.month, w1.day))
        form.addRow("Monday of Week 1:", self.week1)
        self.retention = QSpinBox(minimum=1, maximum=3650, suffix=" days")
        self.retention.setValue(db.backup_retention_days())
        form.addRow("Keep daily backups for:", self.retention)
        layout.addWidget(shared)

        classes = QGroupBox("Classes (checked = active; unchecked classes are hidden, "
                            "their lessons are kept)")
        box = QHBoxLayout(classes)
        self.class_list = QListWidget()
        for c in db.classes(include_inactive=True):
            item = QListWidgetItem(c.name)
            item.setData(ID_ROLE, c.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if c.active else Qt.CheckState.Unchecked)
            self.class_list.addItem(item)
        box.addWidget(self.class_list)
        buttons = QVBoxLayout()
        for text, slot in (("Add…", self._add), ("Rename…", self._rename),
                           ("Move up", lambda: self._move(-1)),
                           ("Move down", lambda: self._move(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        buttons.addStretch()
        box.addLayout(buttons)
        layout.addWidget(classes, 1)

        if read_only:
            for w in (shared, classes):
                w.setEnabled(False)
                w.setToolTip("Read-only: another computer has the database open.")

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self._read_only = read_only

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Database folder", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def _add(self) -> None:
        name, ok = QInputDialog.getText(self, "Add class", "Class name:")
        if ok and name.strip():
            item = QListWidgetItem(name.strip())
            item.setData(ID_ROLE, None)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.class_list.addItem(item)

    def _rename(self) -> None:
        item = self.class_list.currentItem()
        if item is None:
            return
        name, ok = QInputDialog.getText(self, "Rename class", "Class name:", text=item.text())
        if ok and name.strip():
            item.setText(name.strip())

    def _move(self, delta: int) -> None:
        row = self.class_list.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self.class_list.count():
            return
        item = self.class_list.takeItem(row)
        self.class_list.insertItem(target, item)
        self.class_list.setCurrentRow(target)

    def _accept(self) -> None:
        names = [self.class_list.item(i).text().strip() for i in range(self.class_list.count())]
        if len({n.lower() for n in names}) != len(names):
            QMessageBox.warning(self, "Options", "Two classes have the same name.")
            return
        qd = self.week1.date()
        week1 = date(qd.year(), qd.month(), qd.day())
        if week1.weekday() != 0:
            QMessageBox.warning(self, "Options", "Week 1 must start on a Monday.")
            return

        new_folder = Path(self.folder_edit.text()).expanduser()
        if new_folder != config.db_folder():
            if not new_folder.is_dir():
                QMessageBox.warning(self, "Options", f"Folder does not exist:\n{new_folder}")
                return
            config.set_db_folder(new_folder)
            self.folder_changed = True

        if not self._read_only:
            self.db.set_setting("week1_monday", week1.isoformat())
            self.db.set_setting("backup_retention_days", str(self.retention.value()))
            for order in range(self.class_list.count()):
                item = self.class_list.item(order)
                active = item.checkState() == Qt.CheckState.Checked
                class_id = item.data(ID_ROLE)
                if class_id is None:
                    class_id = self.db.add_class(item.text().strip())
                self.db.update_class(class_id, name=item.text().strip(), sort_order=order,
                                     active=active)
        self.accept()


def choose_initial_folder(parent: QWidget | None = None) -> Path | None:
    QMessageBox.information(
        parent, "Lesson Planner",
        "Choose the folder that holds (or will hold) the lesson database.\n\n"
        "Pick a folder inside Nextcloud so it syncs between computers. "
        "Daily backups are saved in the same folder.",
    )
    folder = QFileDialog.getExistingDirectory(parent, "Database folder", str(Path.home()))
    return Path(folder) if folder else None
