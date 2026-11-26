"""Sayfaların paylaştığı durum: ayarlar, uv ve bulunan Python kurulumları."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from pyvot.core import discovery, uvtool
from pyvot.core.models import PythonInstall, same_path_key
from pyvot.core.packages import PackageManager
from pyvot.core.pypi import PypiIndex
from pyvot.core.settings import Settings
from pyvot.ui.workers import run_in_background


class AppContext(QObject):
    installs_changed = Signal()
    discovery_started = Signal()
    discovery_failed = Signal(str)
    busy_changed = Signal(bool)
    show_packages_for = Signal(str)  # yorumlayıcı yolu

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.installs: list[PythonInstall] = []
        self.uv: str | None = None
        self.uv_version: str | None = None
        self.pypi_index = PypiIndex()
        self.discovering = False
        self._busy = 0
        self.refresh_uv()

    # --- uv ---------------------------------------------------------------------

    def refresh_uv(self) -> None:
        self.uv = uvtool.find_uv(self.settings.uv_path or None)
        self.uv_version = uvtool.uv_version(self.uv) if self.uv else None
        if self.uv and not self.uv_version:
            self.uv = None

    def package_manager(self, python: str) -> PackageManager:
        return PackageManager.create(python, self.uv, self.settings.backend)

    # --- Python keşfi -----------------------------------------------------------

    def discover(self) -> None:
        if self.discovering:
            return
        self.discovering = True
        self.discovery_started.emit()
        self.push_busy()
        run_in_background(
            discovery.discover,
            self.uv,
            list(self.settings.extra_pythons),
            on_done=self._discovered,
            on_error=self._discovery_error,
        )

    def _discovered(self, installs: list[PythonInstall]) -> None:
        self.discovering = False
        self.pop_busy()
        self.installs = installs
        self.installs_changed.emit()

    def _discovery_error(self, exc: Exception) -> None:
        self.discovering = False
        self.pop_busy()
        self.discovery_failed.emit(str(exc))

    def find_install(self, executable: str) -> PythonInstall | None:
        key = same_path_key(executable)
        for install in self.installs:
            if same_path_key(install.executable) == key:
                return install
        return None

    def add_python(self, executable: str) -> None:
        if executable not in self.settings.extra_pythons:
            self.settings.extra_pythons.append(executable)
            self.settings.save()

    def forget_python(self, executable: str) -> bool:
        if executable in self.settings.extra_pythons:
            self.settings.extra_pythons.remove(executable)
            self.settings.save()
            return True
        return False

    # --- meşgul göstergesi --------------------------------------------------------

    def push_busy(self) -> None:
        self._busy += 1
        if self._busy == 1:
            self.busy_changed.emit(True)

    def pop_busy(self) -> None:
        self._busy = max(0, self._busy - 1)
        if self._busy == 0:
            self.busy_changed.emit(False)
