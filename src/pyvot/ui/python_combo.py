from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QWidget

from pyvot.core.models import PythonInstall
from pyvot.ui.context import AppContext


class PythonCombo(QComboBox):
    """Sanal ortam olmayan Python kurulumlarından birini seçtirir."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setMinimumContentsLength(40)
        self.reload()

    def reload(self) -> None:
        current = self.selected()
        self.clear()
        installs = [i for i in self.ctx.installs if not i.is_venv]
        chosen = 0
        for row, install in enumerate(installs):
            self.addItem(f"Python {install.version} ({install.bits}-bit) — {install.executable}", install)
            if current is not None and install.executable == current.executable:
                chosen = row
            elif current is None and (install.is_default or install.first_on_path) and chosen == 0:
                chosen = row
        if installs:
            self.setCurrentIndex(chosen)

    def selected(self) -> PythonInstall | None:
        data = self.currentData()
        return data if isinstance(data, PythonInstall) else None
