"""Proje penceresi için dosya yardımcıları: dil, okuma, gizli klasörler, oturum."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pyvot.core.paths import data_dir

MAX_TEXT_BYTES = 5 * 1024 * 1024

HIDDEN_NAMES = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".ipynb_checkpoints",
    ".DS_Store",
}

LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".pyw": "python",
    ".json": "json",
    ".ipynb": "json",
    ".toml": "ini",  # Monaco'da TOML yok; ini en yakın renklendirme
    ".ini": "ini",
    ".cfg": "ini",
    ".lock": "ini",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".jinja": "html",
    ".j2": "html",
    ".css": "css",
    ".scss": "scss",
    ".js": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".xml": "xml",
    ".svg": "xml",
    ".sql": "sql",
    ".sh": "shell",
    ".bat": "bat",
    ".cmd": "bat",
    ".ps1": "powershell",
    ".dockerfile": "dockerfile",
}
NAME_LANGUAGES = {"Dockerfile": "dockerfile", ".gitignore": "ini", ".python-version": "plaintext", "Makefile": "plaintext"}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico"}
PREVIEW_SUFFIXES = IMAGE_SUFFIXES | {".csv", ".ipynb", ".svg", ".md", ".markdown"}
# Bunlar doğrudan önizlemede açılır (editörde değil).
OPEN_AS_PREVIEW = IMAGE_SUFFIXES | {".csv", ".ipynb"}


def is_hidden(name: str) -> bool:
    return name in HIDDEN_NAMES or name.endswith(".egg-info")


def language_for(path: Path) -> str:
    return NAME_LANGUAGES.get(path.name) or LANGUAGES.get(path.suffix.lower(), "plaintext")


class NotText(Exception):
    """Dosya metin değil ya da editörde açılamayacak kadar büyük."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason  # "binary" | "large" | "unreadable"


def read_text(path: Path) -> tuple[str, str]:
    """(metin, satır sonu) döndürür; metin değilse NotText yükseltir."""
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            raise NotText("large")
        data = path.read_bytes()
    except OSError as exc:
        raise NotText("unreadable") from exc
    if b"\0" in data[:8192]:
        raise NotText("binary")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp1254")  # eski Türkçe Windows dosyaları
        except UnicodeDecodeError as exc:
            raise NotText("binary") from exc
    eol = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), eol


def write_text(path: Path, text: str, eol: str = "\n") -> None:
    text = text.replace("\r\n", "\n")  # Monaco metni dosyanın kendi satır sonuyla verir
    if eol != "\n":
        text = text.replace("\n", eol)
    data = text.encode("utf-8")
    tmp = path.with_name(path.name + ".pyvot-tmp")
    tmp.write_bytes(data)
    # Önce geçici dosyayı yerine koy (yarıda kesilirse eski dosya bozulmaz).
    # Windows bu değişimi, dosya başka bir yerde kısa süreliğine okunurken bile
    # reddeder (ör. dış değişiklik kontrolü, virüs tarayıcısı, arama dizini).
    for attempt in range(10):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
    # Hâlâ olmadıysa dosyanın içine doğrudan yaz: okunurken de izin verilir.
    try:
        with open(path, "wb") as handle:
            handle.write(data)
    finally:
        tmp.unlink(missing_ok=True)


# --- oturum (proje yeniden açılınca kalınan yerden devam) ----------------------------


@dataclass
class Session:
    open_files: list[str] = field(default_factory=list)
    active: str = ""
    geometry: str = ""  # base64


class SessionStore:
    def __init__(self, file: Path | None = None) -> None:
        self.file = file or data_dir() / "workspaces.json"

    def _load_all(self) -> dict:
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def load(self, project: Path) -> Session:
        raw = self._load_all().get(str(project))
        if not isinstance(raw, dict):
            return Session()
        files = [f for f in raw.get("open_files") or [] if isinstance(f, str)]
        return Session(open_files=files, active=str(raw.get("active") or ""), geometry=str(raw.get("geometry") or ""))

    def save(self, project: Path, session: Session) -> None:
        data = self._load_all()
        data[str(project)] = asdict(session)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.file)
