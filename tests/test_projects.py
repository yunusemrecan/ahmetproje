from __future__ import annotations

import json
import subprocess
import sys
import threading
import tomllib
from pathlib import Path

import pytest

from pyvot import i18n
from pyvot.core import projects, terminal, vscode
from pyvot.core.projects import NewProject, ProjectStore


@pytest.fixture(autouse=True)
def _turkish():
    i18n.set_language("tr")
    yield
    i18n.set_language("tr")


def _new(tmp_path: Path, template: str = "empty", **kw) -> NewProject:
    defaults = dict(
        name="Benim Projem",
        parent=tmp_path,
        template=template,
        python=sys.executable,
        python_version=".".join(map(str, sys.version_info[:3])),
        create_venv=False,
        git=False,
    )
    defaults.update(kw)
    return NewProject(**defaults)


# --- adlar --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("hesap-makinesi", None),
        ("Benim Projem", None),
        ("Şeker Çay", None),
        ("", "project.err_empty"),
        ("   ", "project.err_empty"),
        (" a", "project.err_edges"),
        ("proje.", "project.err_edges"),
        ("a" * 81, "project.err_long"),
        ("a/b", "project.err_chars"),
        ('a"b', "project.err_chars"),
        ("soru?", "project.err_chars"),
        ("con", "project.err_reserved"),
        ("COM1.txt", "project.err_reserved"),
    ],
)
def test_validate_name(name, error):
    assert projects.validate_name(name) == error


def test_package_name():
    assert projects.package_name("Benim Projem") == "benim-projem"
    assert projects.package_name("Şeker Çay İçelim") == "seker-cay-icelim"
    assert projects.package_name("!!!") == "project"
    assert projects.package_name("café_2") == "cafe-2"


def test_render_nested_and_unknown_tokens():
    values = {"name": "X"}
    assert projects.render("{{t:hello}}", values, "tr") == "Merhaba! X çalışıyor."
    assert projects.render("{{t:hello}}", values, "en") == "Hello! X is running."
    assert projects.render("{{other}} {{t:missing}}", values, "tr") == "{{other}} {{t:missing}}"


def test_every_template_token_has_text_in_both_languages():
    import re

    used = set()
    for file in projects.TEMPLATES_DIR.rglob("*"):
        if file.is_file():
            used |= set(re.findall(r"\{\{t:([a-z_]+)\}\}", file.read_text(encoding="utf-8")))
    for text in projects.TEMPLATE_TEXT["tr"].values():
        used |= set(re.findall(r"\{\{t:([a-z_]+)\}\}", text))
    for language in ("tr", "en"):
        assert used <= set(projects.TEMPLATE_TEXT[language]), language
    assert set(projects.TEMPLATE_TEXT["tr"]) == set(projects.TEMPLATE_TEXT["en"])
    for template in projects.TEMPLATES.values():
        assert template.title_key in i18n.TR and template.description_key in i18n.EN


# --- dosyalar -------------------------------------------------------------------------


def test_pyproject_text_is_valid_toml(tmp_path):
    data = tomllib.loads(projects.pyproject_text(_new(tmp_path, python_version="3.12.4")))
    assert data["project"]["name"] == "benim-projem"
    assert data["project"]["requires-python"] == ">=3.12"
    assert data["project"]["dependencies"] == []


@pytest.mark.parametrize("language", ["tr", "en"])
@pytest.mark.parametrize("template", list(projects.TEMPLATES))
def test_template_files_render(tmp_path, template, language):
    project = _new(tmp_path, template)
    project.target.mkdir()
    written = projects.write_template_files(project, language)
    names = {p.relative_to(project.target).as_posix() for p in written}
    assert {"main.py", ".gitignore", "README.md"} <= names
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert "{{" not in text, path
        if path.suffix == ".py":
            compile(text, str(path), "exec")
        if path.suffix == ".ipynb":
            json.loads(text)


def test_template_files_never_overwrite(tmp_path):
    project = _new(tmp_path)
    project.target.mkdir()
    (project.target / "main.py").write_text("benim kodum", encoding="utf-8")
    projects.write_template_files(project, "tr")
    assert (project.target / "main.py").read_text(encoding="utf-8") == "benim kodum"


def test_vscode_files(tmp_path):
    written = vscode.write_files(tmp_path, ("a", "b"), ("ms-toolsai.jupyter",))
    assert {p.name for p in written} == {"settings.json", "launch.json", "tasks.json", "extensions.json"}
    launch = json.loads((tmp_path / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    assert launch["configurations"][0]["args"] == ["a", "b"]
    assert launch["configurations"][0]["type"] == "debugpy"
    ext = json.loads((tmp_path / ".vscode" / "extensions.json").read_text(encoding="utf-8"))
    assert ext["recommendations"][0] == "ms-python.python" and "ms-toolsai.jupyter" in ext["recommendations"]
    # İkinci kez: hiçbir şeyin üzerine yazılmaz.
    (tmp_path / ".vscode" / "settings.json").write_text("{}", encoding="utf-8")
    assert vscode.write_files(tmp_path) == []
    assert (tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8") == "{}"


def test_vscode_interpreter_setting():
    assert vscode.interpreter_setting(windows=True) == "${workspaceFolder}/.venv/Scripts/python.exe"
    assert vscode.interpreter_setting(windows=False) == "${workspaceFolder}/.venv/bin/python"


# --- terminal ---------------------------------------------------------------------------


def test_terminal_command_with_and_without_windows_terminal(tmp_path):
    venv = tmp_path / ".venv"
    tools = {"wt": "C:/wt.exe", "pwsh": None, "powershell": "C:/ps.exe"}
    cmd = terminal.windows_command(tmp_path, venv, which=tools.get)
    assert cmd[:5] == ["C:/wt.exe", "-w", "new", "-d", str(tmp_path)]
    assert cmd[5:8] == ["C:/ps.exe", "-NoLogo", "-NoExit"]
    assert cmd[8] == "-EncodedCommand"
    script = __import__("base64").b64decode(cmd[9]).decode("utf-16-le")
    assert "$env:VIRTUAL_ENV" in script and "Scripts" in script

    tools["wt"] = None
    cmd = terminal.windows_command(tmp_path, None, which=tools.get)
    assert cmd == ["C:/ps.exe", "-NoLogo", "-NoExit"]


def test_activation_script_quotes_apostrophes():
    script = terminal.activation_script(Path("C:/Users/O'Neil/p/.venv"), windows=True)
    assert "O''Neil" in script


# --- inceleme ve liste ---------------------------------------------------------------------


def test_inspect_detects_files_and_broken_venv(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\ndependencies=["requests>=2"]\n', encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = /nowhere/at/all\nversion_info = 3.12.1\n", encoding="utf-8")
    info = projects.inspect(tmp_path)
    assert info.has_pyproject and info.has_requirements and info.has_git and not info.has_vscode
    assert info.dependencies == ["requests>=2"]
    assert info.venv == venv and info.venv_state == "broken" and info.python_version == "3.12.1"
    assert info.interpreter is None


def test_inspect_empty_folder(tmp_path):
    info = projects.inspect(tmp_path)
    assert info.venv is None and info.venv_state == "none" and not info.has_pyproject


def test_project_store(tmp_path):
    file = tmp_path / "projects.json"
    store = ProjectStore(file)
    a, b, c = (str(tmp_path / n) for n in ("a", "b", "c"))
    store.add(a)
    store.add(b)
    store.add(c)
    store.add(a)  # tekrar eklemek çoğaltmaz, son açılmayı günceller
    assert len(store.entries) == 3
    store.entries[0].last_opened = "2026-01-03T00:00:00+00:00"  # a
    store.entries[1].last_opened = "2026-01-01T00:00:00+00:00"  # b
    store.entries[2].last_opened = "2026-01-02T00:00:00+00:00"  # c
    store.set_pinned(b, True)
    assert [Path(e.path).name for e in store.sorted()] == ["b", "a", "c"]
    assert store.remove(c) and not store.remove(c)
    reloaded = ProjectStore(file)
    assert [Path(e.path).name for e in reloaded.entries] == ["a", "b"]
    assert reloaded.find(b).pinned


def test_project_store_tolerates_bad_file(tmp_path):
    file = tmp_path / "projects.json"
    file.write_text("{oops", encoding="utf-8")
    assert ProjectStore(file).entries == []
    file.write_text('[{"path": 5}, {"path": "/x", "pinned": 1}]', encoding="utf-8")
    assert [e.path for e in ProjectStore(file).entries] == ["/x"]


# --- oluşturma ------------------------------------------------------------------------------


def test_create_without_venv_needs_no_network(tmp_path, uv_bin):
    lines: list[str] = []
    target = projects.create(_new(tmp_path), uv_bin, lines.append, language="tr")
    assert (target / "main.py").is_file() and (target / ".vscode" / "launch.json").is_file()
    assert not (target / ".venv").exists()
    assert lines[-1] == i18n.tr("project.created")


def test_create_refuses_non_empty_folder(tmp_path, uv_bin):
    project = _new(tmp_path)
    project.target.mkdir()
    (project.target / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(projects.ProjectError):
        projects.create(project, uv_bin, lambda _l: None)
    assert (project.target / "x.txt").read_text(encoding="utf-8") == "x"


def test_create_requires_uv(tmp_path):
    with pytest.raises(projects.ProjectError):
        projects.create(_new(tmp_path), None, lambda _l: None)


def test_create_can_be_cancelled(tmp_path, uv_bin):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(projects.Cancelled):
        projects.create(_new(tmp_path, create_venv=True), uv_bin, lambda _l: None, cancel=cancel)


@pytest.mark.parametrize(("template", "args", "expected"), [("empty", [], "çalışıyor"), ("cli", ["Ayşe", "-n", "2"], "Merhaba, Ayşe!")])
def test_create_with_venv_and_run(tmp_path, uv_bin, template, args, expected):
    target = projects.create(_new(tmp_path, template, create_venv=True, git=True), uv_bin, lambda _l: None, language="tr")
    info = projects.inspect(target)
    assert info.venv_state == "ok" and info.has_lock and info.interpreter is not None
    result = subprocess.run([str(info.interpreter), "main.py", *args], cwd=target, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout
    if template == "cli":
        assert result.stdout.count(expected) == 2


@pytest.mark.network
def test_create_data_project_installs_and_runs(tmp_path, uv_bin):
    target = projects.create(_new(tmp_path, "data", create_venv=True), uv_bin, lambda _l: None, language="en")
    info = projects.inspect(target)
    assert {d.split(">=")[0] for d in info.dependencies} == {"pandas", "matplotlib", "ipykernel"}
    result = subprocess.run([str(info.interpreter), "main.py"], cwd=target, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert (target / "chart.png").stat().st_size > 1000


def test_setup_existing_pyproject_project(tmp_path, uv_bin):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "eski"\nversion = "0.1.0"\ndependencies = []\n', encoding="utf-8"
    )
    lines: list[str] = []
    projects.setup_existing(tmp_path, sys.executable, uv_bin, lines.append, create_venv=True, vscode_files=True)
    info = projects.inspect(tmp_path)
    assert info.venv_state == "ok" and info.has_vscode


def test_setup_existing_plain_folder(tmp_path, uv_bin):
    projects.setup_existing(tmp_path, sys.executable, uv_bin, lambda _l: None, create_venv=True, vscode_files=False)
    info = projects.inspect(tmp_path)
    assert info.venv_state == "ok" and not info.has_vscode
