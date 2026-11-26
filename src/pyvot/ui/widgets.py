from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase, QTextCursor
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QWidget


class OutputLog(QPlainTextEdit):
    """Komut çıktısını gösteren, salt okunur ve eşit aralıklı yazı alanı."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

    def append_text(self, text: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def append_line(self, text: str) -> None:
        if self.toPlainText() and not self.toPlainText().endswith("\n"):
            text = "\n" + text
        self.append_text(text + "\n")


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pageTitle")
    return label


def muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def quote_cmd(cmd: list[str]) -> str:
    return " ".join(f'"{part}"' if (" " in part or not part) else part for part in cmd)
