"""Uygulamanın giriş noktası."""

from __future__ import annotations

import sys
from pathlib import Path

from pyvot import APP_NAME, __version__


def _windows_setup() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    # Görev çubuğunda python.exe yerine Pyvot simgesi görünsün.
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Pyvot.Pyvot")
    except (AttributeError, OSError):
        pass
    # PyInstaller'ın DLL arama klasörü, başlattığımız Python'lara geçmesin.
    if getattr(sys, "frozen", False):
        try:
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        except (AttributeError, OSError):
            pass


def _icon_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
    for candidate in (base / "pyvot" / "assets" / "pyvot.svg", Path(__file__).parent / "assets" / "pyvot.svg"):
        if candidate.exists():
            return candidate
    return Path(__file__).parent / "assets" / "pyvot.svg"


def main() -> int:
    _windows_setup()

    from PySide6.QtCore import QCoreApplication, QLocale, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from pyvot import i18n
    from pyvot.core.settings import Settings
    from pyvot.ui.context import AppContext
    from pyvot.ui.main_window import MainWindow
    from pyvot.ui.theme import apply_theme

    # Monaco editörü için QtWebEngine; bu ayar QApplication'dan önce yapılmalı.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)

    settings = Settings.load()
    language = settings.language
    if language == "auto":
        language = "tr" if QLocale.system().name().lower().startswith("tr") else "en"
    i18n.set_language(language)
    apply_theme(app, settings.theme)

    icon = QIcon(str(_icon_path()))
    app.setWindowIcon(icon)

    ctx = AppContext(settings)
    window = MainWindow(ctx, icon)
    window.show()
    if "--self-test" in sys.argv:
        return _self_test(app, ctx)
    code = app.exec()
    # Arka planda süren işlerin bitmesini kısa süre bekle.
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(3000)
    return code


def _self_test(app, ctx) -> int:  # noqa: ANN001
    """Paketlenmiş uygulamayı CI'da denemek için: proje penceresini ve editörü açar.

    0: her şey yolunda; 1: bir şey eksik. Sonuç PYVOT_SELF_TEST_REPORT dosyasına da yazılır.
    """
    import os
    import tempfile

    from PySide6.QtCore import QTimer

    from pyvot.core import ruff, uvtool

    report: list[str] = []
    project = Path(tempfile.mkdtemp(prefix="pyvot-self-test-"))
    (project / "main.py").write_text("print('merhaba')\n", encoding="utf-8")
    report.append(f"uv: {uvtool.find_uv()}")
    report.append(f"ruff: {ruff.find_ruff()}")
    window = ctx.open_workspace(project)
    editor = getattr(window, "editor", None)
    result = {"code": 1}

    def finish() -> None:
        ready = editor is not None and editor.is_ready
        report.append(f"monaco: {'ready' if ready else 'NOT READY'}")
        if editor is not None and not ready:
            report.extend(editor.page.console[-10:])
        ok = ready and uvtool.find_uv() is not None and ruff.find_ruff() is not None
        result["code"] = 0 if ok else 1
        report.append("OK" if ok else "FAILED")
        target = os.environ.get("PYVOT_SELF_TEST_REPORT")
        if target:
            Path(target).write_text("\n".join(report) + "\n", encoding="utf-8")
        window._closing_ok = True  # type: ignore[attr-defined]
        app.quit()

    if editor is not None:
        editor.ready.connect(lambda: QTimer.singleShot(500, finish))
    QTimer.singleShot(60000, finish)
    app.exec()
    return result["code"]


if __name__ == "__main__":
    raise SystemExit(main())
