"""Açık/koyu tema. Fusion stili her Windows sürümünde aynı görünür."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = QColor("#3b82f6")

_STYLE = """
QListWidget#sidebar {
    border: none;
    padding: 8px 6px;
    font-size: 10.5pt;
}
QListWidget#sidebar::item {
    padding: 9px 10px;
    border-radius: 6px;
    margin: 1px 0;
}
QListWidget#sidebar::item:selected {
    background: palette(highlight);
    color: palette(highlighted-text);
}
QLabel#pageTitle {
    font-size: 16pt;
    font-weight: 600;
}
QLabel#muted {
    color: palette(placeholder-text);
}
"""


def system_is_dark(app: QApplication) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt < 6.5
        return app.palette().window().color().lightness() < 128


def _dark_palette() -> QPalette:
    p = QPalette()
    window, base, text = QColor("#1f2125"), QColor("#16181b"), QColor("#e6e6e6")
    disabled = QColor("#7a7d83")
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#1b1d20"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#2b2e33"))
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, QColor("#2a2d32"))
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor("#ff6b6b"))
    p.setColor(QPalette.ColorRole.Link, QColor("#6ea8ff"))
    p.setColor(QPalette.ColorRole.Highlight, ACCENT)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8b8f96"))
    p.setColor(QPalette.ColorRole.Mid, QColor("#3a3d42"))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return p


def _light_palette(app: QApplication) -> QPalette:
    p = app.style().standardPalette()
    p.setColor(QPalette.ColorRole.Highlight, ACCENT)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return p


def is_dark(app: QApplication, mode: str) -> bool:
    return mode == "dark" or (mode == "system" and system_is_dark(app))


def apply_theme(app: QApplication, mode: str) -> None:
    app.setStyle("Fusion")
    app.setPalette(_dark_palette() if is_dark(app, mode) else _light_palette(app))
    app.setStyleSheet(_STYLE)
