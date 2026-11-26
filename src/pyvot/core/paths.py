"""Uygulamanın veri ve önbellek klasörleri."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pyvot import APP_NAME


def _base_data() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def data_dir() -> Path:
    """Ayarların tutulduğu klasör (Windows: %LOCALAPPDATA%\\Pyvot)."""
    override = os.environ.get("PYVOT_HOME")
    d = Path(override) if override else _base_data() / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    """Silinebilir dosyalar (PyPI paket dizini vb.)."""
    override = os.environ.get("PYVOT_HOME")
    if override:
        d = Path(override) / "cache"
    elif sys.platform == "win32":
        d = _base_data() / APP_NAME / "Cache"
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Caches" / APP_NAME
    else:
        d = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / APP_NAME.lower()
    d.mkdir(parents=True, exist_ok=True)
    return d
