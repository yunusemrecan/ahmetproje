from __future__ import annotations

import os
import sys

from pyvot.core import discovery
from pyvot.core.discovery import Candidate
from pyvot.core.models import PythonInstall, same_path_key


def test_parse_py_list_new_format():
    output = (
        " -V:3.13 *        C:\\Users\\a\\AppData\\Local\\Programs\\Python\\Python313\\python.exe\n"
        " -V:3.12          C:\\Program Files\\Python312\\python.exe\n"
        " -V:ContinuumAnalytics/Anaconda39-64 C:\\Anaconda3\\python.exe\n"
    )
    found = discovery.parse_py_list(output)
    assert [c.path for c in found] == [
        "C:\\Users\\a\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
        "C:\\Program Files\\Python312\\python.exe",
        "C:\\Anaconda3\\python.exe",
    ]
    assert [c.is_default for c in found] == [True, False, False]
    assert {c.source for c in found} == {"py"}


def test_parse_py_list_old_format_and_noise():
    output = (
        "Installed Pythons found by py Launcher for Windows\n"
        " -3.11-64 *     C:\\Python311\\python.exe\n"
        " -3.10-32       C:\\Python310-32\\python.exe\n"
        "  *               Active venv\n"
        "\n"
    )
    found = discovery.parse_py_list(output)
    assert [c.path for c in found] == ["C:\\Python311\\python.exe", "C:\\Python310-32\\python.exe"]
    assert found[0].is_default


def test_parse_uv_list():
    output = '[{"key": "cpython-3.13", "path": "/usr/bin/python3.13"}, {"key": "x", "path": null}]'
    assert [c.path for c in discovery.parse_uv_list(output)] == ["/usr/bin/python3.13"]
    assert discovery.parse_uv_list("not json") == []


def _install(path: str, version: str, prefix: str, base: str | None = None) -> PythonInstall:
    return PythonInstall(
        executable=path, version=version, prefix=prefix, base_prefix=base or prefix, real_executable=path
    )


def test_merge_deduplicates_and_flags(tmp_path):
    a = str(tmp_path / "a" / "python")
    b = str(tmp_path / "b" / "python")
    probes = {
        same_path_key(a): _install(a, "3.12.1", str(tmp_path / "a")),
        same_path_key(b): _install(b, "3.13.0", str(tmp_path / "b")),
    }
    candidates = [
        Candidate(a, "path"),
        Candidate(a, "py", is_default=True),
        Candidate(b, "path"),
        Candidate(str(tmp_path / "missing"), "path"),  # çalışmayan aday atlanır
    ]
    merged = discovery.merge(candidates, probes)
    assert [i.version for i in merged] == ["3.13.0", "3.12.1"]  # yeni sürüm önce
    older = merged[1]
    assert older.sources == {"path", "py"}
    assert older.is_default and older.first_on_path
    assert not merged[0].first_on_path


def test_merge_keeps_venv_separate_from_base(tmp_path):
    """Linux'ta venv/bin/python ana yorumlayıcıya bağdır; yine de ayrı kayıt olmalı."""
    base = str(tmp_path / "usr" / "python")
    venv = str(tmp_path / "env" / "bin" / "python")
    probes = {
        same_path_key(base): _install(base, "3.12.0", str(tmp_path / "usr")),
        same_path_key(venv): PythonInstall(
            executable=venv,
            version="3.12.0",
            prefix=str(tmp_path / "env"),
            base_prefix=str(tmp_path / "usr"),
            real_executable=base,  # bağ çözülünce aynı dosya
        ),
    }
    merged = discovery.merge([Candidate(base, "path"), Candidate(venv, "user")], probes)
    assert len(merged) == 2
    assert sum(i.is_venv for i in merged) == 1


def test_probe_current_interpreter():
    info = discovery.probe(sys.executable)
    assert info is not None
    assert info.version.startswith(f"{sys.version_info.major}.{sys.version_info.minor}")
    assert info.bits in (32, 64)


def test_probe_rejects_non_python(tmp_path):
    fake = tmp_path / "not-python"
    fake.write_text("hello")
    assert discovery.probe(str(fake)) is None


def test_discover_includes_extra_interpreter():
    found = discovery.discover(uv=None, extra=[sys.executable])
    # Aynı yorumlayıcı PATH'te başka adla da olabilir; elle eklenen yol gösterilmeli.
    assert any(same_path_key(i.executable) == same_path_key(sys.executable) for i in found)


def test_merge_prefers_user_path_for_aliases(tmp_path):
    real = str(tmp_path / "python3.13")
    alias = str(tmp_path / "python3")
    info = _install(real, "3.13.0", str(tmp_path))
    probes = {same_path_key(alias): info, same_path_key(real): info}
    [merged] = discovery.merge([Candidate(alias, "path"), Candidate(real, "user")], probes)
    assert merged.executable == real
    assert merged.sources == {"path", "user"}


def test_from_path_finds_interpreters(tmp_path):
    name = "python.exe" if sys.platform == "win32" else "python3"
    (tmp_path / name).write_text("")
    found = discovery.from_path(str(tmp_path))
    assert [os.path.basename(c.path) for c in found] == [name]


def test_interpreter_in_folder(tmp_path):
    rel = ("Scripts", "python.exe") if sys.platform == "win32" else ("bin", "python")
    folder = tmp_path / "project" / ".venv"
    (folder / rel[0]).mkdir(parents=True)
    (folder / rel[0] / rel[1]).write_text("")
    assert discovery.interpreter_in_folder(str(tmp_path / "project")) == str(folder / rel[0] / rel[1])
    assert discovery.interpreter_in_folder(str(tmp_path)) is None


def test_version_tuple_and_label():
    install = PythonInstall(executable="/x/python", version="3.13.0rc2", prefix="/x", base_prefix="/x")
    assert install.version_tuple == (3, 13, 2)
    assert install.short_version == "3.13"
    assert not install.is_venv
    assert "3.13.0rc2" in install.label()
