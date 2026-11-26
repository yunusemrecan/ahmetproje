"""uv'yi bulma: önce ayarlardaki yol, sonra uygulamayla gelen kopya, sonra PATH."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pyvot.core import proc

UV_EXE = "uv.exe" if sys.platform == "win32" else "uv"


def bundled_uv() -> str | None:
    bases: list[Path] = []
    if getattr(sys, "frozen", False):
        bases.append(Path(sys.executable).parent)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bases.append(Path(meipass))
    for base in bases:
        for candidate in (base / UV_EXE, base / "bin" / UV_EXE):
            if candidate.is_file():
                return str(candidate)
    return None


def find_uv(override: str | None = None) -> str | None:
    if override:
        return override if Path(override).is_file() else None
    found = bundled_uv()
    if found:
        return found
    try:
        import uv  # type: ignore[import-not-found]

        path = uv.find_uv_bin()
        if path and Path(path).is_file():
            return str(path)
    except Exception:
        pass
    return shutil.which("uv")


def uv_version(uv: str) -> str | None:
    try:
        result = proc.run([uv, "--version"], timeout=15)
    except (OSError, proc.subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    # "uv 0.11.32 (abc123 2026-01-01)"
    parts = result.stdout.split()
    return parts[1] if len(parts) >= 2 else result.stdout.strip() or None
