"""Monaco Editor'ü (VS Code'un editörü) npm'den indirip uygulamanın içine koyar.

Sürüm ve SHA-512 özeti sabittir; özet tutmazsa hiçbir şey yazılmaz.
Kullanım: python scripts/fetch_monaco.py
Çıktı: src/pyvot/web/monaco/vs  (git'e eklenmez)
"""

from __future__ import annotations

import base64
import hashlib
import io
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

VERSION = "0.57.0"
INTEGRITY = "sha512-5BkI9KGoqrNvBGUe15/QlZq3OooZ8WLg1AxTpaqHRCP3HNpzPPZKE2EDz8M7c+VRmCeUw1Brp4cx/PWm3kI/5A=="
URL = f"https://registry.npmjs.org/monaco-editor/-/monaco-editor-{VERSION}.tgz"

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "src" / "pyvot" / "web" / "monaco"
STAMP = TARGET / "VERSION"


def _utf8_output() -> None:
    # Windows konsolunda Türkçe karakterler (İ, ş...) yazılabilsin.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _utf8_output()
    if STAMP.exists() and STAMP.read_text(encoding="utf-8").strip() == VERSION:
        print(f"Monaco {VERSION} zaten var: {TARGET}")
        return 0
    print(f"İndiriliyor: {URL}")
    request = urllib.request.Request(URL, headers={"User-Agent": "pyvot-build"})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 (sabit https adresi)
        data = response.read()
    algorithm, expected = INTEGRITY.split("-", 1)
    actual = base64.b64encode(hashlib.new(algorithm, data).digest()).decode()
    if actual != expected:
        print(f"Özet tutmadı!\n  beklenen: {expected}\n  gelen:    {actual}", file=sys.stderr)
        return 1

    if TARGET.exists():
        shutil.rmtree(TARGET)
    prefix = "package/min/vs/"
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.startswith(prefix):
                continue
            relative = Path(member.name[len("package/min/"):])
            if ".." in relative.parts:
                continue
            dest = TARGET / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            assert extracted is not None
            dest.write_bytes(extracted.read())
        license_member = archive.getmember("package/LICENSE")
        license_file = archive.extractfile(license_member)
        assert license_file is not None
        (TARGET / "LICENSE").write_bytes(license_file.read())
    STAMP.write_text(VERSION + "\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in TARGET.rglob("*") if f.is_file())
    print(f"Monaco {VERSION} hazır: {TARGET} ({size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
