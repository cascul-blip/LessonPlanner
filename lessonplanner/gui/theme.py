"""Follow the operating system's light/dark mode."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

# Special items stand out with the same amber in both themes.
SPECIAL_ACCENT = "#e0a100"


def _palette(dark: bool) -> QPalette:
    p = QPalette()
    if dark:
        window, base, text = QColor(37, 38, 42), QColor(27, 28, 31), QColor(225, 225, 228)
        disabled, mid, shade = QColor(130, 130, 135), QColor(70, 70, 76), QColor(20, 20, 22)
        highlight, link = QColor(60, 110, 200), QColor(110, 170, 255)
    else:
        window, base, text = QColor(239, 239, 241), QColor(255, 255, 255), QColor(25, 25, 28)
        disabled, mid, shade = QColor(120, 120, 125), QColor(180, 180, 186), QColor(150, 150, 155)
        highlight, link = QColor(48, 110, 210), QColor(20, 90, 200)
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, window)
    p.setColor(QPalette.ColorRole.ToolTipBase, window)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.PlaceholderText, disabled)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, window)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link, link)
    p.setColor(QPalette.ColorRole.Highlight, highlight)
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Mid, mid)
    p.setColor(QPalette.ColorRole.Dark, shade)
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                 QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return p


def is_dark() -> bool:
    scheme = QGuiApplication.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Unknown:
        return QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
    return scheme == Qt.ColorScheme.Dark


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setPalette(_palette(is_dark()))
    # style sheets resolve palette() colors when polished, so re-polish
    for widget in app.allWidgets():
        if widget.styleSheet():
            widget.setStyleSheet(widget.styleSheet())


def follow_system(app: QApplication, on_change=None) -> None:
    """Apply the current scheme now and whenever the OS setting changes."""
    apply(app)

    def changed(_scheme):
        apply(app)
        if on_change:
            on_change()

    app.styleHints().colorSchemeChanged.connect(changed)
