"""Bilgisayardaki Python kurulumlarını bulur.

Kaynaklar:
- ``py -0p`` (Windows Python başlatıcısı)
- Windows kayıt defteri (PEP 514)
- PATH
- bilinen kurulum klasörleri
- ``uv python list``
- kullanıcının elle eklediği yorumlayıcılar

Her aday gerçekten çalıştırılıp (probe) sürümü ve türü öğrenilir; aynı
kuruluma giden yollar tek kayıtta birleştirilir.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pyvot.core import proc
from pyvot.core.models import PythonInstall, path_key, same_path_key

IS_WINDOWS = sys.platform == "win32"

PROBE_CODE = (
    "import sys, json, platform, struct;"
    "print(json.dumps({"
    "'version': platform.python_version(),"
    "'implementation': platform.python_implementation().lower(),"
    "'bits': struct.calcsize('P') * 8,"
    "'machine': platform.machine(),"
    "'executable': sys.executable,"
    "'prefix': sys.prefix,"
    "'base_prefix': getattr(sys, 'base_prefix', sys.prefix)"
    "}))"
)


@dataclass
class Candidate:
    path: str
    source: str
    is_default: bool = False
    company: str = ""


# --- py başlatıcısı -----------------------------------------------------------

_PY_LINE = re.compile(r"^\s*(?P<tag>-\S+)\s+(?P<star>\*\s+)?(?P<path>.*\S)\s*$")


def parse_py_list(output: str) -> list[Candidate]:
    """``py -0p`` çıktısını ayrıştırır.

    Örnek satırlar::

         -V:3.13 *        C:\\Users\\a\\AppData\\Local\\Programs\\Python\\Python313\\python.exe
         -V:3.12          C:\\Python312\\python.exe
         -3.11-64         C:\\Python311\\python.exe
    """
    found: list[Candidate] = []
    for line in output.splitlines():
        match = _PY_LINE.match(line)
        if not match:
            continue
        path = match.group("path").strip().strip('"')
        if not (path.lower().endswith(".exe") or "\\" in path or "/" in path):
            continue  # "Active venv" gibi bilgi satırları
        found.append(Candidate(path, "py", is_default=bool(match.group("star"))))
    return found


def from_py_launcher() -> list[Candidate]:
    if not IS_WINDOWS:
        return []
    import shutil

    py = shutil.which("py")
    if not py:
        return []
    try:
        result = proc.run([py, "-0p"], timeout=15)
    except (OSError, proc.subprocess.TimeoutExpired):
        return []
    return parse_py_list(result.stdout)


# --- kayıt defteri (PEP 514) ----------------------------------------------------


def from_registry() -> list[Candidate]:
    if not IS_WINDOWS:
        return []
    import winreg  # type: ignore[import-not-found]

    found: list[Candidate] = []
    views = [
        (winreg.HKEY_CURRENT_USER, 0),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
    ]
    for hive, view in views:
        try:
            root = winreg.OpenKey(hive, r"Software\Python", 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with root:
            for company in _subkeys(winreg, root):
                if company == "PyLauncher":
                    continue
                try:
                    company_key = winreg.OpenKey(root, company)
                except OSError:
                    continue
                with company_key:
                    for tag in _subkeys(winreg, company_key):
                        exe = _registry_executable(winreg, company_key, tag)
                        if exe:
                            found.append(Candidate(exe, "registry", company=company))
    return found


def _subkeys(winreg, key) -> list[str]:  # noqa: ANN001
    names: list[str] = []
    index = 0
    while True:
        try:
            names.append(winreg.EnumKey(key, index))
        except OSError:
            return names
        index += 1


def _registry_executable(winreg, company_key, tag: str) -> str | None:  # noqa: ANN001
    try:
        with winreg.OpenKey(company_key, tag + r"\InstallPath") as install:
            try:
                exe, _ = winreg.QueryValueEx(install, "ExecutablePath")
                if exe:
                    return str(exe)
            except OSError:
                pass
            folder, _ = winreg.QueryValueEx(install, "")
            if folder:
                return os.path.join(str(folder), "python.exe")
    except OSError:
        return None
    return None


# --- PATH ve bilinen klasörler ----------------------------------------------------


def _path_names() -> list[str]:
    if IS_WINDOWS:
        return ["python.exe", "python3.exe"]
    return ["python3", "python"] + [f"python3.{minor}" for minor in range(8, 16)]


def from_path(path_value: str | None = None) -> list[Candidate]:
    found: list[Candidate] = []
    path_value = os.environ.get("PATH", "") if path_value is None else path_value
    for folder in path_value.split(os.pathsep):
        folder = folder.strip().strip('"')
        if not folder:
            continue
        for name in _path_names():
            candidate = os.path.join(folder, name)
            if os.path.isfile(candidate) or os.path.islink(candidate):
                source = "store" if "windowsapps" in candidate.lower() else "path"
                found.append(Candidate(candidate, source))
    return found


def from_known_folders() -> list[Candidate]:
    patterns: list[str] = []
    if IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            patterns.append(os.path.join(local, "Programs", "Python", "Python3*", "python.exe"))
        for root in filter(None, {os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")}):
            patterns.append(os.path.join(root, "Python3*", "python.exe"))
        patterns.append(os.path.join(os.environ.get("SystemDrive", "C:") + os.sep, "Python3*", "python.exe"))
    else:
        patterns += ["/usr/bin/python3.*", "/usr/local/bin/python3.*", "/opt/homebrew/bin/python3.*"]
    found: list[Candidate] = []
    for pattern in patterns:
        for match in glob.glob(pattern):
            if IS_WINDOWS or re.fullmatch(r"python3\.\d+", os.path.basename(match)):
                found.append(Candidate(match, "folder"))
    return found


# --- uv --------------------------------------------------------------------------


def parse_uv_list(output: str) -> list[Candidate]:
    try:
        items = json.loads(output or "[]")
    except json.JSONDecodeError:
        return []
    found: list[Candidate] = []
    for item in items if isinstance(items, list) else []:
        path = item.get("path") if isinstance(item, dict) else None
        if path:
            found.append(Candidate(str(path), "uv"))
    return found


def from_uv(uv: str | None) -> list[Candidate]:
    if not uv:
        return []
    try:
        result = proc.run(
            [uv, "python", "list", "--only-installed", "--output-format", "json"], timeout=30
        )
    except (OSError, proc.subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return parse_uv_list(result.stdout)


# --- çalıştırıp doğrulama ---------------------------------------------------------


def probe(executable: str, timeout: float = 15) -> PythonInstall | None:
    """Yorumlayıcıyı çalıştırıp bilgilerini alır. Çalışmazsa None."""
    try:
        result = proc.run([executable, "-I", "-c", PROBE_CODE], timeout=timeout)
    except (OSError, proc.subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        data = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    return PythonInstall(
        executable=executable,
        version=str(data.get("version", "?")),
        implementation=str(data.get("implementation", "cpython")),
        bits=int(data.get("bits", 64)),
        machine=str(data.get("machine", "")),
        prefix=str(data.get("prefix", "")),
        base_prefix=str(data.get("base_prefix", "")),
        real_executable=str(data.get("executable") or ""),
    )


def merge(candidates: Iterable[Candidate], probes: dict[str, PythonInstall | None]) -> list[PythonInstall]:
    """Adayları aynı kuruluma göre birleştirir.

    ``probes`` aday yolunun same_path_key değerinden probe sonucuna giden eşlemedir.
    """
    groups: dict[str, PythonInstall] = {}
    first_path_seen = False
    for cand in candidates:
        info = probes.get(same_path_key(cand.path))
        if info is None:
            continue
        real = info.real_executable or cand.path
        # Linux'ta venv'in python'u ana yorumlayıcıya sembolik bağdır; prefix'i
        # anahtara katarak venv'leri ana kurulumdan ayrı tutuyoruz.
        key = path_key(real) + "|" + os.path.normcase(info.prefix)
        install = groups.get(key)
        if install is None:
            install = PythonInstall(
                executable=info.executable,
                version=info.version,
                implementation=info.implementation,
                bits=info.bits,
                machine=info.machine,
                prefix=info.prefix,
                base_prefix=info.base_prefix,
                real_executable=info.real_executable,
            )
            groups[key] = install
        install.sources.add(cand.source)
        install.is_default = install.is_default or cand.is_default
        if cand.company and not install.company:
            install.company = cand.company
        if cand.source == "path" and not first_path_seen:
            install.first_on_path = True
            first_path_seen = True
    return sorted(groups.values(), key=lambda i: (tuple(-n for n in i.version_tuple), i.executable.lower()))


def discover(uv: str | None = None, extra: Iterable[str] = ()) -> list[PythonInstall]:
    candidates: list[Candidate] = []
    candidates += from_py_launcher()
    candidates += from_registry()
    candidates += from_path()
    candidates += from_known_folders()
    candidates += from_uv(uv)
    candidates += [Candidate(path, "user") for path in extra]

    unique: dict[str, str] = {}
    for cand in candidates:
        unique.setdefault(same_path_key(cand.path), cand.path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = dict(zip(unique.keys(), pool.map(probe, unique.values()), strict=True))
    return merge(candidates, results)


def interpreter_in_folder(folder: str) -> str | None:
    """Bir sanal ortam ya da proje klasöründeki Python yorumlayıcısını bulur."""
    rel_paths = (
        ["Scripts/python.exe", "python.exe", ".venv/Scripts/python.exe", "venv/Scripts/python.exe"]
        if IS_WINDOWS
        else ["bin/python", "bin/python3", ".venv/bin/python", "venv/bin/python"]
    )
    for rel in rel_paths:
        candidate = os.path.join(folder, *rel.split("/"))
        if os.path.isfile(candidate):
            return candidate
    return None
