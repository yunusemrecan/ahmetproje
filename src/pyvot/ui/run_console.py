"""Proje penceresindeki konsol: programı çalıştırır, çıktıyı gösterir, girdi alır."""

from __future__ import annotations

import codecs
import html
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontDatabase, QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from pyvot.core import launch
from pyvot.i18n import tr

MAX_BLOCKS = 10000


def kill_tree(pid: int) -> None:
    """Süreci ve başlattığı alt süreçleri (ör. uvicorn --reload) sonlandırır."""
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
        )
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


class RunConsole(QWidget):
    started = Signal()
    finished = Signal(int)
    location_clicked = Signal(Path, int, int)

    def __init__(self, project: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.process: QProcess | None = None
        self.spec: launch.RunSpec | None = None
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._pending = ""  # henüz satır sonu gelmemiş çıktı
        self._ready_seen = False
        self._started_at = 0.0

        self.output = QTextBrowser()
        self.output.setOpenLinks(False)
        self.output.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.output.document().setMaximumBlockCount(MAX_BLOCKS)
        self.output.anchorClicked.connect(self._link_clicked)

        self.input = QLineEdit()
        self.input.setPlaceholderText(tr("console.input_placeholder"))
        self.input.setEnabled(False)
        self.input.returnPressed.connect(self._send_input)
        self.status = QLabel()
        self.clear_btn = QPushButton(tr("action.clear"))
        self.clear_btn.clicked.connect(self.output.clear)

        bottom = QHBoxLayout()
        bottom.addWidget(self.input, 1)
        bottom.addWidget(self.status)
        bottom.addWidget(self.clear_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output, 1)
        layout.addLayout(bottom)

    # --- çalıştırma -----------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.process is not None

    def run(self, spec: launch.RunSpec) -> bool:
        if self.process is not None:
            return False
        self.spec = spec
        self._ready_seen = False
        self._pending = ""
        self._decoder.reset()
        process = QProcess(self)
        env = QProcessEnvironment()
        for key, value in launch.run_env(spec).items():
            env.insert(key, value)
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.setWorkingDirectory(str(spec.cwd))
        if sys.platform != "win32" and hasattr(process, "setUnixProcessParameters"):
            # Kendi oturumunda başlasın ki Durdur alt süreçleri de kapatsın.
            process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession)
        process.readyReadStandardOutput.connect(self._read)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        self.process = process
        self._append_info(tr("console.started", name=spec.name) + "\n" + "$ " + " ".join(_quote(a) for a in spec.cmd))
        self._started_at = time.monotonic()
        process.start(spec.cmd[0], spec.cmd[1:])
        self.input.setEnabled(True)
        self.status.setText(tr("console.running"))
        self.started.emit()
        return True

    def stop(self) -> None:
        if self.process is not None:
            kill_tree(int(self.process.processId()))
            self.process.kill()

    def _send_input(self) -> None:
        if self.process is None:
            return
        text = self.input.text()
        self.input.clear()
        self._append_text(text + "\n", echo=True)
        self.process.write((text + "\n").encode("utf-8"))

    # --- çıktı ------------------------------------------------------------------------

    def _read(self) -> None:
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput().data())
        text = self._decoder.decode(data).replace("\r\n", "\n")
        if text:
            self._append_text(text)

    def _append_text(self, text: str, echo: bool = False) -> None:
        # Bağlantılar satır bazında aranır; yarım satırı bir sonraki parçaya ekle.
        self._pending += text
        if "\n" not in self._pending and not echo and len(self._pending) < 4096:
            # input() istemi gibi satır sonu olmayan metni de hemen göster.
            self._write_plain(self._pending)
            self._pending = ""
            return
        complete, _, rest = self._pending.rpartition("\n")
        self._pending = rest
        lines = complete.split("\n")
        for line in lines:
            self._write_line(line, echo)
        if rest:
            self._write_plain(rest)
            self._pending = ""

    def _write_plain(self, text: str) -> None:
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self._scroll()

    def _write_line(self, line: str, echo: bool = False) -> None:
        self._check_ready(line)
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if echo:
            cursor.insertHtml(f"<span style='color:#3b82f6'>{html.escape(line)}</span>")
        else:
            cursor.insertHtml(self._linkify(line))
        cursor.insertText("\n")
        self._scroll()

    def _linkify(self, line: str) -> str:
        parts: list[str] = []
        last = 0
        for start, end, path, number, column in launch.find_locations(line, self.project):
            parts.append(html.escape(line[last:start]))
            url = QUrl.fromLocalFile(str(path))
            url.setFragment(f"{number}:{column}")
            parts.append(f"<a href='{html.escape(url.toString(), quote=True)}'>{html.escape(line[start:end])}</a>")
            last = end
        parts.append(html.escape(line[last:]))
        text = "".join(parts)
        if re.match(r"\s*(Traceback|\w*(Error|Exception)\b)", line):
            text = f"<span style='color:#d9534f'>{text}</span>"
        return text.replace("  ", "&nbsp; ")

    def _check_ready(self, line: str) -> None:
        if self._ready_seen or self.spec is None or not self.spec.ready_pattern:
            return
        try:
            match = re.search(self.spec.ready_pattern, line)
        except re.error:
            return
        if match:
            self._ready_seen = True
            address = match.group(1) if match.groups() else match.group(0)
            QDesktopServices.openUrl(QUrl(self.spec.ready_uri.replace("%s", address)))

    def _append_info(self, text: str) -> None:
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.output.document().isEmpty():
            cursor.insertText("\n")
        cursor.insertHtml(f"<span style='color:gray'>{html.escape(text).replace(chr(10), '<br>')}</span>")
        cursor.insertText("\n")
        self._scroll()

    def _scroll(self) -> None:
        bar = self.output.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _link_clicked(self, url: QUrl) -> None:
        path = Path(url.toLocalFile())
        line, _, column = url.fragment().partition(":")
        self.location_clicked.emit(path, int(line or 1), int(column or 1))

    # --- bitiş ------------------------------------------------------------------------

    def _finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        self._read()
        tail = self._decoder.decode(b"", final=True)
        if tail or self._pending:
            self._append_text(tail + "\n")
        self._done(code)

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart and self.process is not None:
            self._append_info(self.process.errorString())
            self._done(-1)

    def _done(self, code: int) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        elapsed = time.monotonic() - self._started_at
        key = "console.finished_ok" if code == 0 else "console.finished_error"
        self._append_info(tr(key, code=code, seconds=f"{elapsed:.1f}"))
        self.status.setText("")
        self.input.setEnabled(False)
        process.deleteLater()
        self.finished.emit(code)


def _quote(arg: str) -> str:
    return f'"{arg}"' if " " in arg else arg
