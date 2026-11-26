"""Kullanıcı ayarları: %LOCALAPPDATA%\\Pyvot\\settings.json"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from pyvot.core.paths import data_dir

LANGUAGES = ("auto", "tr", "en")
THEMES = ("system", "light", "dark")


@dataclass
class Settings:
    language: str = "auto"
    theme: str = "system"
    backend: str = "auto"  # auto | uv | pip
    uv_path: str = ""
    extra_pythons: list[str] = field(default_factory=list)
    last_python: str = ""

    @classmethod
    def file(cls) -> Path:
        return data_dir() / "settings.json"

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or cls.file()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        settings = cls(**{k: v for k, v in data.items() if k in known})
        if settings.language not in LANGUAGES:
            settings.language = "auto"
        if settings.theme not in THEMES:
            settings.theme = "system"
        if settings.backend not in ("auto", "uv", "pip"):
            settings.backend = "auto"
        if not isinstance(settings.extra_pythons, list):
            settings.extra_pythons = []
        return settings

    def save(self, path: Path | None = None) -> None:
        path = path or self.file()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
