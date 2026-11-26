"""pip ile kurulan uv paketinden uv(.exe) dosyasını dist/Pyvot klasörüne kopyalar."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    import uv  # requirements-build.txt ile kurulur

    source = Path(uv.find_uv_bin())
    target_dir = ROOT / "dist" / "Pyvot"
    if not target_dir.is_dir():
        print(f"{target_dir} yok; önce pyinstaller çalıştırın.", file=sys.stderr)
        return 1
    target = target_dir / source.name
    shutil.copy2(source, target)
    print(f"{source} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
