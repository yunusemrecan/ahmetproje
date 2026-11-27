"""Editörde açılmayan dosyaların önizlemesi: resim, CSV, Markdown, Jupyter defteri."""

from __future__ import annotations

import base64
import csv
import html
import json
import re
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from pyvot.core import files
from pyvot.i18n import tr
from pyvot.ui.widgets import muted

MAX_CSV_ROWS = 5000


def markdown_to_html(text: str) -> str:
    """Qt'nin kendi Markdown çeviricisiyle HTML gövdesi üretir."""
    document = QTextDocument()
    document.setMarkdown(text)
    full = document.toHtml()
    match = re.search(r"<body[^>]*>(.*)</body>", full, re.S)
    return match.group(1) if match else full


class PreviewBase(QWidget):
    open_in_editor = Signal(Path)

    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path

    def reload(self) -> None:
        """Dosya diskte değişince çağrılır."""


class ImagePreview(PreviewBase):
    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(path, parent)
        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.info = muted()
        area = QScrollArea()
        area.setWidget(self.label)
        area.setWidgetResizable(True)
        layout = QVBoxLayout(self)
        layout.addWidget(area, 1)
        layout.addWidget(self.info)
        self.reload()

    def reload(self) -> None:
        pixmap = QPixmap(str(self.path))
        if pixmap.isNull():
            self.label.setText(tr("preview.cannot_show"))
            self.info.setText("")
            return
        self.label.setPixmap(pixmap)
        self.info.setText(f"{pixmap.width()} × {pixmap.height()} px")


class CsvPreview(PreviewBase):
    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(path, parent)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.info = muted()
        edit = QPushButton(tr("preview.edit_as_text"))
        edit.clicked.connect(lambda: self.open_in_editor.emit(self.path))
        bottom = QHBoxLayout()
        bottom.addWidget(self.info, 1)
        bottom.addWidget(edit)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)
        self.reload()

    def reload(self) -> None:
        try:
            text, _ = files.read_text(self.path)
        except files.NotText:
            self.info.setText(tr("preview.cannot_show"))
            return
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(text.splitlines(), dialect))
        header, body = (rows[0], rows[1:]) if rows else ([], [])
        shown = body[:MAX_CSV_ROWS]
        self.table.clear()
        self.table.setColumnCount(max([len(header), *(len(r) for r in shown)] or [0]))
        self.table.setHorizontalHeaderLabels(header)
        self.table.setRowCount(len(shown))
        for r, row in enumerate(shown):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        note = tr("preview.csv_rows", rows=len(body), columns=self.table.columnCount())
        if len(body) > MAX_CSV_ROWS:
            note += " · " + tr("preview.csv_truncated", shown=MAX_CSV_ROWS)
        self.info.setText(note)


class MarkdownPreview(PreviewBase):
    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(path, parent)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setSearchPaths([str(path.parent)])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.addWidget(self.browser)
        self.reload()

    def reload(self) -> None:
        try:
            text, _ = files.read_text(self.path)
        except files.NotText:
            self.browser.setPlainText(tr("preview.cannot_show"))
            return
        self.browser.document().setBaseUrl(QUrl.fromLocalFile(str(self.path.parent) + "/"))
        self.browser.setMarkdown(text)


def notebook_html(data: dict, document: QTextDocument) -> str:
    """.ipynb içeriğini salt okunur HTML'e çevirir; resimler belgeye kaynak olarak eklenir."""

    def source(cell: dict) -> str:
        value = cell.get("source") or ""
        return "".join(value) if isinstance(value, list) else str(value)

    def text_of(value: object) -> str:
        return "".join(value) if isinstance(value, list) else str(value or "")

    image_count = 0
    parts: list[str] = []
    for index, cell in enumerate(data.get("cells") or []):
        kind = cell.get("cell_type")
        if kind == "markdown":
            parts.append(markdown_to_html(source(cell)))
            continue
        if kind != "code":
            parts.append(f"<pre>{html.escape(source(cell))}</pre>")
            continue
        count = cell.get("execution_count")
        label = f"[{count if count is not None else ' '}]"
        parts.append(
            f"<table width='100%' cellspacing='0' cellpadding='6' style='background:rgba(127,127,127,0.12)'>"
            f"<tr><td width='40' style='color:#3b82f6'><pre>{label}</pre></td>"
            f"<td><pre>{html.escape(source(cell))}</pre></td></tr></table>"
        )
        for output in cell.get("outputs") or []:
            otype = output.get("output_type")
            if otype == "stream":
                parts.append(f"<pre>{html.escape(text_of(output.get('text')))}</pre>")
            elif otype == "error":
                trace = "\n".join(output.get("traceback") or [])
                trace = re.sub(r"\x1b\[[0-9;]*m", "", trace)  # renk kodları
                parts.append(f"<pre style='color:#d9534f'>{html.escape(trace)}</pre>")
            elif otype in ("execute_result", "display_data"):
                bundle = output.get("data") or {}
                if "image/png" in bundle or "image/jpeg" in bundle:
                    mime = "image/png" if "image/png" in bundle else "image/jpeg"
                    raw = text_of(bundle[mime]).replace("\n", "")
                    image = QImage()
                    image.loadFromData(QByteArray(base64.b64decode(raw)))
                    if not image.isNull():
                        image_count += 1
                        name = QUrl(f"nbimage://{index}/{image_count}")
                        document.addResource(QTextDocument.ResourceType.ImageResource, name, image)
                        width = min(image.width(), 760)
                        parts.append(f"<p><img src='{name.toString()}' width='{width}'></p>")
                        continue
                if "text/html" in bundle:
                    parts.append(text_of(bundle["text/html"]))
                elif "text/plain" in bundle:
                    parts.append(f"<pre>{html.escape(text_of(bundle['text/plain']))}</pre>")
    return "\n".join(parts)


class NotebookPreview(PreviewBase):
    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(path, parent)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        note = muted(tr("preview.notebook_readonly"))
        edit_vscode = QPushButton(tr("projects.open_vscode"))
        edit_vscode.clicked.connect(self._open_vscode)
        top = QHBoxLayout()
        top.addWidget(note, 1)
        top.addWidget(edit_vscode)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.browser, 1)
        self.reload()

    def reload(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.browser.setPlainText(tr("preview.cannot_show"))
            return
        document = QTextDocument(self.browser)
        document.setHtml(notebook_html(data, document))
        self.browser.setDocument(document)

    def _open_vscode(self) -> None:
        from pyvot.core import vscode

        vscode.open_folder(self.path)


class UnsupportedPreview(PreviewBase):
    def __init__(self, path: Path, reason: str, parent: QWidget | None = None) -> None:
        super().__init__(path, parent)
        message = QLabel(tr(f"preview.not_text_{reason}", name=path.name))
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        open_system = QPushButton(tr("preview.open_system"))
        open_system.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(message)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(open_system)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)


def preview_for(path: Path) -> PreviewBase | None:
    suffix = path.suffix.lower()
    if suffix in files.IMAGE_SUFFIXES:
        return ImagePreview(path)
    if suffix == ".csv":
        return CsvPreview(path)
    if suffix == ".ipynb":
        return NotebookPreview(path)
    if suffix in (".md", ".markdown"):
        return MarkdownPreview(path)
    if suffix == ".svg":
        return ImagePreview(path)
    return None
