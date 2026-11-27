"""VS Code'un launch.json dosyasını okuyup aynı programı çalıştırmak için komut üretir.

Böylece Pyvot'taki "Çalıştır (F5)" ile VS Code'daki F5 aynı şeyi yapar.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pyvot.core import proc
from pyvot.core.projects import venv_python

TRACEBACK_RE = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)')
# "dosya.py:12:5: E501 ..." (ruff, pytest, derleyici çıktıları)
COLON_RE = re.compile(r"(?P<path>(?:[A-Za-z]:)?[^\s:\"']+\.(?:py|pyi|toml|json|cfg|ini|txt)):(?P<line>\d+)(?::(?P<col>\d+))?")


class LaunchError(ValueError):
    pass


def strip_jsonc(text: str) -> str:
    """JSON-with-comments: // ve /* */ yorumlarını ve sondaki virgülleri kaldırır."""
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            out.append(ch)
            i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def read_launch_configs(project: Path) -> list[dict]:
    path = project / ".vscode" / "launch.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise LaunchError(f"launch.json: {exc}") from exc
    configs = data.get("configurations") if isinstance(data, dict) else None
    return [c for c in configs or [] if isinstance(c, dict)]


@dataclass
class RunSpec:
    name: str
    cmd: list[str]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)  # ek ortam değişkenleri
    ready_pattern: str | None = None  # serverReadyAction.pattern
    ready_uri: str = "%s"


def interpreter(project: Path) -> str:
    """Projenin .venv'indeki Python; yoksa PATH'teki python."""
    exe = venv_python(project / ".venv")
    if exe.exists():
        return str(exe)
    # Paketlenmiş uygulamada sys.executable Pyvot.exe'dir; o yüzden PATH'e bırak.
    return "python" if getattr(sys, "frozen", False) else sys.executable


def _substitute(value: str, project: Path, current: Path | None, python: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "workspaceFolder":
            return str(project)
        if name == "workspaceFolderBasename":
            return project.name
        if name == "file" and current is not None:
            return str(current)
        if name == "fileDirname" and current is not None:
            return str(current.parent)
        if name == "fileBasename" and current is not None:
            return current.name
        if name == "fileBasenameNoExtension" and current is not None:
            return current.stem
        if name == "relativeFile" and current is not None:
            return os.path.relpath(current, project)
        if name.startswith("env:"):
            return os.environ.get(name[4:], "")
        if name == "command:python.interpreterPath":
            return python
        if name == "pathSeparator":
            return os.sep
        return match.group(0)

    return re.sub(r"\$\{([^}]+)\}", replace, value)


def spec_from_config(config: dict, project: Path, current: Path | None = None) -> RunSpec:
    python = interpreter(project)

    def sub(value: object) -> str:
        return _substitute(str(value), project, current, python)

    if config.get("request", "launch") != "launch":
        raise LaunchError("attach")
    args = config.get("args") or []
    if isinstance(args, str):
        args = args.split()
    args = [sub(a) for a in args]
    if config.get("module"):
        cmd = [python, "-m", sub(config["module"]), *args]
    elif config.get("program"):
        program = sub(config["program"])
        if "${file}" in str(config["program"]) and current is None:
            raise LaunchError("no-file")
        cmd = [python, program, *args]
    else:
        raise LaunchError("no-program")
    cwd = Path(sub(config.get("cwd") or "${workspaceFolder}"))
    env = {str(k): sub(v) for k, v in (config.get("env") or {}).items()}
    ready = config.get("serverReadyAction") or {}
    return RunSpec(
        name=str(config.get("name") or cmd[1]),
        cmd=cmd,
        cwd=cwd,
        env=env,
        ready_pattern=ready.get("pattern") if isinstance(ready, dict) else None,
        ready_uri=str(ready.get("uriFormat") or "%s") if isinstance(ready, dict) else "%s",
    )


def project_spec(project: Path, current: Path | None = None) -> RunSpec:
    """F5: launch.json'daki ilk uygun ayar; yoksa main.py ya da açık dosya."""
    for config in read_launch_configs(project):
        if config.get("type") in ("debugpy", "python") and config.get("request", "launch") == "launch":
            try:
                return spec_from_config(config, project, current)
            except LaunchError:
                continue
    main = project / "main.py"
    if main.is_file():
        return file_spec(project, main)
    if current is not None:
        return file_spec(project, current)
    raise LaunchError("nothing-to-run")


def file_spec(project: Path, file: Path) -> RunSpec:
    """Açık dosyayı çalıştır."""
    return RunSpec(name=file.name, cmd=[interpreter(project), str(file)], cwd=project, env={"PYTHONUTF8": "1"})


def run_env(spec: RunSpec) -> dict[str, str]:
    env = proc.child_env({"PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"})
    env.update(spec.env)
    # Projenin sanal ortamı etkin gibi davransın (alt süreçler de onu bulsun).
    exe = Path(spec.cmd[0])
    if exe.parent.name in ("Scripts", "bin") and (exe.parent.parent / "pyvenv.cfg").is_file():
        env["VIRTUAL_ENV"] = str(exe.parent.parent)
        env["PATH"] = str(exe.parent) + os.pathsep + env.get("PATH", "")
    return env


def find_locations(text: str, base: Path) -> list[tuple[int, int, Path, int, int]]:
    """Metindeki dosya:satır konumları: (başlangıç, bitiş, yol, satır, sütun).

    Yalnızca gerçekten var olan dosyalar döner; göreli yollar ``base``'e göredir.
    """
    found: list[tuple[int, int, Path, int, int]] = []
    taken: list[range] = []
    for regex in (TRACEBACK_RE, COLON_RE):
        for match in regex.finditer(text):
            span = range(match.start(), match.end())
            if any(span.start < t.stop and t.start < span.stop for t in taken):
                continue
            raw = match.group("path")
            path = Path(raw)
            if not path.is_absolute():
                path = base / path
            if not path.is_file():
                continue
            column = int(match.groupdict().get("col") or 1)
            found.append((match.start(), match.end(), path, int(match.group("line")), column))
            taken.append(span)
    return sorted(found)
