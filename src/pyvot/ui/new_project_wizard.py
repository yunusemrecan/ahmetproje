"""Yeni proje sihirbazı: ad/konum → şablon → Python → seçenekler → oluşturma."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pyvot.core import projects, vscode
from pyvot.core.packages import validate_specs
from pyvot.i18n import tr
from pyvot.ui.context import AppContext
from pyvot.ui.job import BackgroundJob
from pyvot.ui.python_combo import PythonCombo
from pyvot.ui.widgets import OutputLog, muted

PAGE_NAME, PAGE_TEMPLATE, PAGE_PYTHON, PAGE_OPTIONS, PAGE_PROGRESS = range(5)


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * 1.3)
    font.setBold(True)
    label.setFont(font)
    return label


class NewProjectWizard(QDialog):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.created: Path | None = None
        self.setWindowTitle(tr("wizard.title"))
        self.resize(760, 560)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._name_page())
        self.stack.addWidget(self._template_page())
        self.stack.addWidget(self._python_page())
        self.stack.addWidget(self._options_page())
        self.stack.addWidget(self._progress_page())

        self.step_label = muted()
        self.back_btn = QPushButton(tr("wizard.back"))
        self.next_btn = QPushButton(tr("wizard.next"))
        self.next_btn.setDefault(True)
        self.cancel_btn = QPushButton(tr("wizard.cancel"))
        self.open_btn = QPushButton(tr("projects.open_vscode"))
        self.open_btn.setVisible(False)

        buttons = QHBoxLayout()
        buttons.addWidget(self.step_label)
        buttons.addStretch(1)
        for button in (self.open_btn, self.cancel_btn, self.back_btn, self.next_btn):
            buttons.addWidget(button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.stack, 1)
        layout.addLayout(buttons)

        self.job = BackgroundJob(self)
        self.job.line.connect(self.log.append_line)
        self.job.succeeded.connect(self._created)
        self.job.failed.connect(self._failed)

        self.back_btn.clicked.connect(self.go_back)
        self.next_btn.clicked.connect(self.go_next)
        self.cancel_btn.clicked.connect(self._cancel_clicked)
        self.open_btn.clicked.connect(self._open_vscode)
        self._show_page(PAGE_NAME)

    # --- sayfalar ------------------------------------------------------------------

    def _name_page(self) -> QWidget:
        page = QWidget()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("wizard.name_placeholder"))
        root = self.ctx.settings.projects_root or str(projects.default_projects_root())
        self.location_edit = QLineEdit(str(Path(root)))
        browse = QPushButton(tr("action.browse"))
        browse.clicked.connect(self._browse_location)
        location_row = QHBoxLayout()
        location_row.addWidget(self.location_edit, 1)
        location_row.addWidget(browse)
        self.target_label = muted()
        self.name_error = QLabel()
        self.name_error.setStyleSheet("color: #d9534f")

        form = QFormLayout()
        form.addRow(tr("wizard.name"), self.name_edit)
        form.addRow(tr("wizard.location"), location_row)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading(tr("wizard.name_title")))
        layout.addWidget(muted(tr("wizard.name_intro")))
        layout.addLayout(form)
        layout.addWidget(self.target_label)
        layout.addWidget(self.name_error)
        layout.addStretch(1)

        self.name_edit.textChanged.connect(self._validate_name_page)
        self.location_edit.textChanged.connect(self._validate_name_page)
        return page

    def _template_page(self) -> QWidget:
        page = QWidget()
        self.template_list = QListWidget()
        self.template_list.setSpacing(4)
        for template in projects.TEMPLATES.values():
            item = QListWidgetItem(f"{tr(template.title_key)}\n{tr(template.description_key)}")
            item.setData(Qt.ItemDataRole.UserRole, template.id)
            item.setToolTip(tr(template.description_key))
            self.template_list.addItem(item)
        self.template_list.setCurrentRow(0)
        self.template_info = muted()
        self.template_list.currentRowChanged.connect(lambda _row: self._update_template_info())

        layout = QVBoxLayout(page)
        layout.addWidget(_heading(tr("wizard.template_title")))
        layout.addWidget(self.template_list, 1)
        layout.addWidget(self.template_info)
        self._update_template_info()
        return page

    def _python_page(self) -> QWidget:
        page = QWidget()
        self.python_combo = PythonCombo(self.ctx)
        self.python_note = muted()
        layout = QVBoxLayout(page)
        layout.addWidget(_heading(tr("wizard.python_title")))
        layout.addWidget(muted(tr("wizard.python_intro")))
        layout.addWidget(self.python_combo)
        layout.addWidget(self.python_note)
        layout.addStretch(1)
        return page

    def _options_page(self) -> QWidget:
        page = QWidget()
        self.venv_check = QCheckBox(tr("wizard.opt_venv"))
        self.packages_check = QCheckBox()
        self.extra_edit = QLineEdit()
        self.extra_edit.setPlaceholderText(tr("wizard.opt_extra_placeholder"))
        self.vscode_check = QCheckBox(tr("wizard.opt_vscode"))
        self.git_check = QCheckBox(tr("wizard.opt_git"))
        self.readme_check = QCheckBox(tr("wizard.opt_readme"))
        for box in (self.venv_check, self.packages_check, self.vscode_check, self.git_check, self.readme_check):
            box.setChecked(True)
        self.options_error = QLabel()
        self.options_error.setStyleSheet("color: #d9534f")
        self.summary = muted()

        extra_row = QFormLayout()
        extra_row.addRow(tr("wizard.opt_extra"), self.extra_edit)

        layout = QVBoxLayout(page)
        layout.addWidget(_heading(tr("wizard.options_title")))
        layout.addWidget(self.venv_check)
        layout.addWidget(self.packages_check)
        layout.addLayout(extra_row)
        layout.addWidget(self.vscode_check)
        layout.addWidget(self.git_check)
        layout.addWidget(self.readme_check)
        layout.addWidget(self.options_error)
        layout.addStretch(1)
        layout.addWidget(self.summary)
        return page

    def _progress_page(self) -> QWidget:
        page = QWidget()
        self.progress_title = _heading(tr("wizard.progress_title"))
        self.log = OutputLog()
        self.progress_status = QLabel()
        self.progress_status.setWordWrap(True)
        layout = QVBoxLayout(page)
        layout.addWidget(self.progress_title)
        layout.addWidget(self.log, 1)
        layout.addWidget(self.progress_status)
        return page

    # --- gezinme ---------------------------------------------------------------------

    def _show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.back_btn.setVisible(index not in (PAGE_NAME, PAGE_PROGRESS))
        self.next_btn.setText(tr("wizard.create") if index == PAGE_OPTIONS else tr("wizard.next"))
        self.next_btn.setVisible(index != PAGE_PROGRESS)
        if index < PAGE_PROGRESS:
            self.step_label.setText(tr("wizard.step", current=index + 1, total=4))
        if index == PAGE_NAME:
            self._validate_name_page()
            self.name_edit.setFocus()
        elif index == PAGE_PYTHON:
            self._prepare_python_page()
        elif index == PAGE_OPTIONS:
            self._prepare_options_page()

    def go_back(self) -> None:
        index = self.stack.currentIndex()
        if 0 < index < PAGE_PROGRESS:
            self._show_page(index - 1)

    def go_next(self) -> None:
        index = self.stack.currentIndex()
        if index == PAGE_NAME and not self._validate_name_page():
            return
        if index == PAGE_PYTHON and self.python_combo.selected() is None:
            return
        if index == PAGE_OPTIONS:
            self.start_creation()
            return
        self._show_page(index + 1)

    # --- doğrulama ------------------------------------------------------------------

    def target(self) -> Path:
        return Path(self.location_edit.text().strip()) / self.name_edit.text()

    def _validate_name_page(self) -> bool:
        name = self.name_edit.text()
        location = self.location_edit.text().strip()
        error = projects.validate_name(name) if name else None
        if error is None and not location:
            error = "project.err_location"
        if error is None and name:
            error = projects.target_problem(self.target())
        self.name_error.setText(tr(error) if error and name else "")
        self.target_label.setText(tr("wizard.will_create", path=str(self.target())) if name else "")
        ok = bool(name) and error is None
        self.next_btn.setEnabled(ok)
        return ok

    def _browse_location(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("wizard.location"), self.location_edit.text())
        if folder:
            self.location_edit.setText(str(Path(folder)))

    def selected_template(self) -> projects.Template:
        item = self.template_list.currentItem()
        template_id = item.data(Qt.ItemDataRole.UserRole) if item else "empty"
        return projects.TEMPLATES[template_id]

    def _update_template_info(self) -> None:
        template = self.selected_template()
        text = tr(template.description_key)
        if template.packages:
            text += "\n" + tr("wizard.template_packages", packages=", ".join(template.packages))
        self.template_info.setText(text)

    def _prepare_python_page(self) -> None:
        self.python_combo.reload()
        if self.python_combo.count() == 0:
            self.python_note.setText(tr("wizard.no_python"))
            self.next_btn.setEnabled(False)
        else:
            self.python_note.setText(tr("wizard.python_note"))
            self.next_btn.setEnabled(True)

    def _prepare_options_page(self) -> None:
        template = self.selected_template()
        packages = ", ".join(template.packages)
        self.packages_check.setText(tr("wizard.opt_packages", packages=packages))
        self.packages_check.setVisible(bool(template.packages))
        has_git = projects.shutil.which("git") is not None
        self.git_check.setEnabled(has_git)
        self.git_check.setToolTip("" if has_git else tr("project.git_missing"))
        if not has_git:
            self.git_check.setChecked(False)
        if not vscode.find_vscode():
            self.vscode_check.setToolTip(tr("wizard.vscode_not_found"))
        python = self.python_combo.selected()
        self.summary.setText(
            tr(
                "wizard.summary",
                path=str(self.target()),
                template=tr(template.title_key),
                python=python.version if python else "?",
            )
        )
        self.options_error.setText("")

    # --- oluşturma ------------------------------------------------------------------

    def start_creation(self) -> None:
        try:
            extra = validate_specs(self.extra_edit.text()) if self.extra_edit.text().strip() else []
        except ValueError as exc:
            self.options_error.setText(tr("packages.invalid_spec", spec=str(exc)))
            return
        python = self.python_combo.selected()
        if python is None:
            return
        parent = Path(self.location_edit.text().strip())
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            fallback = projects.fallback_projects_root()
            if parent == projects.default_projects_root() and fallback != parent:
                fallback.mkdir(parents=True, exist_ok=True)
                parent = fallback
            else:
                self.options_error.setText(tr("wizard.location_unwritable", path=str(parent)))
                return
        project = projects.NewProject(
            name=self.name_edit.text(),
            parent=parent,
            template=self.selected_template().id,
            python=python.executable,
            python_version=python.version,
            create_venv=self.venv_check.isChecked(),
            install_packages=self.packages_check.isChecked(),
            extra_packages=extra,
            vscode_files=self.vscode_check.isChecked(),
            git=self.git_check.isChecked(),
            readme=self.readme_check.isChecked(),
        )
        self._show_page(PAGE_PROGRESS)
        self.step_label.setText("")
        self.progress_status.setText(tr("wizard.working"))
        self.cancel_btn.setText(tr("wizard.cancel"))
        self.ctx.push_busy()
        self.job.start(projects.create, project, self.ctx.uv)

    def _created(self, path: Path) -> None:
        self.ctx.pop_busy()
        self.created = path
        self.ctx.projects.add(path)
        self.progress_title.setText(tr("wizard.done_title"))
        self.progress_status.setText(tr("wizard.done", path=str(path)))
        self.cancel_btn.setText(tr("wizard.close"))
        self.open_btn.setVisible(True)
        self.open_btn.setFocus()

    def _failed(self, exc: Exception) -> None:
        self.ctx.pop_busy()
        self.progress_title.setText(tr("wizard.failed_title"))
        self.log.append_line(str(exc))
        target = self.target()
        if target.exists():
            # Klasör oluştuysa listeye yine de ekle; kullanıcı eksikleri sonra tamamlayabilir.
            self.created = target
            self.ctx.projects.add(target)
            self.progress_status.setText(tr("wizard.failed_kept", path=str(target)))
        else:
            self.progress_status.setText(tr("wizard.failed"))
        self.cancel_btn.setText(tr("wizard.close"))

    def _cancel_clicked(self) -> None:
        if self.job.running:
            self.job.cancel()
            self.progress_status.setText(tr("wizard.cancelling"))
            return
        if self.created is not None:
            self.accept()
        else:
            self.reject()

    def _open_vscode(self) -> None:
        if self.created is None:
            return
        if vscode.open_folder(self.created):
            self.ctx.projects.touch(self.created)
            self.accept()
        else:
            self.progress_status.setText(tr("projects.vscode_missing"))

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        if self.job.running:
            self.job.cancel()
            event.ignore()
            self.progress_status.setText(tr("wizard.cancelling"))
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if self.job.running:
            self.job.cancel()
            return
        if self.created is not None:
            self.accept()
            return
        super().reject()
