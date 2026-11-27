"""Proje klasöründe, sanal ortamı etkin bir terminal açar.

Windows'ta Activate.ps1 çalıştırmak çoğu bilgisayarda "betik çalıştırma
devre dışı" hatası verir. Bunun yerine ortam değişkenleri doğrudan
ayarlanır ve komut -EncodedCommand ile verilir (tırnak sorunu da olmaz).
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

Which = Callable[[str], str | None]


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def activation_script(venv: Path | None, windows: bool = True) -> str:
    """PowerShell için ortamı etkinleştiren komutlar."""
    if venv is None:
        return ""
    scripts = str(venv / ("Scripts" if windows else "bin"))
    sep = ";" if windows else ":"
    return "; ".join(
        [
            f"$env:VIRTUAL_ENV = {_ps_quote(str(venv))}",
            f"$env:PATH = {_ps_quote(scripts + sep)} + $env:PATH",
            "Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue",
            "function global:prompt { '(.venv) PS ' + $(Get-Location) + '> ' }",
        ]
    )


def encode_command(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def windows_command(folder: Path, venv: Path | None, which: Which = shutil.which) -> list[str]:
    shell = which("pwsh") or which("powershell") or "powershell.exe"
    shell_args = [shell, "-NoLogo", "-NoExit"]
    script = activation_script(venv, windows=True)
    if script:
        shell_args += ["-EncodedCommand", encode_command(script)]
    wt = which("wt")
    if wt:
        return [wt, "-w", "new", "-d", str(folder), *shell_args]
    return shell_args


def open_terminal(folder: Path, venv: Path | None) -> bool:
    if sys.platform == "win32":
        cmd = windows_command(folder, venv)
        flags = 0 if Path(cmd[0]).stem.lower() == "wt" else subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
        try:
            subprocess.Popen(cmd, cwd=str(folder), creationflags=flags, close_fds=True)
        except OSError:
            return False
        return True
    # Linux/macOS: geliştirme kolaylığı için basit destek.
    env = dict(os.environ)
    if venv is not None:
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH"] = str(venv / "bin") + os.pathsep + env.get("PATH", "")
    if sys.platform == "darwin":
        cmd = ["open", "-a", "Terminal", str(folder)]
    else:
        term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal") or shutil.which("konsole")
        if not term:
            return False
        cmd = [term]
    try:
        subprocess.Popen(cmd, cwd=str(folder), env=env, close_fds=True)
    except OSError:
        return False
    return True
