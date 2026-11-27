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

    window.show_page(window.packages)
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
    window.show_page(window.packages)
    page = window.packages
    _wait(qapp, lambda: page.refresh_btn.isEnabled())

    page.spec.setText("six==1.15.0")
    page.install_btn.click()
    _wait(qapp, lambda: not page.runner.running and page.table.rowCount() == 1, timeout_ms=180000)
    assert page.table.item(0, 0).text() == "six"
    assert "✓" in page.log.toPlainText()
    window.close()


def test_new_project_wizard_creates_project(qapp, tmp_path):
    from pyvot.core.settings import Settings
    from pyvot.ui.context import AppContext
    from pyvot.ui.main_window import MainWindow
    from pyvot.ui.new_project_wizard import PAGE_OPTIONS, PAGE_PROGRESS, NewProjectWizard

    ctx = AppContext(Settings(extra_pythons=[sys.executable], projects_root=str(tmp_path)))
    window = MainWindow(ctx)
    _wait(qapp, lambda: ctx.installs and not ctx.discovering)

    wizard = NewProjectWizard(ctx, window)
    wizard.name_edit.setText("a/b")
    assert not wizard.next_btn.isEnabled()  # geçersiz ad
    wizard.name_edit.setText("Deneme Projesi")
    assert wizard.next_btn.isEnabled()
    wizard.go_next()  # şablon
    wizard.select_template("cli")
    wizard.go_next()  # python
    assert wizard.python_combo.count() >= 1
    wizard.go_next()  # seçenekler
    assert wizard.stack.currentIndex() == PAGE_OPTIONS
    wizard.go_next()  # oluştur
    assert wizard.stack.currentIndex() == PAGE_PROGRESS
    _wait(qapp, lambda: not wizard.job.running, timeout_ms=180000)
    target = tmp_path / "Deneme Projesi"
    assert wizard.created == target, wizard.log.toPlainText()
    assert (target / ".venv").is_dir() and (target / "main.py").is_file()

    page = window.projects
    page.refresh()
    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "Deneme Projesi"
    page.table.selectRow(0)
    assert page.packages_btn.isEnabled()
    page.show_packages()
    assert window.stack.currentWidget() is window.packages
    assert window.packages.python and ".venv" in window.packages.python
    window.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Geri Dönüşüm Kutusu yalnızca Windows'ta denenir")
def test_move_to_trash_on_windows(qapp, tmp_path):
    from pyvot.ui.projects_page import move_to_trash

    folder = tmp_path / "silinecek proje"
    (folder / "src").mkdir(parents=True)
    (folder / "src" / "main.py").write_text("print('x')", encoding="utf-8")
    assert move_to_trash(folder)
    assert not folder.exists()


def test_project_panel_shows_dependencies(qapp, tmp_path, uv_bin):
    from pyvot.core import deps, projects
    from pyvot.core.settings import Settings
    from pyvot.ui.context import AppContext
    from pyvot.ui.main_window import MainWindow

    version = ".".join(map(str, sys.version_info[:3]))
    new = projects.NewProject(name="panel", parent=tmp_path, template="empty", python=sys.executable, python_version=version, git=False)
    target = projects.create(new, uv_bin, lambda _l: None)
    (target / "pyproject.toml").write_text(
        (target / "pyproject.toml").read_text(encoding="utf-8").replace("dependencies = []", 'dependencies = ["six>=1"]')
        + '\n[dependency-groups]\ndev = ["pytest>=8"]\n',
        encoding="utf-8",
    )
    ctx = AppContext(Settings(extra_pythons=[sys.executable]))
    ctx.projects.add(target)
    window = MainWindow(ctx)
    page = window.projects
    page.refresh()
    page.table.selectRow(0)
    panel = page.panel
    assert panel.info is not None and panel.info.path == target
    _wait(qapp, lambda: panel.sum_sync.text() != i18n_tr("info.loading"))
    assert panel.sum_sync.text() == i18n_tr("sync.unsynced")  # pyproject değişti, uv.lock eski
    names = [panel.tree.topLevelItem(i).text(0).strip() for i in range(panel.tree.topLevelItemCount())]
    assert "six" in names and "pytest" in names
    assert panel.add_btn.isEnabled() and not panel.major_btn.isEnabled()
    assert deps.sync_state(target, uv_bin) == "unsynced"
    window.close()


def i18n_tr(key: str) -> str:
    from pyvot.i18n import tr

    return tr(key)
