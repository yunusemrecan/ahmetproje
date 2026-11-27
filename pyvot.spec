# PyInstaller yapılandırması. Kullanım: pyinstaller pyvot.spec
# Çıktı: dist/Pyvot/Pyvot.exe (tek klasör; hızlı açılır)
# -*- mode: python -*-

import sys
from pathlib import Path

ROOT = Path(SPECPATH)
ICON = ROOT / "installer" / "pyvot.ico"

# Kullanılmayan büyük Qt modülleri dışarıda kalır. QtWebEngine (Monaco editörü)
# QtQml/QtQuick/QtPositioning'e bağlı olduğu için onlar dışlanmaz.
EXCLUDES = [
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "tkinter",
]

a = Analysis(
    [str(ROOT / "src" / "pyvot" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(ROOT / "src" / "pyvot" / "assets"), "pyvot/assets"),
        (str(ROOT / "src" / "pyvot" / "templates"), "pyvot/templates"),
        (str(ROOT / "src" / "pyvot" / "web"), "pyvot/web"),  # editor.html + Monaco
    ],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel"],
    excludes=EXCLUDES,
    noarchive=False,
)


def _keep(entry) -> bool:
    """Qt ve WebEngine çeviri dosyalarından yalnızca Türkçe ve İngilizce kalsın."""
    dest = entry[0].replace("\\", "/")
    name = dest.rsplit("/", 1)[-1]
    if "/qtwebengine_locales/" in dest and name.endswith(".pak"):
        return name in ("tr.pak", "en-US.pak", "en-GB.pak")
    if "/translations/" in dest and dest.endswith(".qm"):
        return name.split(".")[0].rsplit("_", 1)[-1] in ("tr", "en")
    return True


# PySide6 kancaları QtWebEngine ile birlikte kullanmadığımız onlarca Qt kütüphanesini
# (3D, grafikler, QML denetimleri...) de topluyor. WebEngine'in gerçekten bağlı olduğu
# kütüphaneler: Core, Gui, Widgets, Network, OpenGL, Positioning, PrintSupport, Qml,
# QmlMeta, QmlModels, QmlWorkerScript, Quick, QuickWidgets, Svg, WebChannel,
# WebEngineCore, WebEngineWidgets, DBus. Aşağıdakiler bunların dışında kalanlar.
import re as _re

_UNUSED_QT = _re.compile(
    r"^(?:lib)?Qt6(3D|Charts|DataVisualization|Graphs|Labs|Location|Multimedia|Pdf|"
    r"Quick3D|QuickControls2|QuickDialogs2|QuickEffects|QuickLayouts|QuickParticles|"
    r"QuickShapes|QuickTemplates2|QuickTest|QuickTimeline|QuickVectorImage|RemoteObjects|"
    r"Scxml|Sensors|SerialPort|ShaderTools|SpatialAudio|Sql|StateMachine|Test|TextToSpeech|"
    r"VirtualKeyboard|WebEngineQuick|WebView|WebSockets|WebChannelQuick|PositioningQuick|"
    r"QmlDesignSupport|QmlLocalStorage|QmlXmlListModel|QmlNetwork|QmlCore|Concurrent)"
)


def _wanted(entry) -> bool:
    dest = entry[0].replace("\\", "/")
    if "/qml/" in dest or dest.startswith("PySide6/Qt/qml"):
        return False  # QML dosyaları: Pyvot Qt Widgets kullanıyor
    return not _UNUSED_QT.match(dest.rsplit("/", 1)[-1])


a.datas = [entry for entry in a.datas if _keep(entry) and _wanted(entry)]
a.binaries = [entry for entry in a.binaries if _wanted(entry)]
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
