from __future__ import annotations

import re
import string
from pathlib import Path

from pyvot import i18n
from pyvot.core.settings import Settings

SRC = Path(__file__).resolve().parent.parent / "src" / "pyvot"


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(language="en", theme="dark", extra_pythons=["C:/py/python.exe"])
    s.save(path)
    loaded = Settings.load(path)
    assert loaded == s


def test_settings_tolerates_bad_files(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert Settings.load(path) == Settings()
    path.write_text('{"theme": "neon", "unknown": 1, "extra_pythons": "x"}', encoding="utf-8")
    loaded = Settings.load(path)
    assert loaded.theme == "system" and loaded.extra_pythons == []


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_languages_have_same_keys_and_placeholders():
    assert set(i18n.TR) == set(i18n.EN)
    for key in i18n.TR:
        assert _placeholders(i18n.TR[key]) == _placeholders(i18n.EN[key]), key


def test_every_used_key_exists():
    pattern = re.compile(r"""\btr\(\s*["']([a-z_]+\.[a-z_.]+)["']""")
    # Sözlük tablolarında geçen anahtarlar (ör. "col.version") da kontrol edilir.
    table = re.compile(r"""["']((?:col|source|nav|settings|kind|flag)\.[a-z_]+)["']""")
    used: set[str] = set()
    for file in SRC.rglob("*.py"):
        if file.name == "i18n.py":
            continue
        text = file.read_text(encoding="utf-8")
        used |= set(pattern.findall(text)) | set(table.findall(text))
    used.discard("settings.json")
    missing = sorted(used - set(i18n.TR))
    assert not missing, missing


def test_tr_formats_and_falls_back():
    i18n.set_language("en")
    try:
        assert i18n.tr("packages.count", count=3) == "3 packages"
        assert i18n.tr("no.such.key") == "no.such.key"
    finally:
        i18n.set_language("tr")
    assert i18n.tr("packages.count", count=3) == "3 paket"
