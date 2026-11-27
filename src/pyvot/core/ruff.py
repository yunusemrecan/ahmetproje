"""Ruff: Python kod denetimi ve biçimlendirme.

Ruff, uv gibi uygulamayla birlikte gelir. Projede [tool.ruff] ayarları varsa
Ruff bunları kendiliğinden kullanır (çalışma klasörü proje olduğu için).
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from pyvot.core import proc

RUFF_EXE = "ruff.exe" if sys.platform == "win32" else "ruff"


def find_ruff() -> str | None:
    if getattr(sys, "frozen", False):
        for base in (Path(sys.executable).parent, Path(getattr(sys, "_MEIPASS", ""))):
            if (base / RUFF_EXE).is_file():
                return str(base / RUFF_EXE)
    try:
        from ruff.__main__ import find_ruff_bin  # type: ignore[import-not-found]

        path = find_ruff_bin()
        if path and Path(path).is_file():
            return str(path)
    except Exception:  # noqa: BLE001
        pass
    return shutil.which("ruff")


@dataclass
class Diagnostic:
    path: Path
    line: int
    column: int
    end_line: int
    end_column: int
    code: str
    message: str
    severity: str  # error | warning
    url: str = ""

    def to_marker(self) -> dict:
        return {
            "severity": self.severity,
            "message": self.message,
            "code": self.code,
            "line": self.line,
            "column": self.column,
            "endLine": self.end_line,
            "endColumn": self.end_column,
        }


def _severity(code: str | None) -> str:
    # Sözdizimi hataları (kodsuz) ve E9xx kesin hatadır; geri kalanlar uyarıdır.
    if not code or code.startswith("E9") or code in ("F821", "F822", "F823"):
        return "error"
    return "warning"


def parse_check_output(text: str, project: Path, stdin_path: Path | None = None) -> list[Diagnostic]:
    try:
        items = json.loads(text or "[]")
    except ValueError:
        return []
    found = []
    for item in items if isinstance(items, list) else []:
        location = item.get("location") or {}
        end = item.get("end_location") or location
        filename = item.get("filename") or ""
        path = stdin_path or (Path(filename) if Path(filename).is_absolute() else project / filename)
        code = item.get("code")
        found.append(
            Diagnostic(
                path=path,
                line=int(location.get("row") or 1),
                column=int(location.get("column") or 1),
                end_line=int(end.get("row") or location.get("row") or 1),
                end_column=int(end.get("column") or location.get("column") or 1),
                code=code or "",
                message=str(item.get("message") or ""),
                severity=_severity(code),
                url=str(item.get("url") or ""),
            )
        )
    return found


def check_text(ruff: str, project: Path, path: Path, text: str) -> list[Diagnostic]:
    """Kaydedilmemiş metni de denetleyebilmek için stdin'den gönderilir."""
    result = _run(ruff, ["check", "--output-format", "json", "--no-cache", "--stdin-filename", str(path), "-"], project, text)
    return parse_check_output(result.stdout, project, stdin_path=path)


def check_project(ruff: str, project: Path) -> list[Diagnostic]:
    result = _run(ruff, ["check", "--output-format", "json", "--no-cache", "."], project)
    return parse_check_output(result.stdout, project)


class FormatError(RuntimeError):
    pass


def format_text(ruff: str, project: Path, path: Path, text: str) -> str:
    result = _run(ruff, ["format", "--stdin-filename", str(path), "-"], project, text)
    if result.returncode != 0:
        raise FormatError((result.stderr or result.stdout).strip())
    return result.stdout


def _run(ruff: str, args: list[str], project: Path, stdin: str | None = None):  # noqa: ANN202
    import subprocess

    return subprocess.run(
        [ruff, *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(project),
        env=proc.child_env(),
        timeout=60,
        creationflags=proc.creation_flags(),
    )
