"""pip ile kurulan uv ve Ruff çalıştırılabilirlerini dist/Pyvot klasörüne kopyalar.

Ayrıca Monaco editörünün pakete girdiğini doğrular.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _utf8_output() -> None:
    # Windows konsolunda Türkçe karakterler (İ, ş...) yazılabilsin.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _utf8_output()
    import uv  # requirements-build.txt ile kurulur
    from ruff.__main__ import find_ruff_bin

    target_dir = ROOT / "dist" / "Pyvot"
    if not target_dir.is_dir():
        print(f"{target_dir} yok; önce pyinstaller çalıştırın.", file=sys.stderr)
        return 1
    for source in (Path(uv.find_uv_bin()), Path(find_ruff_bin())):
        target = target_dir / source.name
        shutil.copy2(source, target)
        print(f"{source} -> {target}")
    loaders = list(target_dir.rglob("monaco/vs/loader.js"))
    if not loaders:
        print("Monaco pakette yok! Önce scripts/fetch_monaco.py çalıştırın.", file=sys.stderr)
        return 1
    print(f"Monaco: {loaders[0].parent.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
