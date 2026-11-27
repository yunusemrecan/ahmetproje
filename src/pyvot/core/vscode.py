"""VS Code uyumu: .vscode dosyaları ve VS Code'u bulup açma."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
DOWNLOAD_URL = "https://code.visualstudio.com/download"
BASE_EXTENSIONS = ("ms-python.python", "ms-python.debugpy", "charliermarsh.ruff")
# Windows'ta Python, çıktısı konsola değil başka yere gidince cp1252 kullanır ve
# Türkçe karakterlerde çöker. UTF-8 kipi bunu önler.
UTF8_ENV = {"PYTHONUTF8": "1"}


def interpreter_setting(windows: bool = IS_WINDOWS) -> str:
    rel = ".venv/Scripts/python.exe" if windows else ".venv/bin/python"
    return "${workspaceFolder}/" + rel


def settings_json(windows: bool = IS_WINDOWS, tests: bool = False) -> dict:
    settings: dict = {
        "python.defaultInterpreterPath": interpreter_setting(windows),
        "python.terminal.activateEnvironment": True,
        "files.exclude": {"**/__pycache__": True, "**/.ruff_cache": True, "**/.pytest_cache": True},
        "terminal.integrated.env.windows": dict(UTF8_ENV),
        "[python]": {"editor.defaultFormatter": "charliermarsh.ruff"},
    }
    if tests:
        # VS Code'un Test panelinde pytest testleri görünsün.
        settings["python.testing.pytestEnabled"] = True
        settings["python.testing.unittestEnabled"] = False
        settings["python.testing.pytestArgs"] = ["tests"]
    return settings


def _open_browser(pattern: str, uri: str = "%s") -> dict:
    """Sunucu terminale adresini yazınca tarayıcıyı açar."""
    return {"pattern": pattern, "uriFormat": uri, "action": "openExternally"}


def launch_json(args: Iterable[str] = (), run: str = "script") -> dict:
    base: dict = {
        "type": "debugpy",
        "request": "launch",
        "cwd": "${workspaceFolder}",
        "console": "integratedTerminal",
        "env": dict(UTF8_ENV),
    }
    if run == "fastapi":
        config = {
            "name": "FastAPI (uvicorn)",
            **base,
            "module": "uvicorn",
            "args": ["main:app", "--reload"],
            "serverReadyAction": _open_browser(r"Uvicorn running on (https?://\S+)", "%s/docs"),
        }
    elif run == "flask":
        config = {
            "name": "Flask",
            **base,
            "module": "flask",
            "args": ["--app", "main", "run", "--debug", "--no-debugger"],
            "jinja": True,
            "serverReadyAction": _open_browser(r"Running on (https?://\S+)"),
        }
    else:
        config = {"name": "main.py", **base, "program": "${workspaceFolder}/main.py"}
    args = list(args)
    if args:
        config["args"] = args
    current = {
        "name": "Python: current file",
        "type": "debugpy",
        "request": "launch",
        "program": "${file}",
        "console": "integratedTerminal",
        "env": dict(UTF8_ENV),
    }
    return {"version": "0.2.0", "configurations": [config, current]}


def tasks_json() -> dict:
    return {
        "version": "2.0.0",
        "tasks": [
            {
                "label": "Run main.py",
                "type": "shell",
                "command": "${command:python.interpreterPath}",
                "args": ["main.py"],
                "options": {"env": dict(UTF8_ENV)},
                "group": {"kind": "build", "isDefault": True},
                "problemMatcher": [],
            }
        ],
    }


def extensions_json(extra: Iterable[str] = ()) -> dict:
    return {"recommendations": list(dict.fromkeys([*BASE_EXTENSIONS, *extra]))}


def write_files(
    project: Path,
    launch_args: Iterable[str] = (),
    extensions: Iterable[str] = (),
    *,
    run: str = "script",
    tests: bool = False,
) -> list[Path]:
    """Eksik .vscode dosyalarını yazar; var olanlara dokunmaz. Yazılanları döndürür."""
    folder = project / ".vscode"
    folder.mkdir(parents=True, exist_ok=True)
    files = {
        "settings.json": settings_json(tests=tests),
        "launch.json": launch_json(launch_args, run),
        "tasks.json": tasks_json(),
        "extensions.json": extensions_json(extensions),
    }
    written = []
    for name, content in files.items():
        path = folder / name
        if path.exists():
            continue
        path.write_text(json.dumps(content, indent=4, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        written.append(path)
    return written


# --- VS Code'u bulma ---------------------------------------------------------------


def candidate_paths(env: dict[str, str] | None = None) -> list[Path]:
    env = dict(os.environ) if env is None else env
    found: list[Path] = []
    if IS_WINDOWS:
        roots = [
            Path(env["LOCALAPPDATA"]) / "Programs" if env.get("LOCALAPPDATA") else None,
            Path(env["ProgramFiles"]) if env.get("ProgramFiles") else None,
            Path(env["ProgramFiles(x86)"]) if env.get("ProgramFiles(x86)") else None,
        ]
        for root in filter(None, roots):
            for folder in ("Microsoft VS Code", "Microsoft VS Code Insiders"):
                exe = "Code.exe" if "Insiders" not in folder else "Code - Insiders.exe"
                found.append(root / folder / exe)
    elif sys.platform == "darwin":
        found.append(Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"))
    return found


def find_vscode() -> str | None:
    for path in candidate_paths():
        if path.is_file():
            return str(path)
    for name in ("code", "code-insiders"):
        found = shutil.which(name)
        if found:
            return found
    return None


def open_folder(folder: Path, code: str | None = None) -> bool:
    """Klasörü VS Code'da açar. VS Code bulunamazsa False."""
    code = code or find_vscode()
    if not code:
        return False
    flags = 0
    if IS_WINDOWS:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        if code.lower().endswith((".cmd", ".bat")):
            flags |= subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        subprocess.Popen(
            [code, str(folder)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    except OSError:
        return False
    return True
