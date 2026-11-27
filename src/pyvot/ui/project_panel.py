"""Projeler sayfasının sağ paneli: özet, bağımlılıklar, işlemler."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pyvot.core import deps, projects
from pyvot.core.packages import validate_specs
from pyvot.i18n import tr
from pyvot.ui.context import AppContext
from pyvot.ui.job import BackgroundJob
from pyvot.ui.python_combo import PythonCombo
from pyvot.ui.search_dialog import SearchDialog
from pyvot.ui.theme import ACCENT
from pyvot.ui.widgets import OutputLog, muted
from pyvot.ui.workers import run_in_background

WARN = "#d9534f"


# --- küçük pencereler ----------------------------------------------------------------


class AddPackageDialog(QDialog):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.specs: list[str] = []
        self.setWindowTitle(tr("deps.add_title"))
        self.resize(520, 160)
        self.spec = QLineEdit()
        self.spec.setPlaceholderText(tr("packages.install_placeholder"))
        search = QPushButton(tr("packages.search_pypi"))
        search.clicked.connect(self._search)
        row = QHBoxLayout()
        row.addWidget(self.spec, 1)
        row.addWidget(search)
        self.dev = QCheckBox(tr("deps.add_dev"))
        self.error = QLabel()
        self.error.setStyleSheet(f"color: {WARN}")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(tr("deps.add"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.dev)
        layout.addWidget(muted(tr("deps.add_dev_hint")))
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def _search(self) -> None:
        dialog = SearchDialog(self.ctx, self.spec.text().strip(), self)
        if dialog.exec() and dialog.chosen:
            self.spec.setText(dialog.chosen)

    def accept(self) -> None:
        try:
            self.specs = validate_specs(self.spec.text())
        except ValueError as exc:
            self.error.setText(tr("packages.invalid_spec", spec=str(exc)))
            return
        if not self.specs:
            self.error.setText(tr("project.err_empty_package"))
            return
        super().accept()


class ChoosePythonDialog(QDialog):
    def __init__(self, ctx: AppContext, title: str, intro: str, prefer: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 170)
        self.combo = PythonCombo(ctx)
        for row in range(self.combo.count()):
            install = self.combo.itemData(row)
            if prefer and install.short_version == ".".join(prefer.split(".")[:2]):
                self.combo.setCurrentIndex(row)
                break
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.combo.count() > 0)
        layout = QVBoxLayout(self)
        layout.addWidget(muted(intro))
        layout.addWidget(self.combo)
        if self.combo.count() == 0:
            layout.addWidget(muted(tr("wizard.no_python")))
        layout.addWidget(buttons)


# --- panel -------------------------------------------------------------------------------


def _bold(text: str = "") -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


class ProjectPanel(QWidget):
    changed = Signal()  # proje dosyaları değişti; liste yenilensin
    busy_changed = Signal(bool)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.info: projects.ProjectInfo | None = None
        self.dependencies: list[deps.Dependency] = []
        self._token = 0
        self._latest_checked = False

        self.job = BackgroundJob(self)
        self.job.line.connect(lambda text: self.log.append_line(text))
        self.job.succeeded.connect(self._job_done)
        self.job.failed.connect(self._job_failed)

        self.title = QLabel()
        font = self.title.font()
        font.setPointSizeF(font.pointSizeF() * 1.35)
        font.setBold(True)
        self.title.setFont(font)
        self.path_label = muted()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.placeholder = muted(tr("panel.select"))

        self.tabs = QTabWidget()
        self.tabs.addTab(self._summary_tab(), tr("panel.tab_summary"))
        self.tabs.addTab(self._deps_tab(), tr("panel.tab_deps"))
        self.tabs.addTab(self._actions_tab(), tr("panel.tab_actions"))

        self.log = OutputLog()
        self.stop_btn = QPushButton(tr("action.stop"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.job.cancel)
        self.clear_btn = QPushButton(tr("action.clear"))
        self.clear_btn.clicked.connect(self.log.clear)
        log_box = QWidget()
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_head = QHBoxLayout()
        log_head.addWidget(_bold(tr("panel.output")))
        log_head.addStretch(1)
        log_head.addWidget(self.clear_btn)
        log_head.addWidget(self.stop_btn)
        log_layout.addLayout(log_head)
        log_layout.addWidget(self.log, 1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.tabs)
        splitter.addWidget(log_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        self.body = splitter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.addWidget(self.title)
        layout.addWidget(self.path_label)
        layout.addWidget(self.placeholder)
        layout.addWidget(self.body, 1)
        self.set_project(None)

    # --- sekmeler -------------------------------------------------------------------

    def _summary_tab(self) -> QWidget:
        page = QWidget()
        self.sum_python = QLabel()
        self.sum_env = QLabel()
        self.sum_sync = QLabel()
        self.sum_files = QLabel()
        self.sum_files.setWordWrap(True)
        self.sum_deps = QLabel()
        form = QFormLayout()
        form.addRow(tr("col.python") + ":", self.sum_python)
        form.addRow(tr("col.environment") + ":", self.sum_env)
        form.addRow(tr("panel.sync") + ":", self.sum_sync)
        form.addRow(tr("panel.deps_count") + ":", self.sum_deps)
        form.addRow(tr("panel.files") + ":", self.sum_files)
        self.sum_warning = QLabel()
        self.sum_warning.setWordWrap(True)
        self.sum_warning.setStyleSheet(f"color: {WARN}")
        self.sum_sync_btn = QPushButton(tr("deps.sync"))
        self.sum_repair_btn = QPushButton(tr("panel.repair"))
        self.sum_sync_btn.clicked.connect(self.sync)
        self.sum_repair_btn.clicked.connect(self.repair)
        buttons = QHBoxLayout()
        buttons.addWidget(self.sum_sync_btn)
        buttons.addWidget(self.sum_repair_btn)
        buttons.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addLayout(form)
        layout.addWidget(self.sum_warning)
        layout.addLayout(buttons)
        layout.addStretch(1)
        return page

    def _deps_tab(self) -> QWidget:
        page = QWidget()
        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([tr("col.package"), tr("deps.col_wanted"), tr("col.installed"), tr("col.latest")])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._update_buttons)
        self.deps_note = muted()

        self.add_btn = QPushButton(tr("deps.add_more"))
        self.remove_btn = QPushButton(tr("packages.uninstall"))
        self.check_btn = QPushButton(tr("packages.check_updates"))
        self.upgrade_btn = QPushButton(tr("packages.upgrade_selected"))
        self.upgrade_all_btn = QPushButton(tr("packages.upgrade_all"))
        self.major_btn = QPushButton(tr("deps.major"))
        self.sync_btn = QPushButton(tr("deps.sync"))
        grid = QGridLayout()
        for index, button in enumerate(
            (self.add_btn, self.remove_btn, self.sync_btn, self.check_btn, self.upgrade_btn, self.upgrade_all_btn, self.major_btn)
        ):
            grid.addWidget(button, index // 4, index % 4)
        self.add_btn.clicked.connect(self.add_package)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.check_btn.clicked.connect(self.check_latest)
        self.upgrade_btn.clicked.connect(self.upgrade_selected)
        self.upgrade_all_btn.clicked.connect(self.upgrade_all)
        self.major_btn.clicked.connect(self.upgrade_major)
        self.sync_btn.clicked.connect(self.sync)

        layout = QVBoxLayout(page)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.deps_note)
        layout.addLayout(grid)
        return page

    def _actions_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.repair_btn = QPushButton(tr("panel.repair"))
        self.change_python_btn = QPushButton(tr("panel.change_python"))
        self.convert_btn = QPushButton(tr("panel.convert"))
        self.export_btn = QPushButton(tr("panel.export"))
        for button, hint in (
            (self.repair_btn, "panel.repair_hint"),
            (self.change_python_btn, "panel.change_python_hint"),
            (self.convert_btn, "panel.convert_hint"),
            (self.export_btn, "panel.export_hint"),
        ):
            row = QHBoxLayout()
            button.setMinimumWidth(220)
            row.addWidget(button)
            row.addWidget(muted(tr(hint)), 1)
            layout.addLayout(row)
        layout.addStretch(1)
        self.repair_btn.clicked.connect(self.repair)
        self.change_python_btn.clicked.connect(self.change_python)
        self.convert_btn.clicked.connect(self.convert)
        self.export_btn.clicked.connect(self.export)
        return page

    # --- yükleme -------------------------------------------------------------------

    def set_project(self, path: str | Path | None) -> None:
        if self.job.running:
            return
        if path is not None and self.info is not None and Path(path) == self.info.path:
            return  # aynı proje seçili kaldı
        self._token += 1
        self._latest_checked = False
        if path is None:
            self.info = None
            self.dependencies = []
            self.title.setText("")
            self.path_label.setText("")
            self.placeholder.setVisible(True)
            self.body.setVisible(False)
            return
        self.placeholder.setVisible(False)
        self.body.setVisible(True)
        self.reload(Path(path))

    def reload(self, path: Path | None = None) -> None:
        path = path or (self.info.path if self.info else None)
        if path is None:
            return
        self._token += 1
        token = self._token
        self.info = projects.inspect(path)
        self.title.setText(self.info.name)
        self.path_label.setText(str(path))
        self.dependencies = deps.read_dependencies(path)
        self._fill_summary(sync_state=None)
        self._fill_tree()
        self._update_buttons()
        if not self.info.exists:
            return

        def load() -> tuple[list[deps.Dependency], str]:
            found = deps.with_versions(path, deps.read_dependencies(path), self.ctx.uv)
            return found, deps.sync_state(path, self.ctx.uv)

        def done(result: tuple[list[deps.Dependency], str]) -> None:
            if token != self._token:
                return
            found, state = result
            latest = {d.name: d.latest for d in self.dependencies}
            for dep in found:
                dep.latest = latest.get(dep.name)
            self.dependencies = found
            self._fill_summary(sync_state=state)
            self._fill_tree()

        run_in_background(load, on_done=done)

    def _fill_summary(self, sync_state: str | None) -> None:
        info = self.info
        if info is None:
            return
        self.sum_python.setText(info.python_version or "—")
        if not info.exists:
            env = tr("projects.missing")
        elif info.venv is None:
            env = tr("venv.none")
        else:
            env = f"{tr('venv.' + info.venv_state)} ({info.venv.name})"
        self.sum_env.setText(env)
        self.sum_sync.setText(
            {"ok": tr("sync.ok"), "unsynced": tr("sync.unsynced"), "unknown": "—", None: tr("info.loading")}[sync_state]
        )
        main = sum(d.group == deps.MAIN for d in self.dependencies)
        dev = len(self.dependencies) - main
        self.sum_deps.setText(tr("panel.deps_summary", main=main, dev=dev))
        files = [
            name
            for name, present in (
                ("pyproject.toml", info.has_pyproject),
                ("uv.lock", info.has_lock),
                ("requirements.txt", info.has_requirements),
                ("Git", info.has_git),
                (".vscode", info.has_vscode),
            )
            if present
        ]
        self.sum_files.setText(", ".join(files) or "—")
        warnings = []
        if info.exists and info.venv_state == "broken":
            warnings.append(tr("panel.warn_broken"))
        elif info.exists and info.venv is None:
            warnings.append(tr("panel.warn_no_venv"))
        if sync_state == "unsynced" and info.venv_state == "ok":
            warnings.append(tr("panel.warn_unsynced"))
        if info.exists and not info.has_pyproject and info.has_requirements:
            warnings.append(tr("panel.warn_requirements"))
        self.sum_warning.setText("\n".join(warnings))
        self.sum_sync_btn.setVisible(sync_state == "unsynced" and info.has_pyproject)
        self.sum_repair_btn.setVisible(info.exists and info.venv_state != "ok")

    def _fill_tree(self) -> None:
        selected = {(d.name, d.group) for d in self.selected_dependencies()}
        self.tree.clear()
        bold = QFont()
        bold.setBold(True)
        groups = [(deps.MAIN, "deps.group_main"), (deps.DEV, "deps.group_dev")]
        for group, key in groups:
            rows = [d for d in self.dependencies if d.group == group]
            header = QTreeWidgetItem([tr(key, count=len(rows))])
            header.setFont(0, bold)
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(header)
            header.setFirstColumnSpanned(True)
            for dep in rows:
                latest = dep.latest if dep.outdated else ""
                item = QTreeWidgetItem(["   " + dep.name, dep.constraint, dep.installed or "—", latest])
                item.setData(0, Qt.ItemDataRole.UserRole, dep)
                if latest:
                    item.setFont(3, bold)
                    allowed = dep.latest_allowed()
                    item.setForeground(3, ACCENT)
                    if allowed is False:
                        item.setToolTip(3, tr("deps.latest_outside", constraint=dep.constraint))
                if dep.installed is None and self.info and self.info.venv_state == "ok":
                    item.setForeground(2, Qt.GlobalColor.red)
                    item.setToolTip(2, tr("deps.not_installed"))
                self.tree.addTopLevelItem(item)
                if (dep.name, dep.group) in selected:
                    item.setSelected(True)
            if not rows:
                empty = QTreeWidgetItem(["   " + tr("deps.none")])
                empty.setFlags(Qt.ItemFlag.ItemIsEnabled)
                empty.setForeground(0, Qt.GlobalColor.gray)
                self.tree.addTopLevelItem(empty)
        if self.info and not self.info.has_pyproject:
            self.deps_note.setText(tr("panel.no_pyproject"))
        elif self._latest_checked:
            count = sum(d.outdated for d in self.dependencies)
            self.deps_note.setText(tr("packages.outdated_count", count=count) if count else tr("packages.all_current"))
        else:
            self.deps_note.setText("")
        self._update_buttons()

    def selected_dependencies(self) -> list[deps.Dependency]:
        result = []
        for item in self.tree.selectedItems():
            dep = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(dep, deps.Dependency):
                result.append(dep)
        return result

    def _update_buttons(self) -> None:
        info = self.info
        running = self.job.running
        ok = info is not None and info.exists and not running
        has_pyproject = ok and info is not None and info.has_pyproject
        selected = self.selected_dependencies()
        self.add_btn.setEnabled(has_pyproject)
        self.remove_btn.setEnabled(has_pyproject and bool(selected))
        self.sync_btn.setEnabled(has_pyproject)
        self.check_btn.setEnabled(has_pyproject and info is not None and info.venv_state == "ok")
        self.upgrade_btn.setEnabled(has_pyproject and bool(selected))
        self.upgrade_all_btn.setEnabled(has_pyproject and bool(self.dependencies))
        self.major_btn.setEnabled(
            has_pyproject and len(selected) == 1 and selected[0].latest_allowed() is False
        )
        self.major_btn.setToolTip(tr("deps.major_hint"))
        self.repair_btn.setEnabled(ok)
        self.change_python_btn.setEnabled(ok)
        self.convert_btn.setEnabled(ok and info is not None and info.has_requirements)
        self.export_btn.setEnabled(has_pyproject)
        self.sum_sync_btn.setEnabled(not running)
        self.sum_repair_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    # --- iş çalıştırma ------------------------------------------------------------

    def _start(self, fn, *args) -> None:  # noqa: ANN001
        if self.job.running or self.info is None:
            return
        self.log.append_line("")
        self.ctx.push_busy()
        self.job.start(fn, *args)
        self.busy_changed.emit(True)
        self._update_buttons()

    def _job_done(self, _result: object) -> None:
        self.ctx.pop_busy()
        self.busy_changed.emit(False)
        self.reload()
        self.changed.emit()

    def _job_failed(self, exc: Exception) -> None:
        self.ctx.pop_busy()
        self.log.append_line("✗ " + str(exc))
        self.busy_changed.emit(False)
        self.reload()
        self.changed.emit()

    # --- eylemler -----------------------------------------------------------------------

    def add_package(self) -> None:
        dialog = AddPackageDialog(self.ctx, self)
        if dialog.exec() and self.info:
            self._start(deps.add, self.info.path, dialog.specs, dialog.dev.isChecked(), self.ctx.uv)

    def remove_selected(self) -> None:
        selected = self.selected_dependencies()
        if not selected or not self.info:
            return
        names = ", ".join(d.name for d in selected)
        if QMessageBox.question(self, tr("packages.uninstall"), tr("deps.confirm_remove", names=names)) != QMessageBox.StandardButton.Yes:
            return
        main = [d.name for d in selected if d.group == deps.MAIN]
        dev = [d.name for d in selected if d.group == deps.DEV]
        path, uv = self.info.path, self.ctx.uv

        def work(*, log, cancel) -> None:  # noqa: ANN001
            if main:
                deps.remove(path, main, False, uv, log=log, cancel=cancel)
            if dev:
                deps.remove(path, dev, True, uv, log=log, cancel=cancel)

        self._start(work)

    def check_latest(self) -> None:
        if not self.info:
            return
        path, token = self.info.path, self._token
        self.check_btn.setEnabled(False)
        self.deps_note.setText(tr("packages.checking"))
        self.ctx.push_busy()

        def done(found: list[deps.Dependency]) -> None:
            self.ctx.pop_busy()
            if token != self._token:
                return
            self._latest_checked = True
            self.dependencies = found
            self._fill_tree()

        def failed(exc: Exception) -> None:
            self.ctx.pop_busy()
            self.log.append_line(str(exc))
            self.deps_note.setText(tr("packages.check_failed"))
            self._update_buttons()

        current = [deps.Dependency(d.name, d.spec, d.group, d.installed) for d in self.dependencies]
        run_in_background(deps.with_latest, path, current, self.ctx.uv, on_done=done, on_error=failed)

    def upgrade_selected(self) -> None:
        selected = self.selected_dependencies()
        if selected and self.info:
            self._start(deps.upgrade, self.info.path, [d.name for d in selected], self.ctx.uv)

    def upgrade_all(self) -> None:
        if self.info:
            self._start(deps.upgrade, self.info.path, [], self.ctx.uv)

    def upgrade_major(self) -> None:
        selected = self.selected_dependencies()
        if len(selected) != 1 or not self.info:
            return
        dep = selected[0]
        text = tr("deps.confirm_major", name=dep.name, old=dep.constraint or "*", new=f">={dep.latest}")
        if QMessageBox.question(self, tr("deps.major"), text) == QMessageBox.StandardButton.Yes:
            self._start(deps.upgrade_major, self.info.path, dep, self.ctx.uv)

    def sync(self) -> None:
        if self.info:
            self._start(deps.sync, self.info.path, self.ctx.uv)

    def _choose_python(self, title: str, intro: str) -> str | None:
        assert self.info is not None
        dialog = ChoosePythonDialog(self.ctx, title, intro, self.info.python_version, self)
        if not dialog.exec():
            return None
        install = dialog.combo.selected()
        if install is None:
            return None
        required = deps.requires_python(self.info.path) if self.info.has_pyproject else ""
        if not deps.python_satisfies(install.version, required):
            answer = QMessageBox.question(
                self, title, tr("deps.ask_requires_python", version=install.version, required=required)
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None
            deps.set_requires_python(self.info.path, install.version)
            self.log.append_line(tr("deps.requires_updated", version=install.short_version))
        return install.executable

    def repair(self) -> None:
        if not self.info:
            return
        python = self._choose_python(tr("panel.repair"), tr("panel.repair_intro"))
        if python:
            self._start(deps.rebuild_env, self.info.path, python, self.ctx.uv)

    def change_python(self) -> None:
        if not self.info:
            return
        python = self._choose_python(tr("panel.change_python"), tr("panel.change_python_intro"))
        if python:
            self._start(deps.rebuild_env, self.info.path, python, self.ctx.uv)

    def convert(self) -> None:
        if not self.info:
            return
        python = None
        if self.info.venv_state != "ok":
            python = self._choose_python(tr("panel.convert"), tr("panel.repair_intro"))
            if python is None:
                return
        self._start(deps.convert_requirements, self.info.path, python, self.ctx.uv)

    def export(self) -> None:
        if not self.info:
            return
        target = self.info.path / "requirements.txt"
        if target.exists():
            answer = QMessageBox.question(self, tr("panel.export"), tr("deps.confirm_overwrite_requirements"))
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._start(deps.export_requirements, self.info.path, self.ctx.uv)
