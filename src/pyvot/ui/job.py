"""Uzun bir işi arka planda çalıştırıp günlük satırlarını arayüze akıtır."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal

from pyvot.ui.workers import run_in_background


class BackgroundJob(QObject):
    """``fn(*args, log=..., cancel=...)`` biçimindeki bir işi çalıştırır.

    Sinyaller ana iş parçacığına sıraya alınarak gelir.
    """

    line = Signal(str)
    succeeded = Signal(object)
    failed = Signal(object)  # Exception

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cancel_event = threading.Event()
        self.running = False

    def start(self, fn: Callable[..., Any], *args: Any) -> None:
        self.cancel_event.clear()
        self.running = True

        def work() -> Any:
            return fn(*args, log=self.line.emit, cancel=self.cancel_event)

        run_in_background(work, on_done=self._done, on_error=self._error)

    def cancel(self) -> None:
        self.cancel_event.set()

    def _done(self, result: Any) -> None:
        self.running = False
        self.succeeded.emit(result)

    def _error(self, exc: Exception) -> None:
        self.running = False
        self.failed.emit(exc)
