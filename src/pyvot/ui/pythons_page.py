from __future__ import annotations

import os
import sys

from PySide6.QtCore import QModelIndex, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pyvot.core import discovery
from pyvot.core.models import PythonInstall
from pyvot.i18n import tr
from pyvot.ui.context import AppContext
from pyvot.ui.widgets import muted, page_title
from pyvot.ui.workers import run_in_background

SOURCE_KEYS = {
    "py": "source.py",
    "registry": "source.registry",
    "path": "source.path",
    "store": "source.store",
    "folder": "source.folder",
    "uv": "source.uv",
    "user": "source.user",
}

COLUMNS = ("col.version", "col.kind", "col.arch", "col.flags", "col.sources", "col.location")


class _VersionItem(QTableWidgetItem):
    """Sürümleri sayısal sıralar (3.9 < 3.10)."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        mine = self.data(Qt.ItemDataRole.UserRole + 1)
        theirs = other.data(Qt.ItemDataRole.UserRole + 1)
        if mine is not None and theirs is not None:
            return tuple(mine) < tuple(theirs)
        return super().__lt__(other)


class PythonsPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx

        self.refresh_btn = QPushButton(tr("action.refresh"))
        self.add_btn = QPushButton(tr("pythons.add"))
        self.packages_btn = QPushButton(tr("pythons.show_packages"))
        self.folder_btn = QPushButton(tr("pythons.open_folder"))
        self.copy_btn = QPushButton(tr("pythons.copy_path"))
        self.forget_btn = QPushButton(tr("pythons.forget"))

        buttons = QHBoxLayout()
        for button in (self.refresh_btn, self.add_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        for button in (self.packages_btn, self.folder_btn, self.copy_btn, self.forget_btn):
            buttons.addWidget(button)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(key) for key in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.DescendingOrder)  # en yeni sürüm üstte
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

        self.status = muted(tr("pythons.searching"))

        layout = QVBoxLayout(self)
        layout.addWidget(page_title(tr("nav.pythons")))
        layout.addWidget(muted(tr("pythons.intro")))
        layout.addLayout(buttons)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)

        self.refresh_btn.clicked.connect(self.ctx.discover)
        self.add_btn.clicked.connect(self.add_python)
        self.packages_btn.clicked.connect(self.show_packages)
        self.folder_btn.clicked.connect(self.open_folder)
        self.copy_btn.clicked.connect(self.copy_path)
        self.forget_btn.clicked.connect(self.forget)
        self.table.doubleClicked.connect(lambda _index: self.show_packages())
        self.table.itemSelectionChanged.connect(self._update_buttons)
        ctx.installs_changed.connect(self.populate)
        ctx.discovery_started.connect(self._discovery_started)
        ctx.discovery_failed.connect(self._discovery_failed)
        self._update_buttons()

    # --- tablo ---------------------------------------------------------------------

    def populate(self) -> None:
        selected = self.selected()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for install in self.ctx.installs:
            row = self.table.rowCount()
            self.table.insertRow(row)
            version = _VersionItem(install.version)
            version.setData(Qt.ItemDataRole.UserRole, install.executable)
            version.setData(Qt.ItemDataRole.UserRole + 1, list(install.version_tuple))
            if install.implementation != "cpython":
                version.setText(f"{install.version} ({install.implementation})")
            flags = []
            if install.is_default:
                flags.append(tr("flag.default"))
            if install.first_on_path:
                flags.append(tr("flag.path_first"))
            cells = [
                version,
                QTableWidgetItem(tr("kind.venv") if install.is_venv else tr("kind.system")),
                QTableWidgetItem(f"{install.bits}-bit {install.machine}".strip()),
                QTableWidgetItem(", ".join(flags)),
                QTableWidgetItem(", ".join(tr(SOURCE_KEYS.get(s, s)) for s in sorted(install.sources))),
                QTableWidgetItem(install.executable),
            ]
            cells[-1].setToolTip(install.executable)
            for column, item in enumerate(cells):
                self.table.setItem(row, column, item)
            if selected and install.executable == selected.executable:
                self.table.selectRow(row)
        self.table.setSortingEnabled(True)
        self.refresh_btn.setEnabled(True)
        count = len(self.ctx.installs)
        self.status.setText(tr("pythons.found", count=count) if count else tr("pythons.none"))
        self._update_buttons()

    def selected(self) -> PythonInstall | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        index: QModelIndex = rows[0]
        item = self.table.item(index.row(), 0)
        executable = item.data(Qt.ItemDataRole.UserRole) if item else None
        return self.ctx.find_install(executable) if executable else None

    def _update_buttons(self) -> None:
        install = self.selected()
        for button in (self.packages_btn, self.folder_btn, self.copy_btn):
            button.setEnabled(install is not None)
        self.forget_btn.setEnabled(
            install is not None and install.executable in self.ctx.settings.extra_pythons
        )

    def _discovery_started(self) -> None:
        self.status.setText(tr("pythons.searching"))
        self.refresh_btn.setEnabled(False)

    def _discovery_failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.status.setText(tr("pythons.failed", error=message))

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self.refresh_btn.setEnabled(not self.ctx.discovering)

    # --- eylemler ------------------------------------------------------------------

    def add_python(self) -> None:
        file_filter = tr("pythons.add_filter") + (" (python*.exe)" if sys.platform == "win32" else " (python*)")
        path, _ = QFileDialog.getOpenFileName(self, tr("pythons.add"), "", file_filter)
        if not path:
            return
        path = os.path.normpath(path)
        self.add_btn.setEnabled(False)

        def done(install: PythonInstall | None) -> None:
            self.add_btn.setEnabled(True)
            if install is None:
                QMessageBox.warning(self, tr("pythons.add"), tr("pythons.add_invalid", path=path))
                return
            self.ctx.add_python(path)
            self.ctx.discover()

        run_in_background(discovery.probe, path, on_done=done, on_error=lambda _e: done(None))

    def show_packages(self) -> None:
        install = self.selected()
        if install:
            self.ctx.show_packages_for.emit(install.executable)

    def open_folder(self) -> None:
        install = self.selected()
        if install:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(install.executable)))

    def copy_path(self) -> None:
        install = self.selected()
        if install:
            QGuiApplication.clipboard().setText(install.executable)
            self.status.setText(tr("pythons.copied"))

    def forget(self) -> None:
        install = self.selected()
        if install and self.ctx.forget_python(install.executable):
            self.ctx.discover()
