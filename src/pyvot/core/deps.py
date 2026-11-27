"""Bir projenin bağımlılıklarını uv ile yönetir.

Ana bağımlılıklar ``[project].dependencies``, geliştirme bağımlılıkları
``[dependency-groups].dev`` (uv'nin ``--dev`` için kullandığı yer) içinde
durur. Eski ``[tool.uv].dev-dependencies`` da okunur.
"""

from __future__ import annotations

import re
import shutil
import threading
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import InvalidVersion, Version

from pyvot import i18n
from pyvot.core import proc
from pyvot.core.packages import PackageManager
from pyvot.core.projects import Cancelled, ProjectError, inspect, read_pyvenv_cfg, venv_python
from pyvot.core.pypi import normalize

Log = Callable[[str], None]
MAIN, DEV = "main", "dev"


@dataclass
class Dependency:
    name: str
    spec: str  # pyproject'teki tam yazım, ör. "requests>=2.31"
    group: str  # MAIN | DEV
    installed: str | None = None
    latest: str | None = None

    @property
    def constraint(self) -> str:
        try:
            req = Requirement(self.spec)
        except InvalidRequirement:
            return ""
        text = str(req.specifier)
        if req.extras:
            text = f"[{','.join(sorted(req.extras))}] {text}".strip()
        return text

    def latest_allowed(self) -> bool | None:
        """En son sürüm mevcut sürüm aralığına giriyor mu? Bilinmiyorsa None."""
        if not self.latest:
            return None
        try:
            return Requirement(self.spec).specifier.contains(Version(self.latest), prereleases=True)
        except (InvalidRequirement, InvalidVersion):
            return None

    @property
    def outdated(self) -> bool:
        return bool(self.latest and self.installed and self.latest != self.installed)


# --- okuma -----------------------------------------------------------------------------


def _parse(specs: list, group: str) -> list[Dependency]:
    found = []
    for spec in specs:
        if not isinstance(spec, str):
            continue
        try:
            name = Requirement(spec).name
        except InvalidRequirement:
            name = re.split(r"[\s<>=!~;\[]", spec, maxsplit=1)[0]
        found.append(Dependency(name=name, spec=spec, group=group))
    return found


def read_dependencies(project: Path) -> list[Dependency]:
    try:
        data = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    main = (data.get("project") or {}).get("dependencies") or []
    dev = list((data.get("dependency-groups") or {}).get("dev") or [])
    dev += ((data.get("tool") or {}).get("uv") or {}).get("dev-dependencies") or []
    return _parse(main, MAIN) + _parse(dev, DEV)


def requires_python(project: Path) -> str:
    try:
        data = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    return str((data.get("project") or {}).get("requires-python") or "")


def python_satisfies(version: str, requirement: str) -> bool:
    if not requirement:
        return True
    from packaging.specifiers import InvalidSpecifier, SpecifierSet

    try:
        return SpecifierSet(requirement).contains(Version(version), prereleases=True)
    except (InvalidSpecifier, InvalidVersion):
        return True


def set_requires_python(project: Path, version: str) -> None:
    """requires-python değerini ">=X.Y" yapar (satır yoksa ekler)."""
    path = project / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    major_minor = ".".join(version.split(".")[:2])
    line = f'requires-python = ">={major_minor}"'
    new, count = re.subn(r'(?m)^requires-python\s*=\s*"[^"]*"\s*$', line, text)
    if count == 0:
        new, count = re.subn(r"(?m)^\[project\]\s*$", "[project]\n" + line, text, count=1)
    if count:
        path.write_text(new, encoding="utf-8", newline="\n")


def with_versions(project: Path, deps: list[Dependency], uv: str | None) -> list[Dependency]:
    """Kurulu sürümleri .venv'den doldurur (ağ gerekmez)."""
    exe = venv_python(project / ".venv")
    if not exe.exists() or not deps:
        return deps
    try:
        installed = {normalize(p.name): p.version for p in PackageManager.create(str(exe), uv).list_packages()}
    except Exception:  # noqa: BLE001 - sürüm bilgisi olmadan da gösterilebilir
        return deps
    for dep in deps:
        dep.installed = installed.get(normalize(dep.name))
    return deps


def with_latest(project: Path, deps: list[Dependency], uv: str | None) -> list[Dependency]:
    """PyPI'deki en son sürümleri doldurur (ağ gerekir)."""
    exe = venv_python(project / ".venv")
    if not exe.exists():
        return deps
    latest = PackageManager.create(str(exe), uv).outdated()
    for dep in deps:
        dep.latest = latest.get(dep.name.lower()) or latest.get(normalize(dep.name))
    return deps


def sync_state(project: Path, uv: str | None) -> str:
    """"ok", "unsynced" ya da "unknown" (pyproject yok, uv yok, kontrol edilemedi)."""
    if not uv or not (project / "pyproject.toml").is_file():
        return "unknown"
    if not (project / ".venv").exists():
        return "unsynced"
    # İki kontrol gerekir: "uv sync --check" yalnızca uv.lock eskidiğinde (ortam
    # değişmeyecekse) 0 döner; "uv lock --check" kilit dosyasının güncelliğine bakar.
    for args in (["lock", "--check", "--offline"], ["sync", "--check", "--offline"]):
        try:
            result = proc.run([uv, *args], cwd=str(project), timeout=60)
        except (OSError, proc.subprocess.TimeoutExpired):
            return "unknown"
        if result.returncode != 0:
            return "unsynced"
    return "ok"


# --- işlemler ---------------------------------------------------------------------------


class _Runner:
    def __init__(self, project: Path, uv: str | None, log: Log, cancel: threading.Event | None) -> None:
        if not uv:
            raise ProjectError(i18n.tr("project.err_no_uv"))
        self.project, self.uv, self.log, self.cancel = project, uv, log, cancel

    def __call__(self, *args: str) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled(i18n.tr("project.cancelled"))
        cmd = [self.uv, *args]
        self.log("$ uv " + " ".join(args))
        try:
            code = proc.stream(cmd, self.log, cwd=str(self.project), cancel=self.cancel)
        except OSError as exc:
            raise ProjectError(str(exc)) from exc
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled(i18n.tr("project.cancelled"))
        if code != 0:
            raise ProjectError(i18n.tr("project.err_step", code=code))

    def done(self) -> None:
        self.log(i18n.tr("project.done"))


def _group_flag(dev: bool) -> list[str]:
    return ["--dev"] if dev else []


def add(project: Path, specs: list[str], dev: bool, uv: str | None, *, log: Log, cancel=None) -> None:  # noqa: ANN001
    run = _Runner(project, uv, log, cancel)
    run("add", *_group_flag(dev), *specs)
    run.done()


def remove(project: Path, names: list[str], dev: bool, uv: str | None, *, log: Log, cancel=None) -> None:  # noqa: ANN001
    run = _Runner(project, uv, log, cancel)
    run("remove", *_group_flag(dev), *names)
    run.done()


def upgrade(project: Path, names: list[str], uv: str | None, *, log: Log, cancel=None) -> None:  # noqa: ANN001
    """Sürüm aralığının içinde günceller; names boşsa hepsini."""
    run = _Runner(project, uv, log, cancel)
    if names:
        args = []
        for name in names:
            args += ["--upgrade-package", name]
        run("lock", *args)
    else:
        run("lock", "--upgrade")
    run("sync")
    run.done()


def upgrade_major(project: Path, dep: Dependency, uv: str | None, *, log: Log, cancel=None) -> None:  # noqa: ANN001
    """Sürüm aralığını en son sürüme taşır: "pandas>=2" -> "pandas>=3.1"."""
    if not dep.latest:
        raise ProjectError(i18n.tr("deps.no_latest"))
    try:
        req = Requirement(dep.spec)
        extras = f"[{','.join(sorted(req.extras))}]" if req.extras else ""
        marker = f"; {req.marker}" if req.marker else ""
    except InvalidRequirement:
        extras = marker = ""
    run = _Runner(project, uv, log, cancel)
    run("add", *_group_flag(dep.group == DEV), f"{dep.name}{extras}>={dep.latest}{marker}")
    run.done()


def sync(project: Path, uv: str | None, *, log: Log, cancel=None) -> None:  # noqa: ANN001
    run = _Runner(project, uv, log, cancel)
    run("sync")
    run.done()


def rebuild_env(project: Path, python: str, uv: str | None, *, log: Log, cancel=None) -> None:  # noqa: ANN001
    """.venv'i silip seçilen Python ile yeniden kurar ve paketleri yükler."""
    run = _Runner(project, uv, log, cancel)
    info = inspect(project)
    venv = info.venv or project / ".venv"
    version = _probe_version(python)
    if version is None:
        raise ProjectError(i18n.tr("pythons.add_invalid", path=python))
    required = requires_python(project) if info.has_pyproject else ""
    if not python_satisfies(version, required):
        # Eski ortamı silmeden önce kontrol et; yoksa proje ortamsız kalır.
        raise ProjectError(i18n.tr("deps.python_incompatible", version=version, required=required))
    if venv.exists():
        log(i18n.tr("deps.removing_venv", path=str(venv)))
        try:
            shutil.rmtree(venv)
        except OSError as exc:
            raise ProjectError(i18n.tr("deps.venv_in_use", error=str(exc))) from exc
    python_version_file = project / ".python-version"
    if python_version_file.exists():
        # uv bu dosyadaki sürümü tercih eder; seçilen sürümle uyumlu olsun.
        python_version_file.write_text(".".join(version.split(".")[:2]) + "\n", encoding="utf-8")
    if info.has_pyproject:
        run("sync", "--python", python)
    else:
        run("venv", "--python", python, str(venv))
        if info.has_requirements:
            run("pip", "install", "--python", str(venv_python(venv)), "-r", "requirements.txt")
    run.done()


def _probe_version(python: str) -> str | None:
    from pyvot.core.discovery import probe

    info = probe(python)
    return info.version if info else None


def convert_requirements(project: Path, python: str | None, uv: str | None, *, log: Log, cancel=None) -> None:  # noqa: ANN001
    """requirements.txt'deki paketleri pyproject.toml'a aktarır (dosya silinmez)."""
    run = _Runner(project, uv, log, cancel)
    pyproject = project / "pyproject.toml"
    if not pyproject.exists():
        from pyvot.core.projects import package_name

        version = (read_pyvenv_cfg(project / ".venv").get("version_info") or "").strip()
        lines = ["[project]", f'name = "{package_name(project.name)}"', 'version = "0.1.0"']
        if version:
            lines.append(f'requires-python = ">={".".join(version.split(".")[:2])}"')
        lines.append("dependencies = []")
        pyproject.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        log(i18n.tr("deps.pyproject_created"))
    args = ["add", "-r", "requirements.txt"]
    if python and not (project / ".venv").exists():
        args += ["--python", python]
    run(*args)
    run.done()


def export_requirements(project: Path, uv: str | None, *, log: Log, cancel=None) -> Path:  # noqa: ANN001
    run = _Runner(project, uv, log, cancel)
    out = project / "requirements.txt"
    run("export", "--format", "requirements-txt", "--no-hashes", "--no-dev", "--no-header", "--no-emit-project", "-o", str(out))
    run.done()
    return out
