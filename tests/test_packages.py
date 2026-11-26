from __future__ import annotations

import pytest

from pyvot.core import proc
from pyvot.core.packages import PackageError, PackageManager, parse_list_json, validate_specs


def test_parse_list_json_pip_outdated_format():
    text = '[{"name": "Six", "version": "1.15.0", "latest_version": "1.17.0", "latest_filetype": "wheel"}]'
    [pkg] = parse_list_json(text)
    assert (pkg.name, pkg.version, pkg.latest, pkg.outdated) == ("Six", "1.15.0", "1.17.0", True)


def test_parse_list_json_sorts_and_handles_noise():
    text = 'warning: something\n[{"name": "b", "version": "1"}, {"name": "A", "version": "2", "editable_project_location": "/src"}]'
    packages = parse_list_json(text)
    assert [p.name for p in packages] == ["A", "b"]
    assert packages[0].editable_location == "/src"
    assert parse_list_json("") == []
    with pytest.raises(PackageError):
        parse_list_json("no json here")


def test_validate_specs():
    assert validate_specs("requests  numpy>=2 pandas[excel]==2.2") == ["requests", "numpy>=2", "pandas[excel]==2.2"]
    for bad in ("--index-url=http://evil", "foo===", "-r req.txt"):
        with pytest.raises(ValueError):
            validate_specs(bad)


def test_manager_backend_choice():
    assert PackageManager.create("py", "uv").backend == "uv"
    assert PackageManager.create("py", None).backend == "pip"
    assert PackageManager.create("py", "uv", "pip").backend == "pip"
    assert PackageManager.create("py", None, "uv").backend == "pip"  # uv yoksa pip'e düşer


def test_uv_commands():
    m = PackageManager("C:/env/python.exe", "uv", "uv.exe")
    assert m.list_cmd() == ["uv.exe", "pip", "list", "--python", "C:/env/python.exe", "--format", "json"]
    assert m.list_cmd(outdated=True)[-1] == "--outdated"
    assert m.install_cmd(["a", "b"], upgrade=True) == [
        "uv.exe", "pip", "install", "--python", "C:/env/python.exe", "--upgrade", "a", "b"
    ]
    assert m.uninstall_cmd(["a"]) == ["uv.exe", "pip", "uninstall", "--python", "C:/env/python.exe", "a"]


def test_pip_commands():
    m = PackageManager("python", "pip")
    assert m.list_cmd()[:4] == ["python", "-m", "pip", "list"]
    assert m.install_cmd(["a"])[-1] == "a"
    assert m.uninstall_cmd(["a", "b"]) == ["python", "-m", "pip", "uninstall", "-y", "--disable-pip-version-check", "a", "b"]


def test_list_empty_venv_with_uv(venv_python, uv_bin):
    manager = PackageManager.create(venv_python, uv_bin)
    assert manager.list_packages() == []


def test_pip_backend_reports_missing_pip(venv_python, uv_bin):
    # uv ile açılan ortamlarda pip yoktur.
    with pytest.raises(PackageError, match="no-pip"):
        PackageManager.create(venv_python, uv_bin, "pip").list_packages()


@pytest.mark.network
def test_install_outdated_uninstall_roundtrip(venv_python, uv_bin):
    manager = PackageManager.create(venv_python, uv_bin)
    result = proc.run(manager.install_cmd(["six==1.15.0"]), timeout=300)
    assert result.returncode == 0, result.stderr
    assert [(p.name, p.version) for p in manager.list_packages()] == [("six", "1.15.0")]
    assert "six" in manager.outdated()
    result = proc.run(manager.uninstall_cmd(["six"]), timeout=120)
    assert result.returncode == 0, result.stderr
    assert manager.list_packages() == []
