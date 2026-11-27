"""Proje penceresi: dosya ağacı, Monaco editörü, önizleme, konsol, sorunlar."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QDir,
    QFileSystemWatcher,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileSystemModel,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTabBar,
    QTabWidget,
    QToolBar,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pyvot.core import files, launch, ruff, terminal, vscode
from pyvot.core.projects import inspect
from pyvot.i18n import tr
try:  # QtWebEngine yoksa proje penceresi editörsüz açılır, çökmez.
    from pyvot.ui.code_editor import MonacoEditor, monaco_available

    WEBENGINE_ERROR = ""
except ImportError as exc:  # pragma: no cover - paket eksikse
    MonacoEditor = None  # type: ignore[assignment,misc]
    WEBENGINE_ERROR = str(exc)

    def monaco_available() -> bool:
        return False
from pyvot.ui.context import AppContext
from pyvot.ui.preview import PreviewBase, UnsupportedPreview, preview_for
from pyvot.ui.run_console import RunConsole
from pyvot.ui.theme import is_dark
from pyvot.ui.workers import run_in_background

PREVIEW_SUFFIX = "::preview"


@dataclass
class Tab:
    key: str
    path: Path
    kind: str  # editor | preview
    widget: QWidget | None = None  # önizleme için
    dirty: bool = False
    eol: str = "\n"
    disk_text: str = ""  # son okunan/yazılan içerik (dış değişikliği ayırt etmek için)
    deleted: bool = False


# --- dosya ağacı -------------------------------------------------------------------------


class _HideFilter(QSortFilterProxyModel):
    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:  # noqa: N802
        index = self.sourceModel().index(row, 0, parent)
        return not files.is_hidden(self.sourceModel().fileName(index))

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        left_dir, right_dir = model.isDir(left), model.isDir(right)
        if left_dir != right_dir:
            return left_dir  # klasörler önce
        return model.fileName(left).lower() < model.fileName(right).lower()


class FileTree(QTreeView):
    def __init__(self, root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.root = root
        self.fs = QFileSystemModel(self)
        self.fs.setRootPath(str(root))
        self.fs.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden)
        self.fs.setReadOnly(True)
        self.proxy = _HideFilter(self)
        self.proxy.setSourceModel(self.fs)
        self.proxy.setDynamicSortFilter(True)
        self.setModel(self.proxy)
        self.setRootIndex(self.proxy.mapFromSource(self.fs.index(str(root))))
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        for column in (1, 2, 3):
            self.hideColumn(column)
        self.header().hide()
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def path_at(self, index: QModelIndex) -> Path | None:
        if not index.isValid():
            return None
        return Path(self.fs.filePath(self.proxy.mapToSource(index)))

    def selected_path(self) -> Path | None:
        return self.path_at(self.currentIndex())

    def select_path(self, path: Path) -> None:
        index = self.proxy.mapFromSource(self.fs.index(str(path)))
        if index.isValid():
            self.setCurrentIndex(index)
            self.scrollTo(index)


# --- sorunlar listesi --------------------------------------------------------------------


class ProblemsList(QTreeWidget):
    def __init__(self, root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.root = root
        self.setHeaderLabels([tr("problems.col_problem"), tr("problems.col_location")])
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.by_file: dict[Path, list[ruff.Diagnostic]] = {}

    def set_file(self, path: Path, diagnostics: list[ruff.Diagnostic]) -> None:
        if diagnostics:
            self.by_file[path] = diagnostics
        else:
            self.by_file.pop(path, None)
        self.refresh()

    def set_all(self, diagnostics: list[ruff.Diagnostic]) -> None:
        self.by_file = {}
        for diagnostic in diagnostics:
            self.by_file.setdefault(diagnostic.path, []).append(diagnostic)
        self.refresh()

    def count(self) -> int:
        return sum(len(v) for v in self.by_file.values())

    def refresh(self) -> None:
        self.clear()
        style = self.style()
        icons = {
            "error": style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical),
            "warning": style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning),
        }
        for path in sorted(self.by_file, key=lambda p: str(p).lower()):
            items = self.by_file[path]
            try:
                label = str(path.relative_to(self.root))
            except ValueError:
                label = str(path)
            parent = QTreeWidgetItem([f"{label} ({len(items)})", ""])
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            self.addTopLevelItem(parent)
            for diagnostic in sorted(items, key=lambda d: (d.line, d.column)):
                text = f"{diagnostic.code}  {diagnostic.message}" if diagnostic.code else diagnostic.message
                child = QTreeWidgetItem([text, f"{diagnostic.line}:{diagnostic.column}"])
                child.setIcon(0, icons[diagnostic.severity])
                child.setData(0, Qt.ItemDataRole.UserRole, diagnostic)
                parent.addChild(child)
            parent.setExpanded(True)


# --- pencere ------------------------------------------------------------------------------


class WorkspaceWindow(QMainWindow):
    def __init__(self, ctx: AppContext, project: Path) -> None:
        super().__init__()
        self.ctx = ctx
        self.project = project
        self.tabs: dict[str, Tab] = {}
        self.ruff = ruff.find_ruff()
        self.sessions = files.SessionStore()
        self._last_command: dict[str, float] = {}
        self._closing_ok = False
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"{project.name} — Pyvot")
        self.resize(1280, 820)

        # Merkez: sekmeler + editör/önizleme yığını
        self.tab_bar = QTabBar()
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDocumentMode(True)
        self.stack = QStackedWidget()
        self.editor: MonacoEditor | None = None
        if MonacoEditor is not None and monaco_available():
            self.editor = MonacoEditor()
            self.stack.addWidget(self.editor)
        else:
            text = tr("workspace.no_monaco")
            if WEBENGINE_ERROR:
                text += f"\n\n({WEBENGINE_ERROR})"
            missing = QLabel(text, alignment=Qt.AlignmentFlag.AlignCenter)
            missing.setWordWrap(True)
            self.stack.addWidget(missing)
        self.welcome = QLabel(tr("workspace.welcome"), alignment=Qt.AlignmentFlag.AlignCenter)
        self.welcome.setWordWrap(True)
        self.stack.addWidget(self.welcome)
        self.stack.setCurrentWidget(self.welcome)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self.tab_bar)
        center_layout.addWidget(self.stack, 1)

        # Alt panel
        self.console = RunConsole(project)
        self.problems = ProblemsList(project)
        self.bottom = QTabWidget()
        self.bottom.addTab(self.console, tr("workspace.console"))
        self.bottom.addTab(self.problems, tr("workspace.problems"))
        self.bottom.setDocumentMode(True)

        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(center)
        right.addWidget(self.bottom)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 1)
        right.setSizes([560, 200])

        self.tree = FileTree(project)
        main = QSplitter(Qt.Orientation.Horizontal)
        main.addWidget(self.tree)
        main.addWidget(right)
        main.setStretchFactor(1, 1)
        main.setSizes([240, 1040])
        self.setCentralWidget(main)

        self.cursor_label = QLabel()
        self.language_label = QLabel()
        self.ruff_label = QLabel()
        status = self.statusBar()
        status.addPermanentWidget(self.ruff_label)
        status.addPermanentWidget(self.language_label)
        status.addPermanentWidget(self.cursor_label)

        self._build_actions()
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._file_changed_on_disk)

        self.tab_bar.currentChanged.connect(self._tab_changed)
        self.tab_bar.tabCloseRequested.connect(lambda i: self.close_tab(self._key_at(i)))
        self.tree.activated.connect(self._tree_activated)
        self.tree.doubleClicked.connect(self._tree_activated)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.problems.itemActivated.connect(self._problem_activated)
        self.console.location_clicked.connect(self.open_location)
        self.console.started.connect(self._update_actions)
        self.console.finished.connect(lambda _code: self._update_actions())
        ctx.theme_changed.connect(self._apply_theme)
        if self.editor is not None:
            self.editor.dirty_changed.connect(self._dirty_changed)
            self.editor.cursor_moved.connect(
                lambda line, col: self.cursor_label.setText(tr("workspace.cursor", line=line, column=col))
            )
            self.editor.command.connect(self.handle_command)
            self.editor.ready.connect(self._editor_ready)

        self._apply_theme()
        self._restore_session()
        self.check_project()
        self._update_actions()

    # --- eylemler ve araç çubuğu -------------------------------------------------------

    def _action(self, key: str, slot: Callable[[], None], shortcut: str | None = None, icon=None) -> QAction:  # noqa: ANN001
        action = QAction(tr(key), self)
        if icon is not None:
            action.setIcon(self.style().standardIcon(icon))
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.setToolTip(f"{tr(key)} ({shortcut})")
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _build_actions(self) -> None:
        sp = QStyle.StandardPixmap
        self.run_action = self._action("workspace.run", lambda: self.handle_command("run"), "F5", sp.SP_MediaPlay)
        self.run_file_action = self._action("workspace.run_file", lambda: self.handle_command("run_file"), "Ctrl+F5")
        self.stop_action = self._action("workspace.stop", self.console.stop, "Shift+F5", sp.SP_MediaStop)
        self.save_action = self._action("workspace.save", lambda: self.handle_command("save"), "Ctrl+S", sp.SP_DialogSaveButton)
        self.save_all_action = self._action("workspace.save_all", lambda: self.handle_command("save_all"), "Ctrl+Shift+S")
        self.format_action = self._action("workspace.format", lambda: self.handle_command("format"), "Shift+Alt+F")
        self.preview_action = self._action("workspace.preview", self.preview_current)
        self.close_action = self._action("workspace.close_tab", lambda: self.handle_command("close"), "Ctrl+W")
        self.vscode_action = self._action("projects.open_vscode", self.open_vscode)
        self.terminal_action = self._action("projects.open_terminal", self.open_terminal)
        self.folder_action = self._action("projects.open_folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project))))

        bar = QToolBar(tr("workspace.toolbar"))
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for action in (self.run_action, self.run_file_action, self.stop_action):
            bar.addAction(action)
        bar.addSeparator()
        for action in (self.save_action, self.format_action, self.preview_action):
            bar.addAction(action)
        bar.addSeparator()
        for action in (self.vscode_action, self.terminal_action, self.folder_action):
            bar.addAction(action)
        self.addToolBar(bar)

    def handle_command(self, name: str) -> None:
        # Kısayol hem Qt'ye hem Monaco'ya gidebilir; aynı komut iki kez çalışmasın.
        now = time.monotonic()
        if now - self._last_command.get(name, 0) < 0.3:
            return
        self._last_command[name] = now
        if name == "save":
            tab = self.current_tab()
            if tab is not None:
                self.save(tab)
        elif name == "save_all":
            self.save_all()
        elif name == "close":
            tab = self.current_tab()
            if tab is not None:
                self.close_tab(tab.key)
        elif name == "run":
            self.save_all(then=self.run_project)
        elif name == "run_file":
            self.save_all(then=self.run_current_file)
        elif name == "format":
            self.format_current()

    def _update_actions(self) -> None:
        tab = self.current_tab()
        is_editor = tab is not None and tab.kind == "editor"
        running = self.console.running
        self.run_action.setEnabled(not running)
        self.run_file_action.setEnabled(not running and is_editor and tab.path.suffix in (".py", ".pyw"))
        self.stop_action.setEnabled(running)
        self.save_action.setEnabled(is_editor)
        self.format_action.setEnabled(is_editor)
        self.preview_action.setEnabled(tab is not None and tab.path.suffix.lower() in (".md", ".markdown"))
        self.close_action.setEnabled(tab is not None)

    # --- tema ve ayarlar ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        if self.editor is not None:
            self.editor.set_theme(is_dark(QApplication.instance(), self.ctx.settings.theme))  # type: ignore[arg-type]

    def _editor_ready(self) -> None:
        assert self.editor is not None
        self.editor.set_options(self.editor_options())

    def vscode_settings(self) -> dict:
        path = self.project / ".vscode" / "settings.json"
        try:
            data = json.loads(launch.strip_jsonc(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def editor_options(self) -> dict:
        settings = self.vscode_settings()
        options: dict = {"fontSize": self.ctx.settings.editor_font_size}
        for key, option in (("editor.tabSize", "tabSize"), ("editor.insertSpaces", "insertSpaces"), ("editor.fontSize", "fontSize")):
            if key in settings:
                options[option] = settings[key]
        if "editor.wordWrap" in settings:
            options["wordWrap"] = settings["editor.wordWrap"]
        if isinstance(settings.get("editor.rulers"), list):
            options["rulers"] = settings["editor.rulers"]
        return options

    def format_on_save(self, path: Path) -> bool:
        settings = self.vscode_settings()
        value = bool(settings.get("editor.formatOnSave", False))
        if path.suffix in (".py", ".pyi"):
            python = settings.get("[python]")
            if isinstance(python, dict) and "editor.formatOnSave" in python:
                value = bool(python["editor.formatOnSave"])
        return value

    # --- sekmeler -------------------------------------------------------------------------

    def _key_at(self, index: int) -> str:
        return self.tab_bar.tabData(index) or ""

    def current_tab(self) -> Tab | None:
        index = self.tab_bar.currentIndex()
        return self.tabs.get(self._key_at(index)) if index >= 0 else None

    def _index_of(self, key: str) -> int:
        for index in range(self.tab_bar.count()):
            if self.tab_bar.tabData(index) == key:
                return index
        return -1

    def _add_tab(self, tab: Tab, title: str) -> None:
        self.tabs[tab.key] = tab
        index = self.tab_bar.addTab(title)
        self.tab_bar.setTabData(index, tab.key)
        self.tab_bar.setTabToolTip(index, str(tab.path))
        self.tab_bar.setCurrentIndex(index)

    def _tab_title(self, tab: Tab) -> str:
        title = tab.path.name
        if tab.key.endswith(PREVIEW_SUFFIX):
            title = tr("workspace.preview_title", name=title)
        if tab.deleted:
            title += " " + tr("workspace.deleted")
        return ("● " if tab.dirty else "") + title

    def _refresh_tab_title(self, tab: Tab) -> None:
        index = self._index_of(tab.key)
        if index >= 0:
            self.tab_bar.setTabText(index, self._tab_title(tab))

    def _tab_changed(self, index: int) -> None:
        tab = self.tabs.get(self._key_at(index)) if index >= 0 else None
        if tab is None:
            self.stack.setCurrentWidget(self.welcome)
            self.language_label.setText("")
            self.cursor_label.setText("")
        elif tab.kind == "editor" and self.editor is not None:
            self.stack.setCurrentWidget(self.editor)
            self.editor.activate(tab.path)
            self.language_label.setText(files.language_for(tab.path))
        elif tab.widget is not None:
            self.stack.setCurrentWidget(tab.widget)
            self.language_label.setText("")
            self.cursor_label.setText("")
        if tab is not None:
            self.tree.select_path(tab.path)
        self._update_actions()

    def open_file(self, path: Path, *, as_text: bool = False) -> Tab | None:
        path = path.resolve()
        key = str(path)
        if key in self.tabs:
            self.tab_bar.setCurrentIndex(self._index_of(key))
            return self.tabs[key]
        if not path.is_file():
            return None
        suffix = path.suffix.lower()
        if not as_text and suffix in files.OPEN_AS_PREVIEW:
            return self._open_preview(path, key)
        try:
            text, eol = files.read_text(path)
        except files.NotText as exc:
            widget = UnsupportedPreview(path, exc.reason)
            return self._open_widget(path, key, widget)
        if self.editor is None:
            return None
        tab = Tab(key=key, path=path, kind="editor", eol=eol, disk_text=text)
        self.editor.open(path, text, files.language_for(path), eol)
        self._add_tab(tab, self._tab_title(tab))
        self.watcher.addPath(key)
        diagnostics = self.problems.by_file.get(path)
        if diagnostics:
            self.editor.set_markers(path, [d.to_marker() for d in diagnostics])
        return tab

    def _open_preview(self, path: Path, key: str) -> Tab | None:
        widget = preview_for(path)
        if widget is None:
            return None
        return self._open_widget(path, key, widget)

    def _open_widget(self, path: Path, key: str, widget: QWidget) -> Tab:
        if isinstance(widget, PreviewBase):
            widget.open_in_editor.connect(lambda p: self.open_file(p, as_text=True))
        self.stack.addWidget(widget)
        tab = Tab(key=key, path=path, kind="preview", widget=widget)
        self._add_tab(tab, self._tab_title(tab))
        self.watcher.addPath(str(path))
        return tab

    def preview_current(self) -> None:
        tab = self.current_tab()
        if tab is None:
            return
        key = str(tab.path) + PREVIEW_SUFFIX
        if key in self.tabs:
            self.tab_bar.setCurrentIndex(self._index_of(key))
            self.tabs[key].widget.reload()  # type: ignore[union-attr]
            return
        widget = preview_for(tab.path)
        if widget is not None:
            self._open_widget(tab.path, key, widget)

    def close_tab(self, key: str, *, force: bool = False) -> bool:
        tab = self.tabs.get(key)
        if tab is None:
            return True
        if tab.dirty and not force:
            answer = QMessageBox.question(
                self,
                tr("workspace.close_tab"),
                tr("workspace.ask_save", name=tab.path.name),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return False
            if answer == QMessageBox.StandardButton.Save:
                self.save(tab, then=lambda: self.close_tab(key, force=True))
                return False
        index = self._index_of(key)
        if index >= 0:
            self.tab_bar.removeTab(index)
        self.tabs.pop(key, None)
        if tab.kind == "editor" and self.editor is not None:
            self.editor.close_file(tab.path)
        if tab.widget is not None:
            self.stack.removeWidget(tab.widget)
            tab.widget.deleteLater()
        if not any(t.path == tab.path for t in self.tabs.values()):
            self.watcher.removePath(str(tab.path))
        if not self.tabs:
            self.stack.setCurrentWidget(self.welcome)
        return True

    def _dirty_changed(self, path: Path, dirty: bool) -> None:
        tab = self.tabs.get(str(path))
        if tab is not None and tab.dirty != dirty:
            tab.dirty = dirty
            self._refresh_tab_title(tab)

    # --- kaydetme ve biçimlendirme -----------------------------------------------------------

    def save(self, tab: Tab, then: Callable[[], None] | None = None, *, formatted: bool = False) -> None:
        if tab.kind != "editor" or self.editor is None:
            if then:
                then()
            return

        def got(text: str | None, version: int) -> None:
            if text is None:
                return
            if not formatted and self.ruff and tab.path.suffix in (".py", ".pyi") and self.format_on_save(tab.path):
                try:
                    result = ruff.format_text(self.ruff, self.project, tab.path, text)
                except (ruff.FormatError, OSError):
                    result = text  # sözdizimi hatası varsa biçimlendirmeden kaydet
                if result != text:
                    self.editor.set_text(tab.path, result)  # type: ignore[union-attr]
                    self.save(tab, then, formatted=True)
                    return
            try:
                files.write_text(tab.path, text, tab.eol)
            except OSError as exc:
                QMessageBox.warning(self, tr("workspace.save"), tr("workspace.save_failed", path=str(tab.path), error=str(exc)))
                return
            tab.disk_text = text.replace("\r\n", "\n")
            tab.deleted = False
            self.editor.mark_saved(tab.path, version)  # type: ignore[union-attr]
            if str(tab.path) not in self.watcher.files():
                self.watcher.addPath(str(tab.path))
            self.statusBar().showMessage(tr("workspace.saved", name=tab.path.name), 3000)
            self.check_file(tab.path, text)
            if then:
                then()

        self.editor.snapshot(tab.path, got)

    def save_all(self, then: Callable[[], None] | None = None) -> None:
        dirty = [t for t in self.tabs.values() if t.kind == "editor" and t.dirty]

        def next_one() -> None:
            if dirty:
                self.save(dirty.pop(0), then=next_one)
            elif then:
                then()

        next_one()

    def format_current(self) -> None:
        tab = self.current_tab()
        if tab is None or tab.kind != "editor" or self.editor is None:
            return
        if tab.path.suffix not in (".py", ".pyi"):
            self.editor.format_with_monaco()
            return
        if not self.ruff:
            self.statusBar().showMessage(tr("workspace.no_ruff"), 5000)
            return

        def got(text: str | None, _version: int) -> None:
            if text is None:
                return
            try:
                result = ruff.format_text(self.ruff, self.project, tab.path, text)  # type: ignore[arg-type]
            except ruff.FormatError as exc:
                self.statusBar().showMessage(tr("workspace.format_failed", error=str(exc).splitlines()[0]), 8000)
                return
            if result != text:
                self.editor.set_text(tab.path, result)  # type: ignore[union-attr]

        self.editor.snapshot(tab.path, got)

    # --- dış değişiklikler ----------------------------------------------------------------

    def _file_changed_on_disk(self, raw: str) -> None:
        path = Path(raw)
        # Atomik yazmalardan sonra izleme düşer; dosya duruyorsa yeniden ekle.
        QTimer.singleShot(150, lambda: self._recheck(path))

    def _recheck(self, path: Path) -> None:
        if path.exists() and str(path) not in self.watcher.files():
            self.watcher.addPath(str(path))
        for tab in [t for t in self.tabs.values() if t.path == path]:
            if tab.kind == "preview" and isinstance(tab.widget, PreviewBase):
                if path.exists():
                    tab.widget.reload()
                continue
            if not path.exists():
                tab.deleted = True
                self._refresh_tab_title(tab)
                continue
            try:
                text, eol = files.read_text(path)
            except files.NotText:
                continue
            if text == tab.disk_text:
                if tab.deleted:
                    tab.deleted = False
                    self._refresh_tab_title(tab)
                continue  # kendi kaydımız
            if tab.dirty:
                answer = QMessageBox.question(
                    self,
                    tr("workspace.changed_title"),
                    tr("workspace.changed_dirty", name=path.name),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    tab.disk_text = text  # tekrar sorma
                    continue
            tab.disk_text = text
            tab.eol = eol
            tab.deleted = False
            if self.editor is not None:
                self.editor.set_text(path, text, clean=True)
            self._refresh_tab_title(tab)
            self.statusBar().showMessage(tr("workspace.reloaded", name=path.name), 4000)

    # --- çalıştırma -----------------------------------------------------------------------

    def run_project(self) -> None:
        current = self.current_tab()
        try:
            spec = launch.project_spec(self.project, current.path if current and current.kind == "editor" else None)
        except launch.LaunchError:
            QMessageBox.information(self, tr("workspace.run"), tr("workspace.nothing_to_run"))
            return
        self._start(spec)

    def run_current_file(self) -> None:
        tab = self.current_tab()
        if tab is not None and tab.kind == "editor":
            self._start(launch.file_spec(self.project, tab.path))

    def _start(self, spec: launch.RunSpec) -> None:
        info = inspect(self.project)
        if info.venv_state == "broken":
            self.console._append_info(tr("workspace.venv_broken"))
        self.bottom.setCurrentWidget(self.console)
        self.console.run(spec)

    # --- Ruff ----------------------------------------------------------------------------

    def check_project(self) -> None:
        if not self.ruff:
            self.ruff_label.setText(tr("workspace.no_ruff"))
            return
        ruff_path, project = self.ruff, self.project

        def done(diagnostics: list[ruff.Diagnostic]) -> None:
            self.problems.set_all(diagnostics)
            for tab in self.tabs.values():
                if tab.kind == "editor" and self.editor is not None:
                    self.editor.set_markers(tab.path, [d.to_marker() for d in self.problems.by_file.get(tab.path, [])])
            self._update_problem_count()

        run_in_background(ruff.check_project, ruff_path, project, on_done=done, on_error=lambda _e: None)

    def check_file(self, path: Path, text: str) -> None:
        if not self.ruff or path.suffix not in (".py", ".pyi"):
            return

        def done(diagnostics: list[ruff.Diagnostic]) -> None:
            self.problems.set_file(path, diagnostics)
            if self.editor is not None and str(path) in self.tabs:
                self.editor.set_markers(path, [d.to_marker() for d in diagnostics])
            self._update_problem_count()

        run_in_background(ruff.check_text, self.ruff, self.project, path, text, on_done=done, on_error=lambda _e: None)

    def _update_problem_count(self) -> None:
        count = self.problems.count()
        self.bottom.setTabText(1, tr("workspace.problems_count", count=count) if count else tr("workspace.problems"))
        self.ruff_label.setText(tr("workspace.ruff_status", count=count))

    def _problem_activated(self, item: QTreeWidgetItem, _column: int) -> None:
        diagnostic = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(diagnostic, ruff.Diagnostic):
            self.open_location(diagnostic.path, diagnostic.line, diagnostic.column)

    def open_location(self, path: Path, line: int, column: int = 1) -> None:
        tab = self.open_file(path, as_text=True)
        if tab is not None and tab.kind == "editor" and self.editor is not None:
            self.editor.reveal(tab.path, line, column)

    # --- dosya ağacı işlemleri ------------------------------------------------------------

    def _tree_activated(self, index: QModelIndex) -> None:
        path = self.tree.path_at(index)
        if path is not None and path.is_file():
            self.open_file(path)

    def _tree_menu(self, pos) -> None:  # noqa: ANN001
        path = self.tree.path_at(self.tree.indexAt(pos))
        folder = path if path is not None and path.is_dir() else (path.parent if path else self.project)
        menu = QMenu(self)
        menu.addAction(tr("tree.new_file"), lambda: self.new_file(folder))
        menu.addAction(tr("tree.new_folder"), lambda: self.new_folder(folder))
        if path is not None:
            menu.addSeparator()
            if path.is_file():
                menu.addAction(tr("tree.open"), lambda: self.open_file(path))
                menu.addAction(tr("tree.open_as_text"), lambda: self.open_file(path, as_text=True))
            menu.addAction(tr("tree.rename"), lambda: self.rename(path))
            menu.addAction(tr("projects.trash"), lambda: self.trash(path))
            menu.addSeparator()
            menu.addAction(tr("tree.copy_path"), lambda: QGuiApplication.clipboard().setText(str(path)))
            menu.addAction(tr("tree.reveal"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))))
            if path.is_file() and path.suffix in (".py", ".pyw"):
                menu.addAction(tr("workspace.run_file"), lambda: (self.open_file(path), self.handle_command("run_file")))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _ask_name(self, title: str, label: str, default: str = "") -> str | None:
        from pyvot.core.projects import validate_name

        name, ok = QInputDialog.getText(self, title, label, text=default)
        if not ok or not name:
            return None
        error = validate_name(name)
        if error:
            QMessageBox.warning(self, title, tr(error))
            return None
        return name

    def new_file(self, folder: Path) -> None:
        name = self._ask_name(tr("tree.new_file"), tr("tree.file_name"), "yeni.py")
        if not name:
            return
        path = folder / name
        if path.exists():
            QMessageBox.warning(self, tr("tree.new_file"), tr("tree.exists", name=name))
            return
        try:
            path.write_text("", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, tr("tree.new_file"), str(exc))
            return
        self.open_file(path)

    def new_folder(self, folder: Path) -> None:
        name = self._ask_name(tr("tree.new_folder"), tr("tree.folder_name"))
        if not name:
            return
        try:
            (folder / name).mkdir()
        except OSError as exc:
            QMessageBox.warning(self, tr("tree.new_folder"), str(exc))

    def rename(self, path: Path) -> None:
        name = self._ask_name(tr("tree.rename"), tr("tree.new_name"), path.name)
        if not name or name == path.name:
            return
        target = path.with_name(name)
        if target.exists():
            QMessageBox.warning(self, tr("tree.rename"), tr("tree.exists", name=name))
            return
        affected = [t for t in self.tabs.values() if t.path == path or path in t.path.parents]
        if any(t.dirty for t in affected):
            QMessageBox.warning(self, tr("tree.rename"), tr("tree.save_first"))
            return
        reopen = [(t.path, t.key == self.current_tab().key if self.current_tab() else False) for t in affected]
        for tab in affected:
            self.close_tab(tab.key, force=True)
        try:
            path.rename(target)
        except OSError as exc:
            QMessageBox.warning(self, tr("tree.rename"), str(exc))
            return
        for old, _was_current in reopen:
            self.open_file(target / old.relative_to(path) if old != path else target)

    def trash(self, path: Path) -> None:
        from pyvot.ui.projects_page import move_to_trash

        answer = QMessageBox.question(self, tr("projects.trash"), tr("tree.confirm_trash", name=path.name))
        if answer != QMessageBox.StandardButton.Yes:
            return
        for tab in [t for t in self.tabs.values() if t.path == path or path in t.path.parents]:
            self.close_tab(tab.key, force=True)
        if not move_to_trash(path):
            QMessageBox.warning(self, tr("projects.trash"), tr("projects.trash_failed", path=str(path)))

    # --- dış araçlar --------------------------------------------------------------------

    def open_vscode(self) -> None:
        if not vscode.open_folder(self.project):
            QMessageBox.information(self, tr("projects.open_vscode"), tr("projects.vscode_missing_short"))

    def open_terminal(self) -> None:
        info = inspect(self.project)
        terminal.open_terminal(self.project, info.venv if info.venv_state == "ok" else None)

    # --- oturum ve kapanış -----------------------------------------------------------------

    def _restore_session(self) -> None:
        session = self.sessions.load(self.project)
        if session.geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(session.geometry.encode()))
            except (ValueError, TypeError):
                pass
        for raw in session.open_files:
            path = Path(raw)
            if path.is_file() and self.project in path.parents:
                self.open_file(path)
        if session.active and session.active in self.tabs:
            self.tab_bar.setCurrentIndex(self._index_of(session.active))
        if not self.tabs:
            for candidate in ("main.py", "README.md"):
                if (self.project / candidate).is_file():
                    self.open_file(self.project / candidate)
                    break

    def _save_session(self) -> None:
        keys = [self._key_at(i) for i in range(self.tab_bar.count())]
        files_open = [k for k in keys if not k.endswith(PREVIEW_SUFFIX)]
        current = self.current_tab()
        session = files.Session(
            open_files=files_open,
            active=current.key if current and not current.key.endswith(PREVIEW_SUFFIX) else "",
            geometry=bytes(self.saveGeometry().toBase64().data()).decode(),
        )
        try:
            self.sessions.save(self.project, session)
        except OSError:
            pass

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        dirty = [t for t in self.tabs.values() if t.dirty]
        if dirty and not self._closing_ok:
            names = ", ".join(t.path.name for t in dirty)
            answer = QMessageBox.question(
                self,
                tr("workspace.close_window"),
                tr("workspace.ask_save_all", names=names),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Save:
                event.ignore()
                self.save_all(then=self._close_after_save)
                return
        if self.console.running:
            self.console.stop()
        self._save_session()
        super().closeEvent(event)

    def _close_after_save(self) -> None:
        self._closing_ok = True
        self.close()
