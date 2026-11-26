from __future__ import annotations

import os
from dataclasses import dataclass, field


def same_path_key(path: str) -> str:
    """Yolun kendisi için anahtar; sembolik bağları çözmez.

    Linux/macOS'ta venv/bin/python ana yorumlayıcıya bir bağdır; ikisi farklı
    ortamlardır, bu yüzden arayüzdeki eşleştirmeler bunu kullanır.
    """
    return os.path.normcase(os.path.abspath(path))


def path_key(path: str) -> str:
    """Aynı dosyayı gösteren yolları eşleştirmek için anahtar (bağları çözer)."""
    try:
        real = os.path.realpath(path)
    except OSError:
        real = os.path.abspath(path)
    return os.path.normcase(real)


@dataclass
class PythonInstall:
    executable: str
    version: str
    implementation: str = "cpython"
    bits: int = 64
    machine: str = ""
    prefix: str = ""
    base_prefix: str = ""
    sources: set[str] = field(default_factory=set)
    is_default: bool = False  # py başlatıcısının varsayılanı
    first_on_path: bool = False
    company: str = ""
    real_executable: str = ""  # yorumlayıcının kendi bildirdiği sys.executable

    @property
    def is_venv(self) -> bool:
        return bool(self.prefix) and path_key(self.prefix) != path_key(self.base_prefix or self.prefix)

    @property
    def version_tuple(self) -> tuple[int, ...]:
        parts: list[int] = []
        for piece in self.version.split("."):
            digits = "".join(ch for ch in piece if ch.isdigit())
            parts.append(int(digits) if digits else 0)
        return tuple(parts)

    @property
    def short_version(self) -> str:
        return ".".join(self.version.split(".")[:2])

    def label(self) -> str:
        kind = "venv" if self.is_venv else f"{self.bits}-bit"
        return f"Python {self.version} ({kind}) — {self.executable}"


@dataclass
class Package:
    name: str
    version: str
    latest: str | None = None
    editable_location: str | None = None

    @property
    def outdated(self) -> bool:
        return bool(self.latest) and self.latest != self.version
