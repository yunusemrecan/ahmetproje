from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from pyvot.core import discovery, pypi
from pyvot.core.models import Package, same_path_key
from pyvot.core.packages import PackageManager, validate_specs
from pyvot.i18n import tr
from pyvot.ui import info_html
from pyvot.ui.context import AppContext
from pyvot.ui.search_dialog import SearchDialog
from pyvot.ui.theme import ACCENT
from pyvot.ui.widgets import OutputLog, muted, page_title, quote_cmd
from pyvot.ui.workers import CommandRunner, run_in_background

COLUMNS = ("col.package", "col.installed", "col.latest")


class PackagesPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.python: str | None = None
        self._pending_python: str | None = None  # keşif bitince seçilecek
        self.packages: list[Package] = []
        self.outdated: dict[str, str] | None = None  # None: henüz denetlenmedi
        self._list_token = 0
        self._outdated_token = 0
        self._info_token = 0
        self._info_cache: dict[str, pypi.PackageInfo | None] = {}
        self._after_command_check_outdated = False

        self.runner = CommandRunner(self)
        self.runner.output.connect(lambda text: self.log.append_text(text))
        self.runner.finished.connect(self._command_finished)

        # --- ortam seçimi ---
        self.env_combo = QComboBox()
        self.env_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.env_combo.setMinimumContentsLength(30)
        self.add_env_btn = QPushButton(tr("packages.add_env"))
        self.backend_label = muted()
        env_row = QHBoxLayout()
        env_row.addWidget(QLabel(tr("packages.environment")))
        env_row.addWidget(self.env_combo, 1)
        env_row.addWidget(self.add_env_btn)
        self.system_warning = muted(tr("packages.system_warning"))
        self.system_warning.setVisible(False)

        # --- araç çubuğu ---
        self.refresh_btn = QPushButton(tr("action.refresh"))
        self.check_btn = QPushButton(tr("packages.check_updates"))
        self.upgrade_btn = QPushButton(tr("packages.upgrade_selected"))
        self.upgrade_all_btn = QPushButton(tr("packages.upgrade_all"))
        self.uninstall_btn = QPushButton(tr("packages.uninstall"))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("packages.filter"))
        self.filter.setClearButtonEnabled(True)
        self.filter.setMaximumWidth(260)
        tools = QHBoxLayout()
        for button in (self.refresh_btn, self.check_btn, self.upgrade_btn, self.upgrade_all_btn, self.uninstall_btn):
            tools.addWidget(button)
        tools.addStretch(1)
        tools.addWidget(self.filter)

        # --- kurulum satırı ---
        self.spec = QLineEdit()
        self.spec.setPlaceholderText(tr("packages.install_placeholder"))
        self.install_btn = QPushButton(tr("action.install"))
        self.search_btn = QPushButton(tr("packages.search_pypi"))
        install_row = QHBoxLayout()
        install_row.addWidget(self.spec, 1)
        install_row.addWidget(self.install_btn)
        install_row.addWidget(self.search_btn)

        # --- tablo ve alt sekmeler ---
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(key) for key in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.AscendingOrder)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.info = QTextBrowser()
        self.info.setOpenExternalLinks(True)
        self.info.setHtml(info_html.message(tr("info.select")))
        self.log = OutputLog()
        self.stop_btn = QPushButton(tr("action.stop"))
        self.stop_btn.setEnabled(False)
        self.clear_btn = QPushButton(tr("action.clear"))
        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        log_layout.setContentsMargins(0, 4, 0, 0)
        log_layout.addWidget(self.log, 1)
        log_buttons = QHBoxLayout()
        log_buttons.addStretch(1)
        log_buttons.addWidget(self.clear_btn)
        log_buttons.addWidget(self.stop_btn)
        log_layout.addLayout(log_buttons)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.info, tr("packages.tab_info"))
        self.tabs.addTab(log_page, tr("packages.tab_output"))

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.status = muted()

        layout = QVBoxLayout(self)
        layout.addWidget(page_title(tr("nav.packages")))
        layout.addLayout(env_row)
        layout.addWidget(self.backend_label)
        layout.addWidget(self.system_warning)
        layout.addLayout(tools)
        layout.addLayout(install_row)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.status)

        self._info_timer = QTimer(self, singleShot=True, interval=250)
        self._info_timer.timeout.connect(self.load_info)

        self.env_combo.currentIndexChanged.connect(self._env_changed)
        self.add_env_btn.clicked.connect(self.add_environment)
        self.refresh_btn.clicked.connect(self.load_packages)
        self.check_btn.clicked.connect(self.check_outdated)
        self.upgrade_btn.clicked.connect(self.upgrade_selected)
        self.upgrade_all_btn.clicked.connect(self.upgrade_all)
        self.uninstall_btn.clicked.connect(self.uninstall_selected)
        self.install_btn.clicked.connect(self.install_from_field)
        self.spec.returnPressed.connect(self.install_from_field)
        self.search_btn.clicked.connect(self.open_search)
        self.filter.textChanged.connect(self.apply_filter)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.stop_btn.clicked.connect(self.runner.stop)
        self.clear_btn.clicked.connect(self.log.clear)
        ctx.installs_changed.connect(self.populate_envs)
        ctx.show_packages_for.connect(self.select_python)

        self._update_actions()

    # --- ortamlar ------------------------------------------------------------------

    def populate_envs(self) -> None:
        wanted = self._pending_python or self.python or self.ctx.settings.last_python
        self._pending_python = None
        self.env_combo.blockSignals(True)
        self.env_combo.clear()
        chosen = -1
        for install in self.ctx.installs:
            self.env_combo.addItem(install.label(), install.executable)
            row = self.env_combo.count() - 1
            if wanted and same_path_key(install.executable) == same_path_key(wanted):
                chosen = row
        if chosen < 0:
            for row, install in enumerate(self.ctx.installs):
                if install.first_on_path or install.is_default:
                    chosen = row
                    break
        if chosen < 0 and self.ctx.installs:
            chosen = 0
        self.env_combo.setCurrentIndex(chosen)
        self.env_combo.blockSignals(False)
        self._env_changed(chosen)

    def select_python(self, executable: str) -> None:
        for row in range(self.env_combo.count()):
            if same_path_key(self.env_combo.itemData(row)) == same_path_key(executable):
                self.env_combo.setCurrentIndex(row)
                return

    def _env_changed(self, row: int) -> None:
        executable = self.env_combo.itemData(row) if row >= 0 else None
        if executable is not None and executable == self.python:
            return  # yeniden keşiften sonra aynı ortam seçili kaldı
        self.python = executable
        self.packages = []
        self.outdated = None
        self.table.setRowCount(0)
        self.info.setHtml(info_html.message(tr("info.select")))
        install = self.ctx.find_install(executable) if executable else None
        self.system_warning.setVisible(bool(install and not install.is_venv))
        self._update_backend_label()
        if executable:
            self.ctx.settings.last_python = executable
            self.ctx.settings.save()
            self.load_packages()
        else:
            self.status.setText(tr("packages.no_env"))
        self._update_actions()

    def _update_backend_label(self) -> None:
        if not self.python:
            self.backend_label.setText("")
            return
        manager = self.manager()
        if manager.backend == "uv":
            self.backend_label.setText(tr("packages.backend_uv", version=self.ctx.uv_version or "?"))
        else:
            self.backend_label.setText(tr("packages.backend_pip"))

    def manager(self) -> PackageManager:
        assert self.python
        return self.ctx.package_manager(self.python)

    def add_environment(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("packages.add_env"))
        if not folder:
            return
        python = discovery.interpreter_in_folder(folder)
        if not python:
            QMessageBox.warning(self, tr("packages.add_env"), tr("packages.add_env_none", folder=folder))
            return
        python = os.path.normpath(python)
        self._pending_python = python
        self.ctx.add_python(python)
        self.ctx.discover()

    def settings_changed(self) -> None:
        """Arka uç (uv/pip) değişince listeyi yeniden yükle."""
        self._update_backend_label()
        if self.python:
            self.outdated = None
            self.load_packages()

    # --- liste ---------------------------------------------------------------------

    def load_packages(self) -> None:
        if not self.python:
            return
        self._list_token += 1
        token = self._list_token
        self.status.setText(tr("packages.loading"))
        self.refresh_btn.setEnabled(False)
        self.ctx.push_busy()

        def done(packages: list[Package]) -> None:
            self.ctx.pop_busy()
            if token != self._list_token:
                return
            self.refresh_btn.setEnabled(True)
            self.packages = packages
            self.fill_table()
            if self._after_command_check_outdated:
                self._after_command_check_outdated = False
                self.check_outdated()

        def failed(exc: Exception) -> None:
            self.ctx.pop_busy()
            if token != self._list_token:
                return
            self.refresh_btn.setEnabled(True)
            self.packages = []
            self.fill_table()
            text = tr("packages.no_pip") if str(exc) == "no-pip" else tr("packages.list_failed")
            self.status.setText(text)
            if str(exc) != "no-pip":
                self.log.append_line(str(exc))
                self.tabs.setCurrentIndex(1)

        run_in_background(self.manager().list_packages, on_done=done, on_error=failed)

    def fill_table(self) -> None:
        selected = set(self.selected_names())
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        bold = QFont()
        bold.setBold(True)
        for package in self.packages:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = QTableWidgetItem(package.name)
            name.setData(Qt.ItemDataRole.UserRole, package.name)
            if package.editable_location:
                name.setToolTip(tr("packages.editable", path=package.editable_location))
            latest_text = ""
            if self.outdated is not None:
                latest_text = self.outdated.get(package.name.lower(), "")
            latest = QTableWidgetItem(latest_text)
            if latest_text:
                latest.setFont(bold)
                latest.setForeground(ACCENT)
            for column, item in enumerate((name, QTableWidgetItem(package.version), latest)):
                self.table.setItem(row, column, item)
            if package.name in selected:
                self.table.selectRow(row)
        self.table.setSortingEnabled(True)
        self.apply_filter()
        self._update_status()
        self._update_actions()

    def _update_status(self) -> None:
        text = tr("packages.count", count=len(self.packages))
        if self.outdated is not None:
            text += " · " + (
                tr("packages.outdated_count", count=len(self.outdated)) if self.outdated else tr("packages.all_current")
            )
        self.status.setText(text)

    def apply_filter(self) -> None:
        needle = self.filter.text().strip().lower()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            self.table.setRowHidden(row, bool(needle) and needle not in (item.text().lower() if item else ""))

    def selected_names(self) -> list[str]:
        names = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item is not None and not self.table.isRowHidden(index.row()):
                names.append(item.data(Qt.ItemDataRole.UserRole))
        return names

    def check_outdated(self) -> None:
        if not self.python:
            return
        self._outdated_token += 1
        token = self._outdated_token
        self.check_btn.setEnabled(False)
        self.status.setText(tr("packages.checking"))
        self.ctx.push_busy()

        def done(found: dict[str, str]) -> None:
            self.ctx.pop_busy()
            if token != self._outdated_token:
                return
            self.outdated = found
            self.fill_table()

        def failed(exc: Exception) -> None:
            self.ctx.pop_busy()
            if token != self._outdated_token:
                return
            self._update_actions()
            self.status.setText(tr("packages.check_failed"))
            self.log.append_line(str(exc))
            self.tabs.setCurrentIndex(1)

        run_in_background(self.manager().outdated, on_done=done, on_error=failed)

    # --- komutlar ------------------------------------------------------------------

    def run_command(self, cmd: list[str], check_outdated_after: bool = False) -> None:
        if self.runner.running:
            return
        self.tabs.setCurrentIndex(1)
        self.log.append_line(f"$ {quote_cmd(cmd)}")
        self._after_command_check_outdated = check_outdated_after and self.outdated is not None
        self.ctx.push_busy()
        self.runner.start(cmd)
        self._update_actions()

    def _command_finished(self, code: int) -> None:
        self.ctx.pop_busy()
        self.log.append_line(tr("packages.done") if code == 0 else tr("packages.failed", code=code))
        self._info_cache.clear()
        self._update_actions()
        self.load_packages()

    def install_from_field(self) -> None:
        text = self.spec.text().strip()
        if not text or not self.python:
            return
        try:
            specs = validate_specs(text)
        except ValueError as exc:
            QMessageBox.warning(self, tr("action.install"), tr("packages.invalid_spec", spec=str(exc)))
            return
        self.spec.clear()
        self.run_command(self.manager().install_cmd(specs), check_outdated_after=True)

    def open_search(self) -> None:
        dialog = SearchDialog(self.ctx, self.spec.text().strip(), self)
        if dialog.exec() and dialog.chosen and self.python:
            self.run_command(self.manager().install_cmd([dialog.chosen]), check_outdated_after=True)

    def upgrade_selected(self) -> None:
        names = self.selected_names()
        if names and self.python:
            self.run_command(self.manager().install_cmd(names, upgrade=True), check_outdated_after=True)

    def upgrade_all(self) -> None:
        if not self.outdated or not self.python:
            return
        names = sorted(p.name for p in self.packages if p.name.lower() in self.outdated)
        answer = QMessageBox.question(
            self, tr("packages.upgrade_all"), tr("packages.confirm_upgrade_all", count=len(names), names=", ".join(names))
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.run_command(self.manager().install_cmd(names, upgrade=True), check_outdated_after=True)

    def uninstall_selected(self) -> None:
        names = self.selected_names()
        if not names or not self.python:
            return
        text = tr("packages.confirm_uninstall", count=len(names), names=", ".join(names))
        if {"pip", "setuptools"} & {n.lower() for n in names}:
            text += "\n\n" + tr("packages.confirm_uninstall_core")
        if QMessageBox.question(self, tr("packages.uninstall"), text) == QMessageBox.StandardButton.Yes:
            self.run_command(self.manager().uninstall_cmd(names), check_outdated_after=True)

    # --- bilgi ---------------------------------------------------------------------

    def _selection_changed(self) -> None:
        self._update_actions()
        self._info_timer.start()

    def load_info(self) -> None:
        names = self.selected_names()
        if len(names) != 1:
            if not names:
                self.info.setHtml(info_html.message(tr("info.select")))
            return
        name = names[0]
        installed = next((p.version for p in self.packages if p.name == name), None)
        if name in self._info_cache:
            self._render_info(name, self._info_cache[name], installed)
            return
        self._info_token += 1
        token = self._info_token
        self.info.setHtml(info_html.message(tr("info.loading")))

        def done(info: pypi.PackageInfo | None) -> None:
            self._info_cache[name] = info
            if token == self._info_token:
                self._render_info(name, info, installed)

        def failed(exc: Exception) -> None:
            if token == self._info_token:
                self.info.setHtml(info_html.message(tr("info.failed", error=str(exc))))

        run_in_background(pypi.fetch_info, name, on_done=done, on_error=failed)

    def _render_info(self, name: str, info: pypi.PackageInfo | None, installed: str | None) -> None:
        if info is None:
            self.info.setHtml(info_html.message(tr("info.not_found", name=name)))
        else:
            self.info.setHtml(info_html.render(info, installed))
        if self.tabs.currentIndex() == 1 and not self.runner.running:
            self.tabs.setCurrentIndex(0)

    # --- düğme durumları ----------------------------------------------------------------

    def _update_actions(self) -> None:
        has_env = self.python is not None
        running = self.runner.running
        selected = bool(self.selected_names())
        self.env_combo.setEnabled(not running)
        self.add_env_btn.setEnabled(not running)
        self.check_btn.setEnabled(has_env and not running)
        self.upgrade_btn.setEnabled(has_env and selected and not running)
        self.upgrade_all_btn.setEnabled(has_env and bool(self.outdated) and not running)
        self.uninstall_btn.setEnabled(has_env and selected and not running)
        self.install_btn.setEnabled(has_env and not running)
        self.search_btn.setEnabled(has_env and not running)
        self.spec.setEnabled(has_env and not running)
        self.stop_btn.setEnabled(running)

    def page_shown(self) -> None:
        if self.python is None and self.ctx.installs:
            self.populate_envs()
