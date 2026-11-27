from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pyvot.core import files, launch, projects, ruff

# --- launch.json -----------------------------------------------------------------------------


def test_strip_jsonc_keeps_strings_and_removes_comments():
    text = '{\n // yorum\n "url": "http://a//b", /* blok */ "k": [1, 2,],\n "s": "a/*b*/c", }'
    assert json.loads(launch.strip_jsonc(text)) == {"url": "http://a//b", "k": [1, 2], "s": "a/*b*/c"}


def test_strip_jsonc_escaped_quotes():
    assert json.loads(launch.strip_jsonc('{"a": "x\\" // not a comment"}')) == {"a": 'x" // not a comment'}


def _write_launch(project: Path, configs: list[dict], comment: bool = True) -> None:
    (project / ".vscode").mkdir(parents=True, exist_ok=True)
    body = json.dumps({"version": "0.2.0", "configurations": configs}, indent=2)
    if comment:
        body = "// Pyvot testi\n" + body
    (project / ".vscode" / "launch.json").write_text(body, encoding="utf-8")


def test_module_config_with_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("PYVOT_TEST_PORT", "8123")
    _write_launch(
        tmp_path,
        [
            {"name": "attach", "type": "debugpy", "request": "attach"},
            {
                "name": "API",
                "type": "debugpy",
                "request": "launch",
                "module": "uvicorn",
                "args": ["main:app", "--port", "${env:PYVOT_TEST_PORT}"],
                "cwd": "${workspaceFolder}/src",
                "env": {"APP": "${workspaceFolderBasename}"},
                "serverReadyAction": {"pattern": "running on (\\S+)", "uriFormat": "%s/docs"},
            },
        ],
    )
    spec = launch.project_spec(tmp_path)
    assert spec.name == "API"
    assert spec.cmd[1:] == ["-m", "uvicorn", "main:app", "--port", "8123"]
    assert spec.cwd == tmp_path / "src"
    assert spec.env == {"APP": tmp_path.name}
    assert spec.ready_pattern == "running on (\\S+)" and spec.ready_uri == "%s/docs"


def test_program_config_uses_current_file(tmp_path):
    _write_launch(tmp_path, [{"type": "debugpy", "request": "launch", "program": "${file}"}])
    current = tmp_path / "x.py"
    current.write_text("", encoding="utf-8")
    assert launch.project_spec(tmp_path, current).cmd[1] == str(current)
    # Açık dosya yoksa ${file} kullanan ayar atlanır; main.py da yoksa çalıştırılacak şey yok.
    with pytest.raises(launch.LaunchError):
        launch.project_spec(tmp_path, None)


def test_fallback_to_main_py(tmp_path):
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    spec = launch.project_spec(tmp_path)
    assert spec.cmd[1] == str(tmp_path / "main.py") and spec.cwd == tmp_path


def test_broken_launch_json(tmp_path):
    (tmp_path / ".vscode").mkdir()
    (tmp_path / ".vscode" / "launch.json").write_text("{bozuk", encoding="utf-8")
    with pytest.raises(launch.LaunchError):
        launch.read_launch_configs(tmp_path)


def test_interpreter_prefers_project_venv(tmp_path):
    exe = projects.venv_python(tmp_path / ".venv")
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    assert launch.interpreter(tmp_path) == str(exe)
    env = launch.run_env(launch.file_spec(tmp_path, tmp_path / "a.py"))
    assert env["VIRTUAL_ENV"] == str(tmp_path / ".venv")
    assert env["PYTHONUNBUFFERED"] == "1" and env["PYTHONUTF8"] == "1"


def test_find_locations(tmp_path):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "mod.py"
    target.write_text("", encoding="utf-8")
    text = (
        f'  File "{target}", line 12, in f\n'
        "pkg/mod.py:3:7: F401 unused\n"
        '  File "/does/not/exist.py", line 2\n'
    )
    found = [(path, line, col) for _s, _e, path, line, col in launch.find_locations(text, tmp_path)]
    assert found == [(target, 12, 1), (target, 3, 7)]


def test_file_spec_runs_for_real(tmp_path):
    from pyvot.core import proc

    script = tmp_path / "ç.py"
    script.write_text("print('Merhaba, Dünya')\n", encoding="utf-8")
    spec = launch.file_spec(tmp_path, script)
    spec.cmd[0] = sys.executable
    result = proc.run(spec.cmd, cwd=str(spec.cwd), env=launch.run_env(spec))
    assert result.stdout.strip() == "Merhaba, Dünya"


# --- Ruff ------------------------------------------------------------------------------------


def test_parse_check_output(tmp_path):
    text = json.dumps(
        [
            {"code": "F401", "message": "`os` imported but unused", "filename": "a.py",
             "location": {"row": 1, "column": 8}, "end_location": {"row": 1, "column": 10}, "url": "u"},
            {"code": None, "message": "SyntaxError: x", "filename": str(tmp_path / "b.py"),
             "location": {"row": 2, "column": 1}, "end_location": None},
        ]
    )
    first, second = ruff.parse_check_output(text, tmp_path)
    assert (first.path, first.code, first.severity, first.end_column) == (tmp_path / "a.py", "F401", "warning", 10)
    assert (second.path, second.severity, second.end_line) == (tmp_path / "b.py", "error", 2)
    assert first.to_marker()["line"] == 1
    assert ruff.parse_check_output("not json", tmp_path) == []


@pytest.fixture(scope="module")
def ruff_bin():
    found = ruff.find_ruff()
    if not found:
        pytest.skip("ruff yok")
    return found


def test_check_and_format_text(tmp_path, ruff_bin):
    path = tmp_path / "x.py"
    diagnostics = ruff.check_text(ruff_bin, tmp_path, path, "import os\nprint(undefined_name)\n")
    codes = {d.code: d for d in diagnostics}
    assert codes["F401"].severity == "warning" and codes["F821"].severity == "error"
    assert all(d.path == path for d in diagnostics)
    assert ruff.format_text(ruff_bin, tmp_path, path, "x  =  [1,2]\n") == "x = [1, 2]\n"
    with pytest.raises(ruff.FormatError):
        ruff.format_text(ruff_bin, tmp_path, path, "def (:\n")


def test_project_ruff_config_is_respected(tmp_path, ruff_bin):
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nignore = ["F401"]\n', encoding="utf-8")
    (tmp_path / "a.py").write_text("import os\n", encoding="utf-8")
    assert ruff.check_project(ruff_bin, tmp_path) == []


@pytest.mark.parametrize("language", ["tr", "en"])
@pytest.mark.parametrize("template", list(projects.TEMPLATES))
def test_templates_are_ruff_clean(tmp_path, ruff_bin, template, language):
    """Yeni bir proje Sorunlar listesinde uyarıyla açılmamalı ve biçimi düzgün olmalı."""
    project = projects.NewProject(
        name=f"{template}-{language}", parent=tmp_path, template=template,
        python=sys.executable, python_version="3.13.0",
    )
    project.target.mkdir()
    projects.write_template_files(project, language)
    (project.target / "pyproject.toml").write_text(projects.pyproject_text(project), encoding="utf-8")
    diagnostics = ruff.check_project(ruff_bin, project.target)
    assert diagnostics == [], [(d.path.name, d.line, d.code, d.message) for d in diagnostics]
    result = ruff._run(ruff_bin, ["format", "--check", "."], project.target)
    assert result.returncode == 0, result.stdout + result.stderr


# --- dosyalar -----------------------------------------------------------------------------------


def test_language_and_hidden():
    assert files.language_for(Path("a.py")) == "python"
    assert files.language_for(Path("pyproject.toml")) == "ini"
    assert files.language_for(Path("Dockerfile")) == "dockerfile"
    assert files.language_for(Path("x.weird")) == "plaintext"
    assert files.is_hidden(".venv") and files.is_hidden("pkg.egg-info") and not files.is_hidden("src")


def test_read_text_variants(tmp_path):
    crlf = tmp_path / "crlf.txt"
    crlf.write_bytes(b"\xef\xbb\xbfa\r\nb\r\n")
    assert files.read_text(crlf) == ("a\nb\n", "\r\n")
    legacy = tmp_path / "eski.txt"
    legacy.write_bytes("Çalışma".encode("cp1254"))
    assert files.read_text(legacy)[0] == "Çalışma"
    binary = tmp_path / "x.bin"
    binary.write_bytes(b"\x00\x01\x02")
    with pytest.raises(files.NotText) as exc:
        files.read_text(binary)
    assert exc.value.reason == "binary"
    with pytest.raises(files.NotText):
        files.read_text(tmp_path / "missing.txt")


def test_write_text_keeps_line_endings(tmp_path):
    path = tmp_path / "w.txt"
    files.write_text(path, "a\r\nb\n", "\r\n")  # Monaco CRLF verse de çift \r olmaz
    assert path.read_bytes() == b"a\r\nb\r\n"
    files.write_text(path, "ş\n", "\n")
    assert path.read_bytes() == "ş\n".encode()


def test_session_store(tmp_path):
    store = files.SessionStore(tmp_path / "ws.json")
    assert store.load(tmp_path) == files.Session()
    store.save(tmp_path, files.Session(open_files=["a.py"], active="a.py", geometry="AAA="))
    assert store.load(tmp_path).open_files == ["a.py"]
    (tmp_path / "ws.json").write_text("{bozuk", encoding="utf-8")
    assert store.load(tmp_path) == files.Session()


def test_write_text_falls_back_when_replace_is_refused(tmp_path, monkeypatch):
    """Windows'ta dosya başka yerde açıkken os.replace reddedilir; kayıt yine de olmalı."""
    target = tmp_path / "kilitli.py"
    target.write_text("eski\n", encoding="utf-8")
    calls = []

    def refuse(self, other):  # noqa: ANN001, ANN202
        calls.append(other)
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(Path, "replace", refuse)
    monkeypatch.setattr(files.time, "sleep", lambda _s: None)
    files.write_text(target, "yeni\r\n", "\r\n")
    assert target.read_bytes() == b"yeni\r\n"
    assert len(calls) == 10
    assert not (tmp_path / "kilitli.py.pyvot-tmp").exists()
