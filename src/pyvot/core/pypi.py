"""PyPI istemcisi: paket bilgisi ve isimle arama.

PyPI'nin arama API'si yok. Arama için tüm paket adlarının listesi
(/simple/, yaklaşık 10 MB) bir kez indirilir ve önbellekte tutulur.
"""

from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from packaging.version import InvalidVersion, Version

from pyvot import __version__
from pyvot.core.paths import cache_dir

PYPI = "https://pypi.org"
USER_AGENT = f"Pyvot/{__version__}"
INDEX_MAX_AGE = 7 * 24 * 3600

_NORMALIZE = re.compile(r"[-_.]+")
_FOLD = str.maketrans({"_": "-", ".": "-"})


def normalize(name: str) -> str:
    """PEP 503 ad normalleştirmesi."""
    return _NORMALIZE.sub("-", name).lower()


def _get(url: str, timeout: float, accept: str = "application/json") -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Encoding": "gzip"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (sabit https adresi)
        data = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data


# --- paket bilgisi --------------------------------------------------------------


@dataclass
class PackageInfo:
    name: str
    version: str
    summary: str = ""
    license: str = ""
    requires_python: str = ""
    author: str = ""
    home_page: str = ""
    project_urls: dict[str, str] = field(default_factory=dict)
    requires_dist: list[str] = field(default_factory=list)
    releases: list[str] = field(default_factory=list)  # yeniden eskiye


def _sort_versions(versions: list[str]) -> list[str]:
    def key(v: str) -> tuple[int, Version | str]:
        try:
            return (1, Version(v))
        except InvalidVersion:
            return (0, v)

    return sorted(versions, key=key, reverse=True)


def _license(info: dict) -> str:
    expression = (info.get("license_expression") or "").strip()
    if expression:
        return expression
    text = (info.get("license") or "").strip()
    if text and len(text) <= 80 and "\n" not in text:
        return text
    for classifier in info.get("classifiers") or []:
        if classifier.startswith("License ::"):
            return classifier.split("::")[-1].strip()
    return text.splitlines()[0][:80] if text else ""


def parse_info(data: dict) -> PackageInfo:
    info = data.get("info") or {}
    releases = data.get("releases") or {}
    # Sadece geri çekilmiş (yanked) dosyaları olan sürümleri gösterme.
    visible = [
        v for v, files in releases.items() if not files or not all(f.get("yanked") for f in files)
    ]
    urls = {str(k): str(v) for k, v in (info.get("project_urls") or {}).items() if v}
    return PackageInfo(
        name=str(info.get("name") or ""),
        version=str(info.get("version") or ""),
        summary=str(info.get("summary") or ""),
        license=_license(info),
        requires_python=str(info.get("requires_python") or ""),
        author=str(info.get("author") or info.get("author_email") or ""),
        home_page=str(info.get("home_page") or ""),
        project_urls=urls,
        requires_dist=[str(r) for r in (info.get("requires_dist") or [])],
        releases=_sort_versions(visible),
    )


def fetch_info(name: str, timeout: float = 20) -> PackageInfo | None:
    """Paket yoksa None; ağ hatasında OSError/URLError yükseltir."""
    url = f"{PYPI}/pypi/{normalize(name)}/json"
    try:
        raw = _get(url, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return parse_info(json.loads(raw))


# --- arama --------------------------------------------------------------------


def parse_simple_index(raw: bytes) -> list[str]:
    data = json.loads(raw)
    return [p["name"] for p in data.get("projects", []) if isinstance(p, dict) and p.get("name")]


def search_names(names: list[str], query: str, limit: int = 50) -> list[str]:
    """Tam eşleşme > ön ek > içerir sırasıyla, kısa adlar önce."""
    q = normalize(query.strip())
    if not q:
        return []
    exact: list[str] = []
    prefix: list[str] = []
    contains: list[str] = []
    for name in names:
        folded = name.lower().translate(_FOLD)
        if q not in folded:
            continue
        folded = _NORMALIZE.sub("-", folded)
        if folded == q:
            exact.append(name)
        elif folded.startswith(q):
            prefix.append(name)
        elif q in folded:
            contains.append(name)
    prefix.sort(key=len)
    contains.sort(key=len)
    return (exact + prefix + contains)[:limit]


class PypiIndex:
    def __init__(self, cache_file: Path | None = None) -> None:
        self.cache_file = cache_file or cache_dir() / "pypi-index.txt.gz"
        self.names: list[str] = []

    @property
    def loaded(self) -> bool:
        return bool(self.names)

    def cache_is_fresh(self) -> bool:
        try:
            return time.time() - self.cache_file.stat().st_mtime < INDEX_MAX_AGE
        except OSError:
            return False

    def load(self, force_download: bool = False, timeout: float = 120) -> None:
        if not force_download and self.cache_is_fresh():
            try:
                self.names = gzip.decompress(self.cache_file.read_bytes()).decode("utf-8").split("\n")
                return
            except (OSError, EOFError, UnicodeDecodeError):
                pass
        try:
            raw = _get(f"{PYPI}/simple/", timeout, accept="application/vnd.pypi.simple.v1+json")
        except OSError:
            # Ağ yoksa eski önbellek de iş görür.
            if self.cache_file.exists():
                self.names = gzip.decompress(self.cache_file.read_bytes()).decode("utf-8").split("\n")
                return
            raise
        self.names = parse_simple_index(raw)
        tmp = self.cache_file.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress("\n".join(self.names).encode("utf-8")))
        tmp.replace(self.cache_file)

    def search(self, query: str, limit: int = 50) -> list[str]:
        return search_names(self.names, query, limit)
