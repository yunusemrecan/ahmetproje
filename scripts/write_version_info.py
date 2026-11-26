"""installer/version_info.txt üretir (Windows'ta exe'nin Özellikler > Ayrıntılar bilgisi).

Sürüm src/pyvot/__init__.py içinden okunur; tek kaynak orasıdır.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "src" / "pyvot" / "__init__.py"
OUT = ROOT / "installer" / "version_info.txt"


def read_version() -> str:
    match = re.search(r'__version__\s*=\s*"([^"]+)"', INIT.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("__version__ bulunamadı")
    return match.group(1)


def main() -> None:
    version = read_version()
    numbers = [int(n) for n in re.findall(r"\d+", version)[:3]]
    numbers += [0] * (4 - len(numbers))
    tup = ", ".join(str(n) for n in numbers)
    OUT.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041F04B0', [
      StringStruct('CompanyName', 'Pyvot'),
      StringStruct('FileDescription', 'Pyvot'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'Pyvot'),
      StringStruct('OriginalFilename', 'Pyvot.exe'),
      StringStruct('ProductName', 'Pyvot'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [0x041F, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    print(f"{OUT} yazıldı ({version}).")


if __name__ == "__main__":
    main()
