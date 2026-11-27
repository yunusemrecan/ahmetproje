"""Arka plan işleri: arayüz donmasın diye.

- ``run_in_background``: bir fonksiyonu iş parçacığı havuzunda çalıştırır,
  sonucu ana iş parçacığına sinyalle getirir.
- ``CommandRunner``: uzun komutları QProcess ile çalıştırıp çıktıyı canlı akıtır.
"""

from __future__ import annotations

import codecs
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QRunnable, QThreadPool, Signal

from pyvot.core import proc

_alive: set[_Task] = set()


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)  # Exception


class _Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], args: tuple, kwargs: dict) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001 - arayüze iletilir
            exc.__pyvot_trace__ = traceback.format_exc()  # type: ignore[attr-defined]
            self._emit(self.signals.failed, exc)
        else:
            self._emit(self.signals.done, result)

    @staticmethod
    def _emit(signal, value: Any) -> None:  # noqa: ANN001
        # Uygulama kapanırken pencere silinmiş olabilir; o zaman sonucu bırak.
        try:
            signal.emit(value)
        except RuntimeError:
            pass


def run_in_background(
    fn: Callable[..., Any],
    *args: Any,
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    **kwargs: Any,
) -> None:
    task = _Task(fn, args, kwargs)

    def finish() -> None:
        _alive.discard(task)

    if on_done:
        task.signals.done.connect(on_done)
    if on_error:
        task.signals.failed.connect(on_error)
    task.signals.done.connect(finish)
    task.signals.failed.connect(finish)
    _alive.add(task)
    QThreadPool.globalInstance().start(task)


class CommandRunner(QObject):
    """Tek seferde bir komut çalıştırır; stdout ve stderr birleşik akar."""

    output = Signal(str)
    started = Signal(list)
    finished = Signal(int)  # çıkış kodu; başlatılamazsa -1

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    @property
    def running(self) -> bool:
        return self._process is not None

    def start(self, cmd: list[str], cwd: str | None = None) -> bool:
        if self._process is not None:
            return False
        process = QProcess(self)
        env = QProcessEnvironment()
        for key, value in proc.child_env().items():
            env.insert(key, value)
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        if cwd:
            process.setWorkingDirectory(cwd)
        process.readyReadStandardOutput.connect(self._read)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        self._decoder.reset()
        self._process = process
        self.started.emit(cmd)
        process.start(cmd[0], cmd[1:])
        return True

    def stop(self) -> None:
        if self._process is not None:
            self._process.kill()

    def _read(self) -> None:
        if self._process is not None:
            data = bytes(self._process.readAllStandardOutput().data())
            text = self._decoder.decode(data)
            if text:
                self.output.emit(text.replace("\r\n", "\n"))

    def _finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        self._read()
        tail = self._decoder.decode(b"", final=True)
        if tail:
            self.output.emit(tail)
        self._cleanup(code)

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            if self._process is not None:
                self.output.emit(self._process.errorString() + "\n")
            self._cleanup(-1)

    def _cleanup(self, code: int) -> None:
        process, self._process = self._process, None
        if process is not None:
            process.deleteLater()
            self.finished.emit(code)
