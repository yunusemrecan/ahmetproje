from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStackedWidget,
    QStyle,
    QWidget,
)

from pyvot import APP_NAME, __version__
from pyvot.i18n import tr
from pyvot.ui.context import AppContext
from pyvot.ui.packages_page import PackagesPage
from pyvot.ui.projects_page import ProjectsPage
from pyvot.ui.pythons_page import PythonsPage
from pyvot.ui.settings_page import SettingsPage
from pyvot.ui.theme import apply_theme


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, icon: QIcon | None = None) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        if icon is not None:
            self.setWindowIcon(icon)
        self.resize(1180, 760)

        self.projects = ProjectsPage(ctx)
        self.pythons = PythonsPage(ctx)
        self.packages = PackagesPage(ctx)
        self.settings = SettingsPage(ctx)

        self.stack = QStackedWidget()
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(200)
        self.sidebar.setIconSize(QSize(20, 20))
        style = self.style()
        for page, key, icon_id in (
            (self.projects, "nav.projects", QStyle.StandardPixmap.SP_DirHomeIcon),
            (self.pythons, "nav.pythons", QStyle.StandardPixmap.SP_ComputerIcon),
            (self.packages, "nav.packages", QStyle.StandardPixmap.SP_DirIcon),
            (self.settings, "nav.settings", QStyle.StandardPixmap.SP_FileDialogDetailedView),
        ):
            self.stack.addWidget(page)
            QListWidgetItem(style.standardIcon(icon_id), tr(key), self.sidebar)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumWidth(140)
        self.busy.setMaximumHeight(14)
        self.busy.setTextVisible(False)
        self.busy.setVisible(False)
        self.statusBar().addPermanentWidget(self.busy)

        help_menu = self.menuBar().addMenu(tr("menu.help"))
        about = QAction(tr("menu.about"), self)
        about.triggered.connect(self.show_about)
        help_menu.addAction(about)

        self.sidebar.currentRowChanged.connect(self._page_changed)
        ctx.busy_changed.connect(self.busy.setVisible)
        ctx.show_packages_for.connect(lambda _exe: self.show_page(self.packages))
        self.settings.theme_changed.connect(self._apply_theme)
        self.settings.backend_changed.connect(self.packages.settings_changed)
        self._follow_system_theme()

        self.sidebar.setCurrentRow(0)
        if not ctx.uv:
            self.statusBar().showMessage(tr("status.no_uv"), 15000)
        ctx.discover()

    def show_page(self, page: QWidget) -> None:
        self.sidebar.setCurrentRow(self.stack.indexOf(page))

    def _page_changed(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        if self.stack.currentWidget() is self.packages:
            self.packages.page_shown()

    def _apply_theme(self, mode: str) -> None:
        apply_theme(QApplication.instance(), mode)  # type: ignore[arg-type]

    def _follow_system_theme(self) -> None:
        hints = QApplication.styleHints()
        signal = getattr(hints, "colorSchemeChanged", None)
        if signal is not None:
            signal.connect(lambda _scheme: self.ctx.settings.theme == "system" and self._apply_theme("system"))

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            tr("menu.about"),
            f"<h3>{APP_NAME} {__version__}</h3><p>{tr('about.text')}</p>",
        )

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802
        # Ctrl+1..4 ile sayfalar arasında geçiş.
        last = Qt.Key.Key_1 + self.stack.count() - 1
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_1 <= event.key() <= last:
            self.sidebar.setCurrentRow(event.key() - Qt.Key.Key_1)
            return
        super().keyPressEvent(event)
