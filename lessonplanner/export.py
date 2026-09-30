"""Printing and PDF export of a week, scaled to fit one landscape page."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from . import schoolcal
from .db import Database
from .render import week_html

LOGICAL_WIDTH = 950  # layout width in document pixels before scaling to the page
TABLET_FOLDER = "Tablet"
HASH_FILE = ".contents.json"


def make_printer(pdf_path: Path | None = None) -> QPrinter:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageLayout(QPageLayout(
        QPageSize(QPageSize.PageSizeId.Letter), QPageLayout.Orientation.Landscape,
        QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter,
    ))
    if pdf_path is not None:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(pdf_path))
    return printer


def paint_html(html: str, printer: QPrinter) -> None:
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setHtml(html)
    doc.setTextWidth(LOGICAL_WIDTH)
    page = printer.pageLayout().paintRectPixels(printer.resolution())
    height = max(doc.size().height(), 1)
    scale = min(page.width() / LOGICAL_WIDTH, page.height() / height)
    painter = QPainter(printer)
    try:
        painter.scale(scale, scale)
        doc.drawContents(painter)
    finally:
        painter.end()


def export_week_pdf(db: Database, monday: date, path: Path) -> None:
    paint_html(week_html(db, monday), make_printer(path))


def tablet_pdf_name(monday: date, week1_monday: date) -> str:
    week = schoolcal.week_number(monday, week1_monday)
    return f"Week {week:02d} ({monday:%b} {monday.day:02d}).pdf"


def export_tablet(db: Database, folder: Path) -> list[Path]:
    """Keep <folder>/Tablet in sync: one read-only PDF per week that has
    lessons. Only weeks whose content changed are rewritten."""
    out_dir = folder / TABLET_FOLDER
    out_dir.mkdir(exist_ok=True)
    hash_file = out_dir / HASH_FILE
    try:
        old_hashes = json.loads(hash_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old_hashes = {}

    week1 = db.week1_monday()
    mondays = sorted({schoolcal.monday_of(d) for d in db.dates_with_entries()})
    hashes, written = {}, []
    for monday in mondays:
        name = tablet_pdf_name(monday, week1)
        html = week_html(db, monday)
        digest = hashlib.sha1(html.encode("utf-8")).hexdigest()
        hashes[name] = digest
        path = out_dir / name
        if old_hashes.get(name) != digest or not path.exists():
            paint_html(html, make_printer(path))
            written.append(path)
    for name in set(old_hashes) - set(hashes):
        (out_dir / name).unlink(missing_ok=True)
    if hashes != old_hashes:
        hash_file.write_text(json.dumps(hashes, indent=1), encoding="utf-8")
    return written
