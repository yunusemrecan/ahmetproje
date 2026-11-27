from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

from pyvot import i18n
from pyvot.core import deps, projects
from pyvot.core.deps import DEV, MAIN, Dependency

PY_VERSION = ".".join(map(str, sys.version_info[:3]))


def _quiet(_line: str) -> None:
    pass


@pytest.fixture
def project(tmp_path, uv_bin) -> Path:
    """.venv'i kurulu, bağımlılıksız bir proje (internet gerekmez)."""
    i18n.set_language("tr")
    new = projects.NewProject(
        name="dep-test", parent=tmp_path, template="empty", python=sys.executable, python_version=PY_VERSION, git=False
    )
    return projects.create(new, uv_bin, _quiet, language="tr")


def _pyproject(path: Path) -> dict:
    return tomllib.loads((path / "pyproject.toml").read_text(encoding="utf-8"))


# --- okuma ve yardımcılar ----------------------------------------------------------------


def test_read_dependencies_all_groups(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\ndependencies=["requests>=2.31", "pandas[excel]>=2; python_version>\'3.9\'"]\n'
        '[dependency-groups]\ndev=["pytest>=8"]\n'
        '[tool.uv]\ndev-dependencies=["ruff"]\n',
        encoding="utf-8",
    )
    found = deps.read_dependencies(tmp_path)
    assert [(d.name, d.group) for d in found] == [
        ("requests", MAIN),
        ("pandas", MAIN),
        ("pytest", DEV),
        ("ruff", DEV),
    ]
    assert found[0].constraint == ">=2.31"
    assert found[1].constraint == "[excel] >=2"
    assert found[3].constraint == ""


def test_read_dependencies_without_pyproject(tmp_path):
    assert deps.read_dependencies(tmp_path) == []


def test_latest_allowed_and_outdated():
    dep = Dependency("idna", "idna<3.5", MAIN, installed="3.4", latest="3.20")
    assert dep.outdated and dep.latest_allowed() is False
    dep = Dependency("six", "six>=1.10", MAIN, installed="1.15.0", latest="1.17.0")
    assert dep.latest_allowed() is True
    assert Dependency("x", "x", MAIN).latest_allowed() is None
    assert not Dependency("x", "x", MAIN, installed="1", latest="1").outdated


def test_python_satisfies():
    assert deps.python_satisfies("3.13.1", ">=3.12")
    assert not deps.python_satisfies("3.11.9", ">=3.12")
    assert deps.python_satisfies("3.11.9", "")
    assert deps.python_satisfies("3.11.9", "not a specifier")


def test_set_requires_python(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "x"\nrequires-python = ">=3.13"\ndependencies = []\n', encoding="utf-8")
    deps.set_requires_python(tmp_path, "3.11.4")
    assert deps.requires_python(tmp_path) == ">=3.11"
    path.write_text('[project]\nname = "x"\ndependencies = []\n', encoding="utf-8")
    deps.set_requires_python(tmp_path, "3.12.0")
    assert _pyproject(tmp_path)["project"]["requires-python"] == ">=3.12"


# --- uv ile (internet gerekmez) --------------------------------------------------------------


def test_sync_state_detects_unsynced_and_sync_fixes_it(project, uv_bin):
    assert deps.sync_state(project, uv_bin) == "ok"
    # requires-python uv.lock'a yazılır; değişince kilit dosyası eskir (internet gerekmez).
    deps.set_requires_python(project, "3.8")
    assert deps.sync_state(project, uv_bin) == "unsynced"
    deps.sync(project, uv_bin, log=_quiet)
    assert deps.sync_state(project, uv_bin) == "ok"


def test_sync_state_unknown_without_pyproject(tmp_path, uv_bin):
    assert deps.sync_state(tmp_path, uv_bin) == "unknown"
    assert deps.sync_state(tmp_path, None) == "unknown"


def test_rebuild_env_recreates_venv(project, uv_bin):
    marker = project / ".venv" / "pyvot-marker"
    marker.write_text("x", encoding="utf-8")
    deps.rebuild_env(project, sys.executable, uv_bin, log=_quiet)
    info = projects.inspect(project)
    assert info.venv_state == "ok" and not marker.exists()


def test_rebuild_env_refuses_incompatible_python_and_keeps_venv(project, uv_bin):
    deps.set_requires_python(project, "99.0")
    marker = project / ".venv" / "pyvot-marker"
    marker.write_text("x", encoding="utf-8")
    with pytest.raises(projects.ProjectError):
        deps.rebuild_env(project, sys.executable, uv_bin, log=_quiet)
    assert marker.exists()  # eski ortam silinmedi


def test_rebuild_env_repairs_broken_venv(project, uv_bin):
    cfg = project / ".venv" / "pyvenv.cfg"
    cfg.write_text("home = /bu/yol/yok\nversion_info = 3.0.0\n", encoding="utf-8")
    assert projects.inspect(project).venv_state == "broken"
    deps.rebuild_env(project, sys.executable, uv_bin, log=_quiet)
    assert projects.inspect(project).venv_state == "ok"


def test_rebuild_env_for_plain_folder(tmp_path, uv_bin):
    deps.rebuild_env(tmp_path, sys.executable, uv_bin, log=_quiet)
    assert projects.inspect(tmp_path).venv_state == "ok"


def test_export_requirements_without_deps(project, uv_bin):
    out = deps.export_requirements(project, uv_bin, log=_quiet)
    assert out.exists()


def test_operations_need_uv(project):
    with pytest.raises(projects.ProjectError):
        deps.sync(project, None, log=_quiet)


# --- PyPI gerektirenler --------------------------------------------------------------------


@pytest.mark.network
def test_add_upgrade_major_remove(project, uv_bin):
    deps.add(project, ["six==1.15.0", "idna<3.5"], False, uv_bin, log=_quiet)
    deps.add(project, ["iniconfig"], True, uv_bin, log=_quiet)
    data = _pyproject(project)
    assert sorted(data["project"]["dependencies"]) == ["idna<3.5", "six==1.15.0"]
    assert data["dependency-groups"]["dev"][0].startswith("iniconfig")

    found = deps.with_latest(project, deps.with_versions(project, deps.read_dependencies(project), uv_bin), uv_bin)
    by_name = {d.name: d for d in found}
    assert by_name["six"].installed == "1.15.0" and by_name["six"].latest_allowed() is False
    assert by_name["iniconfig"].group == DEV and by_name["iniconfig"].installed

    # Aralık içinde güncelleme sınırı aşmaz.
    deps.upgrade(project, ["idna"], uv_bin, log=_quiet)
    idna = next(d for d in deps.with_versions(project, deps.read_dependencies(project), uv_bin) if d.name == "idna")
    assert idna.installed and idna.installed.startswith("3.") and int(idna.installed.split(".")[1]) < 5

    # Büyük sürüme yükseltme aralığı değiştirir.
    deps.upgrade_major(project, by_name["six"], uv_bin, log=_quiet)
    six = next(d for d in deps.read_dependencies(project) if d.name == "six")
    assert six.spec == f"six>={by_name['six'].latest}"

    deps.remove(project, ["iniconfig"], True, uv_bin, log=_quiet)
    assert [d.name for d in deps.read_dependencies(project)] == ["idna", "six"]

    text = deps.export_requirements(project, uv_bin, log=_quiet).read_text(encoding="utf-8")
    assert "six==" in text and "iniconfig" not in text


@pytest.mark.network
def test_convert_requirements(tmp_path, uv_bin):
    (tmp_path / "requirements.txt").write_text("six==1.16.0\n", encoding="utf-8")
    deps.convert_requirements(tmp_path, sys.executable, uv_bin, log=_quiet)
    assert [d.spec for d in deps.read_dependencies(tmp_path)] == ["six==1.16.0"]
    assert (tmp_path / "requirements.txt").exists()
    assert projects.inspect(tmp_path).venv_state == "ok"
