from __future__ import annotations

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pyvot import __version__
from pyvot.core.paths import data_dir
from pyvot.core.projects import default_projects_root
from pyvot.i18n import tr
from pyvot.ui.context import AppContext
from pyvot.ui.widgets import muted, page_title


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    backend_changed = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        s = ctx.settings

        self.language = QComboBox()
        for code, key in (("auto", "settings.lang_auto"), ("tr", "settings.lang_tr"), ("en", "settings.lang_en")):
            self.language.addItem(tr(key), code)
        self.language.setCurrentIndex(max(0, self.language.findData(s.language)))
        self.restart_note = muted(tr("settings.restart_note"))
        self.restart_note.setVisible(False)

        self.theme = QComboBox()
        for code, key in (("system", "settings.theme_system"), ("light", "settings.theme_light"), ("dark", "settings.theme_dark")):
            self.theme.addItem(tr(key), code)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.theme)))

        self.backend = QComboBox()
        for code, key in (("auto", "settings.backend_auto"), ("uv", "settings.backend_uv"), ("pip", "settings.backend_pip")):
            self.backend.addItem(tr(key), code)
        self.backend.setCurrentIndex(max(0, self.backend.findData(s.backend)))

        self.uv_path = QLineEdit(s.uv_path)
        self.uv_path.setPlaceholderText(tr("settings.uv_auto"))
        browse = QPushButton(tr("action.browse"))
        uv_row = QHBoxLayout()
        uv_row.addWidget(self.uv_path, 1)
        uv_row.addWidget(browse)
        self.uv_status = muted()

        self.projects_root = QLineEdit(s.projects_root)
        self.projects_root.setPlaceholderText(str(default_projects_root()))
        browse_root = QPushButton(tr("action.browse"))
        root_row = QHBoxLayout()
        root_row.addWidget(self.projects_root, 1)
        root_row.addWidget(browse_root)

        appearance = QGroupBox(tr("settings.appearance"))
        form = QFormLayout(appearance)
        form.addRow(tr("settings.language"), self.language)
        form.addRow("", self.restart_note)
        form.addRow(tr("settings.theme"), self.theme)

        tools = QGroupBox(tr("settings.tools"))
        form2 = QFormLayout(tools)
        form2.addRow(tr("settings.backend"), self.backend)
        form2.addRow(tr("settings.uv_path"), uv_row)
        form2.addRow("", self.uv_status)
        form2.addRow(tr("settings.projects_root"), root_row)

        about = QGroupBox(tr("settings.about"))
        about_layout = QVBoxLayout(about)
        about_layout.addWidget(muted(tr("settings.version", version=__version__)))
        open_data = QPushButton(tr("settings.open_data"))
        about_layout.addWidget(open_data)

        layout = QVBoxLayout(self)
        layout.addWidget(page_title(tr("nav.settings")))
        layout.addWidget(appearance)
        layout.addWidget(tools)
        layout.addWidget(about)
        layout.addStretch(1)

        self.language.currentIndexChanged.connect(self._language_changed)
        self.theme.currentIndexChanged.connect(self._theme_changed)
        self.backend.currentIndexChanged.connect(self._backend_changed)
        self.uv_path.editingFinished.connect(self._uv_path_changed)
        browse.clicked.connect(self._browse_uv)
        self.projects_root.editingFinished.connect(self._projects_root_changed)
        browse_root.clicked.connect(self._browse_projects_root)
        open_data.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))
        self._update_uv_status()

    def _save(self) -> None:
        self.ctx.settings.save()

    def _language_changed(self) -> None:
        self.ctx.settings.language = self.language.currentData()
        self.restart_note.setVisible(True)
        self._save()

    def _theme_changed(self) -> None:
        self.ctx.settings.theme = self.theme.currentData()
        self._save()
        self.theme_changed.emit(self.ctx.settings.theme)

    def _backend_changed(self) -> None:
        self.ctx.settings.backend = self.backend.currentData()
        self._save()
        self.backend_changed.emit()

    def _uv_path_changed(self) -> None:
        value = self.uv_path.text().strip()
        if value == self.ctx.settings.uv_path:
            return
        self.ctx.settings.uv_path = value
        self._save()
        self.ctx.refresh_uv()
        self._update_uv_status()
        self.backend_changed.emit()

    def _browse_uv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("settings.uv_path"))
        if path:
            self.uv_path.setText(path)
            self._uv_path_changed()

    def _projects_root_changed(self) -> None:
        self.ctx.settings.projects_root = self.projects_root.text().strip()
        self._save()

    def _browse_projects_root(self) -> None:
        start = self.projects_root.text() or str(default_projects_root())
        folder = QFileDialog.getExistingDirectory(self, tr("settings.projects_root"), start)
        if folder:
            self.projects_root.setText(folder)
            self._projects_root_changed()

    def _update_uv_status(self) -> None:
        if self.ctx.uv:
            self.uv_status.setText(tr("settings.uv_found", version=self.ctx.uv_version or "?", path=self.ctx.uv))
        else:
            self.uv_status.setText(tr("settings.uv_missing"))
