from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QFile, QPoint, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from pyvot.core import projects, terminal, vscode
from pyvot.i18n import tr
from pyvot.ui.context import AppContext
from pyvot.ui.existing_project_dialog import ExistingProjectDialog, needs_setup
from pyvot.ui.new_project_wizard import NewProjectWizard
from pyvot.ui.widgets import muted, page_title

COLUMNS = ("col.pin", "col.project", "col.python", "col.environment", "col.last_opened", "col.location")


def move_to_trash(path: Path) -> bool:
    """Klasörü çöp kutusuna (Windows: Geri Dönüşüm Kutusu) taşır.

    PySide6 sürüme göre bool ya da (bool, yol) döndürebiliyor.
    """
    result = QFile.moveToTrash(str(path))
    moved = result[0] if isinstance(result, tuple) else result
    return bool(moved) and not path.exists()


def _format_time(stamp: str) -> str:
    if not stamp:
        return ""
    try:
        moment = datetime.fromisoformat(stamp).astimezone()
    except ValueError:
        return stamp
    return moment.strftime("%d.%m.%Y %H:%M")


class ProjectsPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.infos: dict[str, projects.ProjectInfo] = {}

        self.new_btn = QPushButton(tr("projects.new"))
        self.new_btn.setDefault(True)
        self.add_btn = QPushButton(tr("projects.add_existing"))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("projects.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        top = QHBoxLayout()
        top.addWidget(self.new_btn)
        top.addWidget(self.add_btn)
        top.addStretch(1)
        top.addWidget(self.search)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(key) for key in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(1, 220)

        self.vscode_btn = QPushButton(tr("projects.open_vscode"))
        self.folder_btn = QPushButton(tr("projects.open_folder"))
        self.terminal_btn = QPushButton(tr("projects.open_terminal"))
        self.packages_btn = QPushButton(tr("projects.show_packages"))
        self.pin_btn = QPushButton(tr("projects.pin"))
        self.remove_btn = QPushButton(tr("projects.remove"))
        self.trash_btn = QPushButton(tr("projects.trash"))
        actions = QHBoxLayout()
        for button in (self.vscode_btn, self.folder_btn, self.terminal_btn, self.packages_btn):
            actions.addWidget(button)
        actions.addStretch(1)
        for button in (self.pin_btn, self.remove_btn, self.trash_btn):
            actions.addWidget(button)

        self.empty_label = muted(tr("projects.empty"))
        self.status = muted()

        layout = QVBoxLayout(self)
        layout.addWidget(page_title(tr("nav.projects")))
        layout.addWidget(muted(tr("projects.intro")))
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.empty_label)
        layout.addLayout(actions)
        layout.addWidget(self.status)

        self.new_btn.clicked.connect(self.new_project)
        self.add_btn.clicked.connect(self.add_existing)
        self.search.textChanged.connect(self.apply_filter)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.doubleClicked.connect(lambda _index: self.open_vscode())
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.vscode_btn.clicked.connect(self.open_vscode)
        self.folder_btn.clicked.connect(self.open_folder)
        self.terminal_btn.clicked.connect(self.open_terminal)
        self.packages_btn.clicked.connect(self.show_packages)
        self.pin_btn.clicked.connect(self.toggle_pin)
        self.remove_btn.clicked.connect(self.remove)
        self.trash_btn.clicked.connect(self.move_to_trash)
        self.refresh()

    # --- liste -------------------------------------------------------------------------

    def refresh(self, select: str | Path | None = None) -> None:
        current = str(select) if select is not None else self.selected_path()
        self.infos.clear()
        self.table.setRowCount(0)
        warn = QColor("#d9534f")
        for entry in self.ctx.projects.sorted():
            path = Path(entry.path)
            info = projects.inspect(path)
            self.infos[entry.path] = info
            row = self.table.rowCount()
            self.table.insertRow(row)
            if not info.exists:
                env_text = tr("projects.missing")
            elif info.venv is None:
                env_text = tr("venv.none")
            else:
                env_text = tr("venv." + info.venv_state)
            cells = [
                QTableWidgetItem("★" if entry.pinned else ""),
                QTableWidgetItem(entry.name),
                QTableWidgetItem(info.python_version),
                QTableWidgetItem(env_text),
                QTableWidgetItem(_format_time(entry.last_opened or entry.added)),
                QTableWidgetItem(entry.path),
            ]
            cells[1].setData(Qt.ItemDataRole.UserRole, entry.path)
            cells[1].setToolTip(entry.path)
            font = cells[1].font()
            font.setBold(True)
            cells[1].setFont(font)
            if not info.exists or info.venv_state == "broken":
                cells[3].setForeground(warn)
            for column, item in enumerate(cells):
                self.table.setItem(row, column, item)
            if current and entry.path == current:
                self.table.selectRow(row)
        has_projects = self.table.rowCount() > 0
        self.table.setVisible(has_projects)
        self.empty_label.setVisible(not has_projects)
        self.apply_filter()
        self._update_buttons()

    def apply_filter(self) -> None:
        needle = self.search.text().strip().lower()
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 1)
            location = self.table.item(row, 5)
            text = f"{name.text() if name else ''} {location.text() if location else ''}".lower()
            self.table.setRowHidden(row, bool(needle) and needle not in text)

    def selected_path(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def selected_info(self) -> projects.ProjectInfo | None:
        path = self.selected_path()
        return self.infos.get(path) if path else None

    def _update_buttons(self) -> None:
        info = self.selected_info()
        exists = info is not None and info.exists
        for button in (self.vscode_btn, self.folder_btn, self.terminal_btn, self.trash_btn):
            button.setEnabled(exists)
        self.packages_btn.setEnabled(exists and info is not None and info.interpreter is not None)
        self.remove_btn.setEnabled(info is not None)
        self.pin_btn.setEnabled(info is not None)
        entry = self.ctx.projects.find(info.path) if info else None
        self.pin_btn.setText(tr("projects.unpin") if entry and entry.pinned else tr("projects.pin"))

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self.refresh()

    # --- eylemler ----------------------------------------------------------------------

    def new_project(self) -> None:
        if not self.ctx.installs and self.ctx.discovering:
            self.status.setText(tr("pythons.searching"))
        wizard = NewProjectWizard(self.ctx, self)
        wizard.exec()
        if wizard.created is not None:
            self.refresh(select=str(wizard.created))

    def add_existing(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("projects.add_existing"))
        if not folder:
            return
        path = Path(folder)
        if self.ctx.projects.find(path) is None:
            info = projects.inspect(path)
            if needs_setup(info):
                ExistingProjectDialog(self.ctx, info, self).exec()
            self.ctx.projects.add(path)
        else:
            self.status.setText(tr("projects.already_listed"))
        self.refresh(select=str(self.ctx.projects.find(path).path))  # type: ignore[union-attr]

    def open_vscode(self) -> None:
        info = self.selected_info()
        if info is None or not info.exists:
            return
        if vscode.open_folder(info.path):
            self.ctx.projects.touch(info.path)
            self.status.setText(tr("projects.vscode_opening"))
            self.refresh()
            return
        answer = QMessageBox.question(
            self,
            tr("projects.open_vscode"),
            tr("projects.vscode_missing"),
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Open:
            QDesktopServices.openUrl(QUrl(vscode.DOWNLOAD_URL))

    def open_folder(self) -> None:
        info = self.selected_info()
        if info is not None and info.exists:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(info.path)))
            self.ctx.projects.touch(info.path)

    def open_terminal(self) -> None:
        info = self.selected_info()
        if info is None or not info.exists:
            return
        venv = info.venv if info.venv_state == "ok" else None
        if terminal.open_terminal(info.path, venv):
            self.ctx.projects.touch(info.path)
        else:
            self.status.setText(tr("projects.terminal_failed"))

    def show_packages(self) -> None:
        info = self.selected_info()
        if info is not None and info.interpreter is not None:
            self.ctx.show_packages_for.emit(str(info.interpreter))

    def toggle_pin(self) -> None:
        info = self.selected_info()
        if info is None:
            return
        entry = self.ctx.projects.find(info.path)
        if entry is not None:
            self.ctx.projects.set_pinned(info.path, not entry.pinned)
            self.refresh()

    def remove(self) -> None:
        info = self.selected_info()
        if info is None:
            return
        answer = QMessageBox.question(self, tr("projects.remove"), tr("projects.confirm_remove", name=info.name))
        if answer == QMessageBox.StandardButton.Yes:
            self.ctx.projects.remove(info.path)
            self.status.setText(tr("projects.removed", name=info.name))
            self.refresh()

    def move_to_trash(self) -> None:
        info = self.selected_info()
        if info is None or not info.exists:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(tr("projects.trash"))
        box.setText(tr("projects.confirm_trash", name=info.name, path=str(info.path)))
        trash = box.addButton(tr("projects.trash"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not trash:
            return
        if move_to_trash(info.path):
            self.ctx.projects.remove(info.path)
            self.status.setText(tr("projects.trashed", name=info.name))
            self.refresh()
        else:
            QMessageBox.warning(self, tr("projects.trash"), tr("projects.trash_failed", path=str(info.path)))

    def _context_menu(self, pos: QPoint) -> None:
        if self.selected_info() is None:
            return
        menu = QMenu(self)
        for button in (
            self.vscode_btn,
            self.folder_btn,
            self.terminal_btn,
            self.packages_btn,
            None,
            self.pin_btn,
            self.remove_btn,
            self.trash_btn,
        ):
            if button is None:
                menu.addSeparator()
                continue
            action = menu.addAction(button.text())
            action.setEnabled(button.isEnabled())
            action.triggered.connect(button.click)
        menu.exec(self.table.viewport().mapToGlobal(pos))
