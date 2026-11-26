"""Arayüzün açılabildiğini ve komut çalıştırıcının çalıştığını doğrular (ekransız)."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6.QtWidgets")


def _wait(qapp, condition, timeout_ms: int = 60000) -> None:
    from PySide6.QtCore import QDeadlineTimer, QEventLoop

    deadline = QDeadlineTimer(timeout_ms)
    while not condition():
        if deadline.hasExpired():
            raise TimeoutError
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


def test_command_runner_streams_output(qapp):
    from pyvot.ui.workers import CommandRunner

    runner = CommandRunner()
    chunks: list[str] = []
    codes: list[int] = []
    runner.output.connect(chunks.append)
    runner.finished.connect(codes.append)
    assert runner.start([sys.executable, "-c", "print('merhaba ğüşİ')"])
    _wait(qapp, lambda: codes)
    assert codes == [0]
    assert "merhaba ğüşİ" in "".join(chunks)
    assert not runner.running


def test_command_runner_reports_missing_program(qapp):
    from pyvot.ui.workers import CommandRunner

    runner = CommandRunner()
    codes: list[int] = []
    runner.finished.connect(codes.append)
    runner.start(["this-program-does-not-exist-pyvot"])
    _wait(qapp, lambda: codes)
    assert codes == [-1]


def test_main_window_lists_pythons_and_packages(qapp, venv_python):
    from pyvot.core.settings import Settings
    from pyvot.ui.context import AppContext
    from pyvot.ui.main_window import MainWindow

    settings = Settings(extra_pythons=[venv_python], last_python=venv_python)
    ctx = AppContext(settings)
    window = MainWindow(ctx)
    window.show()
    _wait(qapp, lambda: ctx.installs and not ctx.discovering)
    assert window.pythons.table.rowCount() >= 1

    window.sidebar.setCurrentRow(1)
    page = window.packages
    assert page.python and page.python.lower() == venv_python.lower()
    _wait(qapp, lambda: page.refresh_btn.isEnabled())
    assert page.table.rowCount() == 0  # boş ortam
    window.close()


@pytest.mark.network
def test_install_through_packages_page(qapp, venv_python):
    from pyvot.core.settings import Settings
    from pyvot.ui.context import AppContext
    from pyvot.ui.main_window import MainWindow

    ctx = AppContext(Settings(extra_pythons=[venv_python], last_python=venv_python))
    window = MainWindow(ctx)
    _wait(qapp, lambda: ctx.installs and not ctx.discovering)
    window.sidebar.setCurrentRow(1)
    page = window.packages
    _wait(qapp, lambda: page.refresh_btn.isEnabled())

    page.spec.setText("six==1.15.0")
    page.install_btn.click()
    _wait(qapp, lambda: not page.runner.running and page.table.rowCount() == 1, timeout_ms=180000)
    assert page.table.item(0, 0).text() == "six"
    assert "✓" in page.log.toPlainText()
    window.close()
