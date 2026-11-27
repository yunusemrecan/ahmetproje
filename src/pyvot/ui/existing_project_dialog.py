"""Var olan bir klasörü proje olarak eklerken eksikleri tamamlama penceresi."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from pyvot.core import projects
from pyvot.i18n import tr
from pyvot.ui.context import AppContext
from pyvot.ui.job import BackgroundJob
from pyvot.ui.python_combo import PythonCombo
from pyvot.ui.widgets import OutputLog, muted


def needs_setup(info: projects.ProjectInfo) -> bool:
    return info.venv_state != "ok" or not info.has_vscode


class ExistingProjectDialog(QDialog):
    def __init__(self, ctx: AppContext, info: projects.ProjectInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.info = info
        self.setWindowTitle(tr("existing.title"))
        self.resize(680, 480)

        found = []
        if info.has_pyproject:
            found.append("pyproject.toml")
        if info.has_requirements:
            found.append("requirements.txt")
        if info.venv is not None:
            found.append(f"{info.venv.name} ({tr('venv.' + info.venv_state)})")
        if info.has_git:
            found.append("git")
        if info.has_vscode:
            found.append(".vscode")
        found_text = ", ".join(found) if found else tr("existing.nothing_found")

        self.venv_check = QCheckBox(self._venv_text())
        self.venv_check.setVisible(info.venv_state != "ok")
        self.venv_check.setChecked(info.venv_state != "ok")
        self.python_combo = PythonCombo(ctx)
        self.python_combo.setVisible(info.venv_state != "ok")
        self.vscode_check = QCheckBox(tr("existing.add_vscode"))
        self.vscode_check.setVisible(not info.has_vscode)
        self.vscode_check.setChecked(not info.has_vscode)
        self.log = OutputLog()
        self.log.setVisible(False)
        self.status = QLabel()
        self.status.setWordWrap(True)

        self.run_btn = QPushButton(tr("existing.run"))
        self.run_btn.setDefault(True)
        self.skip_btn = QPushButton(tr("existing.skip"))
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.skip_btn)
        buttons.addWidget(self.run_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>{info.name}</b>"))
        layout.addWidget(muted(str(info.path)))
        layout.addWidget(muted(tr("existing.found", items=found_text)))
        layout.addWidget(self.venv_check)
        layout.addWidget(self.python_combo)
        layout.addWidget(self.vscode_check)
        layout.addWidget(muted(tr("existing.no_overwrite")))
        layout.addWidget(self.log, 1)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

        self.job = BackgroundJob(self)
        self.job.line.connect(self.log.append_line)
        self.job.succeeded.connect(self._done)
        self.job.failed.connect(self._failed)
        self.run_btn.clicked.connect(self.run)
        self.skip_btn.clicked.connect(self.accept)

    def _venv_text(self) -> str:
        if self.info.has_pyproject:
            return tr("existing.venv_sync")
        if self.info.has_requirements:
            return tr("existing.venv_requirements")
        return tr("existing.venv_plain")

    def run(self) -> None:
        if self.run_btn.text() == tr("wizard.close"):
            self.accept()
            return
        create_venv = self.venv_check.isVisible() and self.venv_check.isChecked()
        add_vscode = self.vscode_check.isVisible() and self.vscode_check.isChecked()
        if not create_venv and not add_vscode:
            self.accept()
            return
        python = self.python_combo.selected()
        if create_venv and python is None:
            self.status.setText(tr("wizard.no_python"))
            return
        self.log.setVisible(True)
        self.run_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.status.setText(tr("wizard.working"))
        self.ctx.push_busy()
        self.job.start(
            _setup,
            Path(self.info.path),
            python.executable if python else "",
            self.ctx.uv,
            create_venv,
            add_vscode,
        )

    def _done(self, _result: object) -> None:
        self.ctx.pop_busy()
        self.status.setText(tr("existing.done"))
        self._finish()

    def _failed(self, exc: Exception) -> None:
        self.ctx.pop_busy()
        self.log.append_line(str(exc))
        self.status.setText(tr("existing.failed"))
        self._finish()

    def _finish(self) -> None:
        self.run_btn.setText(tr("wizard.close"))
        self.run_btn.setEnabled(True)
        self.skip_btn.setVisible(False)

    def reject(self) -> None:
        if self.job.running:
            self.job.cancel()
            return
        super().reject()


def _setup(path: Path, python: str, uv: str | None, create_venv: bool, add_vscode: bool, *, log, cancel) -> None:  # noqa: ANN001
    projects.setup_existing(path, python, uv, log, create_venv=create_venv, vscode_files=add_vscode, cancel=cancel)
