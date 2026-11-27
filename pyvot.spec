# PyInstaller yapılandırması. Kullanım: pyinstaller pyvot.spec
# Çıktı: dist/Pyvot/Pyvot.exe (tek klasör; hızlı açılır)
# -*- mode: python -*-

import sys
from pathlib import Path

ROOT = Path(SPECPATH)
ICON = ROOT / "installer" / "pyvot.ico"

# v0.1'de kullanılmayan büyük Qt modülleri dışarıda kalır (Monaco v0.3'te gelecek).
EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtPdf",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "tkinter",
]

a = Analysis(
    [str(ROOT / "src" / "pyvot" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(ROOT / "src" / "pyvot" / "assets"), "pyvot/assets"),
        (str(ROOT / "src" / "pyvot" / "templates"), "pyvot/templates"),
    ],
    hiddenimports=["PySide6.QtSvg"],
    excludes=EXCLUDES,
    noarchive=False,
)


def _keep(entry) -> bool:
    """Qt çeviri dosyalarından yalnızca Türkçe ve İngilizce kalsın."""
    dest = entry[0].replace("\\", "/")
    if "/translations/" in dest and dest.endswith(".qm"):
        return dest.rsplit("/", 1)[-1].split(".")[0].rsplit("_", 1)[-1] in ("tr", "en")
    return True


a.datas = [entry for entry in a.datas if _keep(entry)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Pyvot",
    console=False,
    icon=str(ICON) if sys.platform == "win32" else None,
    version=str(ROOT / "installer" / "version_info.txt") if sys.platform == "win32" else None,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="Pyvot", upx=False)
