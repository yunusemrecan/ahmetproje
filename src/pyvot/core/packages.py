"""Bir Python ortamındaki paketleri uv (tercihen) ya da pip ile yönetir.

Komutlar burada liste olarak üretilir; uzun süren kurma/kaldırma işlemlerini
arayüz kendi çalıştırır ki çıktı canlı aksın.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from packaging.requirements import InvalidRequirement, Requirement

from pyvot.core import proc
from pyvot.core.models import Package

BACKENDS = ("auto", "uv", "pip")


class PackageError(RuntimeError):
    pass


def parse_list_json(text: str) -> list[Package]:
    text = text.strip()
    if not text:
        return []
    # Bazı sürümler JSON'dan önce uyarı yazabilir; dizinin başını ararız.
    start = text.find("[")
    if start < 0:
        raise PackageError(text)
    try:
        items = json.loads(text[start:])
    except json.JSONDecodeError as exc:
        raise PackageError(f"JSON: {exc}") from exc
    packages: list[Package] = []
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            continue
        packages.append(
            Package(
                name=str(item["name"]),
                version=str(item.get("version", "")),
                latest=item.get("latest_version") or None,
                editable_location=item.get("editable_project_location") or None,
            )
        )
    packages.sort(key=lambda p: p.name.lower())
    return packages


def validate_specs(text: str) -> list[str]:
    """Kullanıcının yazdığı "requests numpy==2.1" gibi girdiyi doğrular.

    Geçersiz bir parça varsa ValueError(parça) yükseltir.
    """
    specs = text.split()
    for spec in specs:
        if spec.startswith("-"):
            raise ValueError(spec)
        try:
            Requirement(spec)
        except InvalidRequirement as exc:
            raise ValueError(spec) from exc
    return specs


@dataclass
class PackageManager:
    python: str
    backend: str  # "uv" ya da "pip"
    uv: str | None = None

    @classmethod
    def create(cls, python: str, uv: str | None, preference: str = "auto") -> PackageManager:
        if preference == "pip" or not uv:
            return cls(python=python, backend="pip", uv=uv)
        return cls(python=python, backend="uv", uv=uv)

    # --- komutlar ---------------------------------------------------------------

    def list_cmd(self, outdated: bool = False) -> list[str]:
        if self.backend == "uv":
            cmd = [self._uv(), "pip", "list", "--python", self.python, "--format", "json"]
        else:
            cmd = [self.python, "-m", "pip", "list", "--format", "json", "--disable-pip-version-check"]
        if outdated:
            cmd.append("--outdated")
        return cmd

    def install_cmd(self, specs: list[str], upgrade: bool = False) -> list[str]:
        if self.backend == "uv":
            cmd = [self._uv(), "pip", "install", "--python", self.python]
        else:
            cmd = [self.python, "-m", "pip", "install", "--disable-pip-version-check"]
        if upgrade:
            cmd.append("--upgrade")
        return cmd + list(specs)

    def uninstall_cmd(self, names: list[str]) -> list[str]:
        if self.backend == "uv":
            return [self._uv(), "pip", "uninstall", "--python", self.python, *names]
        return [self.python, "-m", "pip", "uninstall", "-y", "--disable-pip-version-check", *names]

    def _uv(self) -> str:
        if not self.uv:
            raise PackageError("uv bulunamadı")
        return self.uv

    # --- hızlı (beklenen) işlemler -----------------------------------------------

    def list_packages(self, timeout: float = 120) -> list[Package]:
        return parse_list_json(self._run(self.list_cmd(), timeout))

    def outdated(self, timeout: float = 300) -> dict[str, str]:
        """Paket adı (küçük harf) -> en son sürüm."""
        found = parse_list_json(self._run(self.list_cmd(outdated=True), timeout))
        return {p.name.lower(): p.latest for p in found if p.latest}

    def _run(self, cmd: list[str], timeout: float) -> str:
        try:
            result = proc.run(cmd, timeout=timeout)
        except OSError as exc:
            raise PackageError(str(exc)) from exc
        except proc.subprocess.TimeoutExpired as exc:
            raise PackageError(f"timeout: {' '.join(cmd)}") from exc
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip()
            if self.backend == "pip" and "No module named pip" in message:
                raise PackageError("no-pip")
            raise PackageError(message or f"exit {result.returncode}")
        return result.stdout
