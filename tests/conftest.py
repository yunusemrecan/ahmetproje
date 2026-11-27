from __future__ import annotations

import os
import shutil
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Kök kullanıcıyla ya da CI'da Chromium korumalı alanı açılamayabilir.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Testler gerçek ayar klasörüne dokunmasın."""
    monkeypatch.setenv("PYVOT_HOME", str(tmp_path / "pyvot-home"))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


@pytest.fixture(scope="session")
def uv_bin():
    from pyvot.core.uvtool import find_uv

    found = find_uv()
    if not found:
        pytest.skip("uv bulunamadı")
    return found


@pytest.fixture
def venv_python(tmp_path, uv_bin):
    """İnternet gerektirmeden boş bir sanal ortam (mevcut Python ile)."""
    from pyvot.core import proc

    target = tmp_path / "env"
    result = proc.run([uv_bin, "venv", "--python", sys.executable, str(target)], timeout=120)
    assert result.returncode == 0, result.stderr
    exe = target / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    assert exe.exists()
    yield str(exe)
    shutil.rmtree(target, ignore_errors=True)
