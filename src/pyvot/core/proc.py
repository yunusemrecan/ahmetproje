"""Alt süreç (subprocess) yardımcıları.

Windows'ta konsol penceresi açılmaması için CREATE_NO_WINDOW kullanılır ve
çocuk süreçlere UTF-8 çıktı vermeleri söylenir.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence


def creation_flags() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return 0


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    # Başka bir Python'un ayarları hedef yorumlayıcıyı bozmasın.
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "VIRTUAL_ENV", "__PYVENV_LAUNCHER__"):
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["NO_COLOR"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    if extra:
        env.update(extra)
    return env


def run(
    cmd: Sequence[str],
    *,
    timeout: float = 60,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Komutu çalıştırır ve çıktısını metin olarak döndürür.

    Çalıştırılamazsa OSError, süre aşılırsa subprocess.TimeoutExpired yükseltir.
    """
    return subprocess.run(
        list(cmd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=cwd,
        env=env if env is not None else child_env(),
        stdin=subprocess.DEVNULL,
        creationflags=creation_flags(),
    )
