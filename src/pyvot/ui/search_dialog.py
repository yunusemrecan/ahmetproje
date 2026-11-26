"""PyPI'de paket arama penceresi."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from pyvot.core import pypi
from pyvot.i18n import tr
from pyvot.ui import info_html
from pyvot.ui.context import AppContext
from pyvot.ui.widgets import muted
from pyvot.ui.workers import run_in_background


class SearchDialog(QDialog):
    def __init__(self, ctx: AppContext, query: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.chosen: str | None = None
        self._search_token = 0
        self._info_token = 0
        self._info_cache: dict[str, pypi.PackageInfo | None] = {}
        self.setWindowTitle(tr("search.title"))
        self.resize(860, 560)

        self.query = QLineEdit(query)
        self.query.setPlaceholderText(tr("search.placeholder"))
        self.query.setClearButtonEnabled(True)
        self.results = QListWidget()
        self.info = QTextBrowser()
        self.info.setOpenExternalLinks(True)
        self.status = muted()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.results)
        splitter.addWidget(self.info)
        splitter.setSizes([300, 560])

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.install_btn = self.buttons.addButton(tr("action.install"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.install_btn.setEnabled(False)

        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(self.query)
        layout.addWidget(splitter, 1)
        layout.addLayout(bottom)

        self._debounce = QTimer(self, singleShot=True, interval=300)
        self._debounce.timeout.connect(self.search)
        self._info_timer = QTimer(self, singleShot=True, interval=200)
        self._info_timer.timeout.connect(self.load_info)
        self.query.textChanged.connect(lambda _t: self._debounce.start())
        self.query.returnPressed.connect(self.search)
        self.results.currentItemChanged.connect(lambda *_: self._info_timer.start())
        self.results.itemDoubleClicked.connect(lambda _i: self.accept())
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        self.ensure_index()
        if query:
            self.search()

    # --- dizin -------------------------------------------------------------------

    def ensure_index(self) -> None:
        index = self.ctx.pypi_index
        if index.loaded:
            return
        self.status.setText(tr("search.index_cached") if index.cache_is_fresh() else tr("search.index_downloading"))
        self.ctx.push_busy()

        def done(_result: object) -> None:
            self.ctx.pop_busy()
            self.status.setText(tr("search.index_ready", count=f"{len(index.names):,}"))
            if self.query.text().strip():
                self.search()

        def failed(exc: Exception) -> None:
            self.ctx.pop_busy()
            self.status.setText(tr("search.index_failed", error=str(exc)))

        run_in_background(index.load, on_done=done, on_error=failed)

    # --- arama -------------------------------------------------------------------

    def search(self) -> None:
        text = self.query.text().strip()
        self._search_token += 1
        token = self._search_token
        if not text:
            self.results.clear()
            return
        index = self.ctx.pypi_index
        if index.loaded:
            run_in_background(index.search, text, on_done=lambda names: self._show(token, names))
        else:
            # Dizin hazır değilken tam adı doğrudan PyPI'ye sor.
            run_in_background(
                pypi.fetch_info,
                text,
                on_done=lambda info: self._show(token, [info.name] if info else []),
                on_error=lambda _e: self._show(token, []),
            )

    def _show(self, token: int, names: list[str]) -> None:
        if token != self._search_token:
            return
        self.results.clear()
        for name in names:
            QListWidgetItem(name, self.results)
        if names:
            self.results.setCurrentRow(0)
        else:
            self.info.setHtml(info_html.message(tr("search.no_results")))
        self.install_btn.setEnabled(bool(names))

    # --- bilgi -------------------------------------------------------------------

    def load_info(self) -> None:
        item = self.results.currentItem()
        if item is None:
            return
        name = item.text()
        self.install_btn.setEnabled(True)
        if name in self._info_cache:
            self._render(name, self._info_cache[name])
            return
        self._info_token += 1
        token = self._info_token
        self.info.setHtml(info_html.message(tr("info.loading")))

        def done(info: pypi.PackageInfo | None) -> None:
            self._info_cache[name] = info
            if token == self._info_token:
                self._render(name, info)

        def failed(exc: Exception) -> None:
            if token == self._info_token:
                self.info.setHtml(info_html.message(tr("info.failed", error=str(exc))))

        run_in_background(pypi.fetch_info, name, on_done=done, on_error=failed)

    def _render(self, name: str, info: pypi.PackageInfo | None) -> None:
        if info is None:
            self.info.setHtml(info_html.message(tr("info.not_found", name=name)))
        else:
            self.info.setHtml(info_html.render(info))

    def accept(self) -> None:
        item = self.results.currentItem()
        if item is None:
            return
        self.chosen = item.text()
        super().accept()
