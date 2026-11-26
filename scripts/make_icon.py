"""assets/pyvot.svg dosyasından Windows için çok boyutlu pyvot.ico üretir.

Kullanım: python scripts/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "src" / "pyvot" / "assets" / "pyvot.svg"
ICO = ROOT / "installer" / "pyvot.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data.data())


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        print(f"Geçersiz SVG: {SVG}", file=sys.stderr)
        return 1
    images = [render_png(renderer, size) for size in SIZES]
    # ICO dosyası: başlık + her boyut için dizin girdisi + PNG verileri.
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in zip(SIZES, images, strict=True):
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    ICO.parent.mkdir(parents=True, exist_ok=True)
    ICO.write_bytes(header + entries + blobs)
    print(f"{ICO} yazıldı ({len(SIZES)} boyut).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
