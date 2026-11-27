"""Proje penceresinin (Monaco editörü, konsol, sorunlar, önizleme) ekransız testleri."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWebEngineWidgets")

from pyvot.ui.code_editor import monaco_available  # noqa: E402

pytestmark = pytest.mark.skipif(not monaco_available(), reason="Monaco yok (scripts/fetch_monaco.py)")


def _wait(qapp, condition, timeout_ms: int = 30000) -> None:
    from PySide6.QtCore import QDeadlineTimer, QEventLoop

    deadline = QDeadlineTimer(timeout_ms)
    while not condition():
        if deadline.hasExpired():
            raise TimeoutError
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


def _evaluate(qapp, window, function: str, *args):
    box: list = []
    window.editor.evaluate(function, *args, callback=box.append)
    _wait(qapp, lambda: box)
    return box[0]


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "proje"
    root.mkdir()
    (root / "main.py").write_text("print('ana program')\n", encoding="utf-8")
    (root / "selam.py").write_text(
        "isim = input('Adınız: ')\nprint(f'Merhaba {isim}!')\n", encoding="utf-8"
    )
    (root / "kirli.py").write_text("import os\n", encoding="utf-8")
    (root / "veri.csv").write_text("şehir;satış\nİzmir;3\nBursa;5\n", encoding="utf-8")
    return root


@pytest.fixture
def window(qapp, project):
    from pyvot.core.settings import Settings
    from pyvot.ui.context import AppContext

    ctx = AppContext(Settings())
    win = ctx.open_workspace(project)
    _wait(qapp, lambda: win.editor.is_ready)
    yield win
    win._closing_ok = True
    win.console.stop()
    win.close()


def test_opens_main_py_and_saves_edits(qapp, window, project):
    main = (project / "main.py").resolve()
    assert str(main) in window.tabs  # oturum boşken main.py açılır
    window.editor.set_text(main, "print('değişti')\n")
    _wait(qapp, lambda: window.tabs[str(main)].dirty)
    assert window.tab_bar.tabText(window.tab_bar.currentIndex()).startswith("●")
    window.handle_command("save")
    _wait(qapp, lambda: not window.tabs[str(main)].dirty)
    assert main.read_text(encoding="utf-8") == "print('değişti')\n"


def test_format_on_save_uses_vscode_setting(qapp, window, project):
    from pyvot.core import ruff

    if not ruff.find_ruff():
        pytest.skip("ruff yok")
    (project / ".vscode").mkdir()
    (project / ".vscode" / "settings.json").write_text(
        '{\n  // yorum\n  "[python]": {"editor.formatOnSave": true},\n}', encoding="utf-8"
    )
    main = (project / "main.py").resolve()
    window.editor.set_text(main, "x  =  [1,2]\n")
    _wait(qapp, lambda: window.tabs[str(main)].dirty)
    window.handle_command("save")
    _wait(qapp, lambda: main.read_text(encoding="utf-8") == "x = [1, 2]\n")
    _wait(qapp, lambda: not window.tabs[str(main)].dirty)


def test_external_change_reloads_clean_file(qapp, window, project):
    main = (project / "main.py").resolve()
    main.write_text("print('dışarıdan')\n", encoding="utf-8")
    _wait(qapp, lambda: (_evaluate(qapp, window, "snapshot", main.as_uri()) or {}).get("text") == "print('dışarıdan')\n")
    assert not window.tabs[str(main)].dirty


def test_run_with_input_and_traceback_link(qapp, window, project):
    selam = (project / "selam.py").resolve()
    window.open_file(selam)
    from pyvot.core import launch

    spec = launch.file_spec(project, selam)
    spec.cmd[0] = sys.executable
    window._start(spec)
    _wait(qapp, lambda: "Adınız" in window.console.output.toPlainText())
    window.console.input.setText("Ayşe")
    window.console._send_input()
    _wait(qapp, lambda: not window.console.running)
    text = window.console.output.toPlainText()
    assert "Merhaba Ayşe!" in text and "(çıkış kodu 0" in text

    (project / "hata.py").write_text("print(1 / 0)\n", encoding="utf-8")
    spec = launch.file_spec(project, project / "hata.py")
    spec.cmd[0] = sys.executable
    window._start(spec)
    _wait(qapp, lambda: not window.console.running)
    assert "ZeroDivisionError" in window.console.output.toPlainText()
    assert "hata.py" in window.console.output.toHtml() and "<a href=" in window.console.output.toHtml()


def test_stop_kills_long_running_program(qapp, window, project):
    from pyvot.core import launch

    (project / "uzun.py").write_text("import time\nprint('başladı', flush=True)\ntime.sleep(60)\n", encoding="utf-8")
    spec = launch.file_spec(project, project / "uzun.py")
    spec.cmd[0] = sys.executable
    window._start(spec)
    _wait(qapp, lambda: "başladı" in window.console.output.toPlainText())
    window.console.stop()
    _wait(qapp, lambda: not window.console.running, timeout_ms=10000)


def test_problems_list_and_markers(qapp, window, project):
    from pyvot.core import ruff

    if not ruff.find_ruff():
        pytest.skip("ruff yok")
    kirli = (project / "kirli.py").resolve()
    _wait(qapp, lambda: kirli in window.problems.by_file)
    assert window.problems.by_file[kirli][0].code == "F401"
    assert "Sorunlar (" in window.bottom.tabText(1) or "Problems (" in window.bottom.tabText(1)
    window.open_location(kirli, 1, 8)
    assert window.current_tab().path == kirli


def test_csv_and_unsupported_previews(qapp, window, project):
    from pyvot.ui.preview import CsvPreview, UnsupportedPreview

    tab = window.open_file(project / "veri.csv")
    assert isinstance(tab.widget, CsvPreview)
    assert tab.widget.table.rowCount() == 2 and tab.widget.table.horizontalHeaderItem(0).text() == "şehir"
    (project / "resim.bin").write_bytes(b"\x00\x01")
    tab = window.open_file(project / "resim.bin")
    assert isinstance(tab.widget, UnsupportedPreview)


def test_session_is_restored(qapp, project):
    from pyvot.core.settings import Settings
    from pyvot.ui.context import AppContext

    ctx = AppContext(Settings())
    first = ctx.open_workspace(project)
    first.open_file(project / "selam.py")
    first.close()
    qapp.processEvents()
    second = ctx.open_workspace(project)
    assert first is not second
    assert str((project / "selam.py").resolve()) in second.tabs
    second._closing_ok = True
    second.close()


def test_new_file_and_rename(qapp, window, project, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    answers = iter([("yeni.py", True), ("baska.py", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers))
    window.new_file(project)
    assert (project / "yeni.py").is_file() and str((project / "yeni.py").resolve()) in window.tabs
    window.rename((project / "yeni.py").resolve())
    assert (project / "baska.py").is_file() and not (project / "yeni.py").exists()
    assert str((project / "baska.py").resolve()) in window.tabs


def test_notebook_html_renders_outputs(qapp):
    from PySide6.QtGui import QImage, QTextDocument
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(0xFF3B82F6)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    notebook = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Başlık\n", "metin"]},
            {
                "cell_type": "code",
                "execution_count": 3,
                "source": "print('x')",
                "outputs": [
                    {"output_type": "stream", "text": ["x\n"]},
                    {"output_type": "display_data", "data": {"image/png": base64.b64encode(bytes(data.data())).decode()}},
                    {"output_type": "error", "traceback": ["\x1b[31mValueError\x1b[0m: kötü"]},
                ],
            },
        ]
    }
    from pyvot.ui.preview import notebook_html

    document = QTextDocument()
    html = notebook_html(json.loads(json.dumps(notebook)), document)
    assert "Başlık" in html and "[3]" in html and "nbimage://" in html
    assert "ValueError: kötü" in html and "\x1b" not in html
