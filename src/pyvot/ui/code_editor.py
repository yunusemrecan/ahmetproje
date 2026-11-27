"""Monaco editörünü (VS Code'un editörü) Qt içinde gösteren bileşen.

Tek bir QWebEngineView içinde tek bir Monaco editörü vardır; her açık dosya
Monaco'da ayrı bir "model"dir. Sekmeler Qt tarafında tutulur.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
EDITOR_HTML = WEB_DIR / "editor.html"


def monaco_available() -> bool:
    return (WEB_DIR / "monaco" / "vs" / "loader.js").is_file()


def uri_for(path: Path) -> str:
    return QUrl.fromLocalFile(str(path)).toString()


class _Bridge(QObject):
    """JavaScript'in çağırdığı nesne (QWebChannel'da "bridge" adıyla)."""

    ready_signal = Signal()
    dirty_signal = Signal(str, bool)
    cursor_signal = Signal(int, int)
    command_signal = Signal(str)

    @Slot()
    def ready(self) -> None:
        self.ready_signal.emit()

    @Slot(str, bool)
    def dirtyChanged(self, uri: str, dirty: bool) -> None:  # noqa: N802 (JS adı)
        self.dirty_signal.emit(uri, dirty)

    @Slot(int, int)
    def cursor(self, line: int, column: int) -> None:
        self.cursor_signal.emit(line, column)

    @Slot(str)
    def command(self, name: str) -> None:
        self.command_signal.emit(name)


class _Page(QWebEnginePage):
    """JavaScript konsol mesajlarını sessizce toplar (hata ayıklama için)."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.console: list[str] = []

    def javaScriptConsoleMessage(self, level, message, line, source) -> None:  # noqa: ANN001, N802
        self.console.append(f"{level.name}: {message} ({source}:{line})")
        del self.console[:-200]


class MonacoEditor(QWidget):
    ready = Signal()
    dirty_changed = Signal(Path, bool)
    cursor_moved = Signal(int, int)
    command = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.is_ready = False
        self._queue: list[str] = []
        self._paths: dict[str, Path] = {}

        self.view = QWebEngineView(self)
        self.page = _Page(self.view)
        self.view.setPage(self.page)
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.view.setContextMenuPolicy(self.view.contextMenuPolicy())

        self.bridge = _Bridge(self)
        self.channel = QWebChannel(self.page)
        self.channel.registerObject("bridge", self.bridge)
        self.page.setWebChannel(self.channel)

        self.bridge.ready_signal.connect(self._on_ready)
        self.bridge.dirty_signal.connect(self._on_dirty)
        self.bridge.cursor_signal.connect(self.cursor_moved)
        self.bridge.command_signal.connect(self.command)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.view.load(QUrl.fromLocalFile(str(EDITOR_HTML)))

    # --- iç işler -------------------------------------------------------------------

    def _on_ready(self) -> None:
        self.is_ready = True
        queued, self._queue = self._queue, []
        for script in queued:
            self.page.runJavaScript(script)
        self.ready.emit()

    def _on_dirty(self, uri: str, dirty: bool) -> None:
        path = self._paths.get(uri)
        if path is not None:
            self.dirty_changed.emit(path, dirty)

    def _call(self, function: str, *args: Any, callback: Callable[[Any], None] | None = None) -> None:
        script = f"window.pyvot.{function}({', '.join(json.dumps(a) for a in args)})"
        if callback is not None:
            # PySide6 dizi/nesne sonuçlarını boş döndürüyor; JSON metni olarak taşıyoruz.
            script = f"JSON.stringify({script} ?? null)"
            raw_callback = callback

            def callback(result: Any) -> None:  # noqa: F811
                try:
                    raw_callback(json.loads(result) if isinstance(result, str) else None)
                except ValueError:
                    raw_callback(None)

        if not self.is_ready:
            if callback is not None:
                # Henüz hazır değil: hazır olunca çalıştır.
                self.ready.connect(lambda: self.page.runJavaScript(script, 0, callback), type=_single_shot())
            else:
                self._queue.append(script)
            return
        if callback is None:
            self.page.runJavaScript(script)
        else:
            self.page.runJavaScript(script, 0, callback)

    # --- dışa açık işlemler -------------------------------------------------------------

    def open(self, path: Path, text: str, language: str, eol: str = "\n") -> None:
        uri = uri_for(path)
        self._paths[uri] = path
        self._call("open", uri, text, language, eol)

    def activate(self, path: Path) -> None:
        self._call("activate", uri_for(path))

    def close_file(self, path: Path) -> None:
        uri = uri_for(path)
        self._paths.pop(uri, None)
        self._call("close", uri)

    def snapshot(self, path: Path, callback: Callable[[str | None, int], None]) -> None:
        def done(result: Any) -> None:
            if isinstance(result, dict):
                callback(result.get("text"), int(result.get("version", 0)))
            else:
                callback(None, 0)

        self._call("snapshot", uri_for(path), callback=done)

    def mark_saved(self, path: Path, version: int) -> None:
        self._call("markSaved", uri_for(path), version)

    def set_text(self, path: Path, text: str, clean: bool = False) -> None:
        self._call("setText", uri_for(path), text, clean)

    def set_markers(self, path: Path, markers: list[dict]) -> None:
        self._call("setMarkers", uri_for(path), markers)

    def reveal(self, path: Path, line: int, column: int = 1) -> None:
        self._call("reveal", uri_for(path), line, column)

    def set_options(self, options: dict) -> None:
        self._call("setOptions", options)

    def set_theme(self, dark: bool) -> None:
        self._call("setTheme", dark)

    def set_empty_text(self, text: str) -> None:
        self._call("setEmptyText", text)

    def format_with_monaco(self) -> None:
        self._call("formatWithMonaco")

    def evaluate(self, function: str, *args: Any, callback: Callable[[Any], None]) -> None:
        """Testler için: window.pyvot.<function>(...) sonucunu döndürür."""
        self._call(function, *args, callback=callback)

    def rename_path(self, old: Path, new: Path) -> None:
        """Dosya yeniden adlandırılınca köprü eşlemesini günceller (model yeniden açılır)."""
        uri = uri_for(old)
        if uri in self._paths:
            self._paths.pop(uri)


def _single_shot():  # noqa: ANN202
    from PySide6.QtCore import Qt

    return Qt.ConnectionType.SingleShotConnection
