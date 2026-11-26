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

    from PySide6.QtCore import QLocale
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from pyvot import i18n
    from pyvot.core.settings import Settings
    from pyvot.ui.context import AppContext
    from pyvot.ui.main_window import MainWindow
    from pyvot.ui.theme import apply_theme

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
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
