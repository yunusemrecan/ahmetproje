"""Alt süreç (subprocess) yardımcıları.

Windows'ta konsol penceresi açılmaması için CREATE_NO_WINDOW kullanılır ve
çocuk süreçlere UTF-8 çıktı vermeleri söylenir.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence


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


def stream(
    cmd: Sequence[str],
    log: Callable[[str], None],
    *,
    cwd: str | None = None,
    cancel: threading.Event | None = None,
) -> int:
    """Komutu çalıştırır, çıktısını satır satır ``log``'a iletir; çıkış kodunu döndürür.

    ``cancel`` ayarlanırsa süreç sonlandırılır ve -1 döner.
    Komut bulunamazsa OSError yükseltir.
    """
    process = subprocess.Popen(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=child_env(),
        creationflags=creation_flags(),
    )
    assert process.stdout is not None
    watcher: threading.Thread | None = None
    if cancel is not None:

        def watch() -> None:
            while process.poll() is None:
                if cancel.wait(0.2):
                    process.kill()
                    return

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
    for line in process.stdout:
        log(line.rstrip("\r\n"))
    code = process.wait()
    if cancel is not None and cancel.is_set():
        return -1
    return code
