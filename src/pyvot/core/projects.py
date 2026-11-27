"""Projeler: şablondan oluşturma, var olan klasörü algılama, proje listesi.

Proje işleri uv ile yapılır: bağımlılıklar ``pyproject.toml``'da, kesin
sürümler ``uv.lock``'ta, sanal ortam ``.venv`` klasöründe durur.
Pyvot proje klasörüne kendine ait bir dosya yazmaz; liste
%LOCALAPPDATA%\\Pyvot\\projects.json dosyasında tutulur.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import tomllib
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pyvot import i18n
from pyvot.core import proc, vscode
from pyvot.core.paths import data_dir

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
IS_WINDOWS = sys.platform == "win32"

Log = Callable[[str], None]


class ProjectError(RuntimeError):
    pass


class Cancelled(ProjectError):
    pass


# --- şablonlar ---------------------------------------------------------------------


@dataclass(frozen=True)
class Template:
    id: str
    group: str = "basic"  # basic | data | web | desktop (sihirbazdaki başlıklar)
    packages: tuple[str, ...] = ()
    dev_packages: tuple[str, ...] = ()
    launch_args: tuple[str, ...] = ()
    run: str = "script"  # F5 nasıl başlatır: script | fastapi | flask
    extensions: tuple[str, ...] = ()
    pytest: bool = False  # tests/ klasörü ve pytest ayarları
    download_mb: int = 0  # paketlerin yaklaşık indirme boyutu

    @property
    def folder(self) -> Path:
        return TEMPLATES_DIR / self.id

    @property
    def title_key(self) -> str:
        return f"template.{self.id}"

    @property
    def description_key(self) -> str:
        return f"template.{self.id}_desc"


TEMPLATE_GROUPS = ("basic", "data", "web", "desktop")

TEMPLATES: dict[str, Template] = {
    t.id: t
    for t in (
        Template("empty"),
        Template("cli", launch_args=("World", "--times", "2")),
        Template(
            "data",
            group="data",
            packages=("pandas", "matplotlib", "ipykernel"),
            extensions=("ms-toolsai.jupyter",),
            download_mb=70,
        ),
        Template(
            "fastapi",
            group="web",
            packages=("fastapi", "uvicorn"),
            dev_packages=("pytest", "httpx2"),
            run="fastapi",
            pytest=True,
            download_mb=15,
        ),
        Template(
            "flask",
            group="web",
            packages=("flask",),
            dev_packages=("pytest",),
            run="flask",
            pytest=True,
            download_mb=5,
        ),
        Template("desktop", group="desktop", packages=("pyside6",), download_mb=200),
        # pygame-ce: pygame'in daha aktif geliştirilen sürümü; kodda yine "import pygame".
        Template("game", group="desktop", packages=("pygame-ce",), download_mb=15),
    )
}

# Şablon dosyalarındaki {{t:anahtar}} yer tutucuları.
TEMPLATE_TEXT: dict[str, dict[str, str]] = {
    "tr": {
        "hello": "Merhaba! {{name}} çalışıyor.",
        "readme_intro": "Bu proje Pyvot ile \"{{template}}\" şablonundan oluşturuldu.",
        "readme_run_title": "Çalıştırma",
        "readme_run_vscode": "VS Code'da projeyi açıp **F5**'e basın.",
        "readme_run_terminal": "Ya da terminalde:",
        "readme_packages_title": "Paket ekleme",
        "readme_packages": "Pyvot'un Paketler sayfasından ya da terminalde:",
        "cli_doc": "komut satırı aracı",
        "cli_desc": "Örnek bir komut satırı aracı.",
        "cli_default_name": "Dünya",
        "cli_name_help": "selamlanacak ad",
        "cli_times_help": "kaç kez yazılsın",
        "cli_upper_help": "büyük harfle yaz",
        "cli_greeting": "Merhaba, {name}!",
        "data_doc": "veri analizi",
        "data_agg_comment": "grafiği pencere açmadan dosyaya kaydet",
        "col_city": "Şehir",
        "col_month": "Ay",
        "col_sales": "Satış",
        "chart_title": "Şehirlere göre toplam satış",
        "chart_saved": "Grafik kaydedildi:",
        "nb_intro": "Örnek veriyi inceleyen bir Jupyter defteri. Hücreleri sırayla çalıştırın (Shift+Enter).",
        "tests_doc": "Örnek testler. VS Code'un Test panelinden ya da terminalde \"uv run pytest\" ile çalıştırın.",
        "api_doc": "yapılacaklar listesi API'si",
        "api_desc": "Görev ekleme, listeleme, tamamlama ve silme örneği.",
        "api_memory_comment": "Örnek olduğu için görevler bellekte tutulur; sunucu yeniden başlayınca silinir.",
        "api_hello": "Merhaba! API çalışıyor. Denemek için /docs sayfasını açın.",
        "api_not_found": "Görev bulunamadı",
        "api_sample_task": "Süt al",
        "web_doc": "basit not defteri sitesi",
        "web_memory_comment": "Örnek olduğu için notlar bellekte tutulur; sunucu yeniden başlayınca silinir.",
        "html_lang": "tr",
        "web_intro": "Bir not yazıp Ekle'ye basın.",
        "web_placeholder": "Notunuz…",
        "web_add": "Ekle",
        "web_empty": "Henüz not yok.",
        "web_sample": "Süt al",
        "desktop_doc": "masaüstü uygulaması",
        "desktop_placeholder": "Bir şey yazın…",
        "desktop_add": "Ekle",
        "desktop_count": "{count} öğe",
        "game_doc": "yıldız toplama oyunu",
        "game_run_doc": "Oyunu çalıştırır ve puanı döndürür. max_frames, testlerde oyunu kısa tutmak içindir.",
        "game_score": "Puan: {score}",
        "game_hint": "Ok tuşları: hareket · Esc: çıkış",
    },
    "en": {
        "hello": "Hello! {{name}} is running.",
        "readme_intro": "This project was created with Pyvot from the \"{{template}}\" template.",
        "readme_run_title": "Running",
        "readme_run_vscode": "Open the project in VS Code and press **F5**.",
        "readme_run_terminal": "Or in a terminal:",
        "readme_packages_title": "Adding packages",
        "readme_packages": "Use Pyvot's Packages page, or in a terminal:",
        "cli_doc": "command-line tool",
        "cli_desc": "An example command-line tool.",
        "cli_default_name": "World",
        "cli_name_help": "name to greet",
        "cli_times_help": "how many times to print",
        "cli_upper_help": "print in upper case",
        "cli_greeting": "Hello, {name}!",
        "data_doc": "data analysis",
        "data_agg_comment": "save the chart to a file without opening a window",
        "col_city": "City",
        "col_month": "Month",
        "col_sales": "Sales",
        "chart_title": "Total sales by city",
        "chart_saved": "Chart saved:",
        "nb_intro": "A Jupyter notebook exploring the sample data. Run the cells in order (Shift+Enter).",
        "tests_doc": "Example tests. Run them from VS Code's Testing panel or with \"uv run pytest\" in a terminal.",
        "api_doc": "to-do list API",
        "api_desc": "An example of adding, listing, completing and deleting tasks.",
        "api_memory_comment": "As an example, tasks are kept in memory and are lost when the server restarts.",
        "api_hello": "Hello! The API is running. Open /docs to try it.",
        "api_not_found": "Task not found",
        "api_sample_task": "Buy milk",
        "web_doc": "simple notebook website",
        "web_memory_comment": "As an example, notes are kept in memory and are lost when the server restarts.",
        "html_lang": "en",
        "web_intro": "Write a note and press Add.",
        "web_placeholder": "Your note…",
        "web_add": "Add",
        "web_empty": "No notes yet.",
        "web_sample": "Buy milk",
        "desktop_doc": "desktop application",
        "desktop_placeholder": "Type something…",
        "desktop_add": "Add",
        "desktop_count": "{count} items",
        "game_doc": "star collecting game",
        "game_run_doc": "Runs the game and returns the score. max_frames keeps the game short in tests.",
        "game_score": "Score: {score}",
        "game_hint": "Arrow keys: move · Esc: quit",
    },
}

_TOKEN = re.compile(r"\{\{\s*(t:)?([a-z_]+)\s*\}\}")


def render(text: str, values: dict[str, str], language: str) -> str:
    strings = TEMPLATE_TEXT.get(language, TEMPLATE_TEXT["en"])

    def replace(match: re.Match[str]) -> str:
        if match.group(1):
            text = strings.get(match.group(2))
            # Metnin içinde {{name}} gibi yer tutucular olabilir; bilinmeyen anahtar olduğu gibi kalır.
            return match.group(0) if text is None else _TOKEN.sub(replace, text)
        return values.get(match.group(2), match.group(0))

    return _TOKEN.sub(replace, text)


# --- adlar ve yollar --------------------------------------------------------------

_INVALID_CHARS = set('<>:"/\\|?*')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
_TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def validate_name(name: str) -> str | None:
    """Klasör adı olarak geçerliyse None, değilse hata anahtarı (i18n) döner."""
    if not name.strip():
        return "project.err_empty"
    if name != name.strip() or name.endswith("."):
        return "project.err_edges"
    if len(name) > 80:
        return "project.err_long"
    if any(ch in _INVALID_CHARS or ord(ch) < 32 for ch in name):
        return "project.err_chars"
    if name.split(".")[0].upper() in _RESERVED:
        return "project.err_reserved"
    return None


def package_name(name: str) -> str:
    """pyproject.toml için geçerli ASCII ad: "Benim Projem" -> "benim-projem"."""
    text = name.translate(_TR_ASCII)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or "project"


def default_projects_root() -> Path:
    if IS_WINDOWS:
        return Path("C:/PyvotProjects")
    return Path.home() / "PyvotProjects"


def fallback_projects_root() -> Path:
    if IS_WINDOWS:
        return Path.home() / "Documents" / "PyvotProjects"
    return Path.home() / "PyvotProjects"


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


# --- var olan klasörü inceleme ----------------------------------------------------------


@dataclass
class ProjectInfo:
    path: Path
    name: str
    venv: Path | None = None  # bulunan ortam klasörü
    venv_state: str = "none"  # none | ok | broken
    python_version: str = ""
    has_pyproject: bool = False
    has_requirements: bool = False
    has_lock: bool = False
    has_git: bool = False
    has_vscode: bool = False
    dependencies: list[str] = field(default_factory=list)

    @property
    def interpreter(self) -> Path | None:
        if self.venv is None:
            return None
        exe = venv_python(self.venv)
        return exe if exe.exists() else None

    @property
    def exists(self) -> bool:
        return self.path.is_dir()


def read_pyvenv_cfg(venv: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = (venv / "pyvenv.cfg").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key.strip().lower()] = value.strip()
    return values


def inspect(path: Path) -> ProjectInfo:
    info = ProjectInfo(path=path, name=path.name)
    pyproject = path / "pyproject.toml"
    if pyproject.is_file():
        info.has_pyproject = True
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            project = data.get("project") or {}
            info.dependencies = [str(d) for d in project.get("dependencies") or []]
        except (OSError, tomllib.TOMLDecodeError, AttributeError):
            pass
    info.has_requirements = (path / "requirements.txt").is_file()
    info.has_lock = (path / "uv.lock").is_file()
    info.has_git = (path / ".git").exists()
    info.has_vscode = (path / ".vscode").is_dir()

    for candidate in (".venv", "venv", "env"):
        venv = path / candidate
        if (venv / "pyvenv.cfg").is_file():
            info.venv = venv
            cfg = read_pyvenv_cfg(venv)
            info.python_version = cfg.get("version_info") or cfg.get("version") or ""
            home = cfg.get("home", "")
            healthy = venv_python(venv).exists() and (not home or Path(home).exists())
            info.venv_state = "ok" if healthy else "broken"
            break
    return info


# --- proje listesi --------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ProjectEntry:
    path: str
    pinned: bool = False
    added: str = field(default_factory=_now)
    last_opened: str = ""

    @property
    def name(self) -> str:
        return Path(self.path).name


class ProjectStore:
    def __init__(self, file: Path | None = None) -> None:
        self.file = file or data_dir() / "projects.json"
        self.entries: list[ProjectEntry] = []
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = []
        entries = []
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                entries.append(
                    ProjectEntry(
                        path=item["path"],
                        pinned=bool(item.get("pinned")),
                        added=str(item.get("added") or _now()),
                        last_opened=str(item.get("last_opened") or ""),
                    )
                )
        self.entries = entries

    def save(self) -> None:
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(e) for e in self.entries], indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.file)

    def find(self, path: str | Path) -> ProjectEntry | None:
        key = _key(path)
        return next((e for e in self.entries if _key(e.path) == key), None)

    def add(self, path: str | Path) -> ProjectEntry:
        entry = self.find(path)
        if entry is None:
            entry = ProjectEntry(path=str(Path(path)))
            self.entries.append(entry)
        entry.last_opened = _now()
        self.save()
        return entry

    def remove(self, path: str | Path) -> bool:
        entry = self.find(path)
        if entry is None:
            return False
        self.entries.remove(entry)
        self.save()
        return True

    def touch(self, path: str | Path) -> None:
        entry = self.find(path)
        if entry is not None:
            entry.last_opened = _now()
            self.save()

    def set_pinned(self, path: str | Path, pinned: bool) -> None:
        entry = self.find(path)
        if entry is not None:
            entry.pinned = pinned
            self.save()

    def sorted(self) -> list[ProjectEntry]:
        """Sabitlenenler önce, sonra en son açılan."""
        by_recent = sorted(self.entries, key=lambda e: e.last_opened or e.added, reverse=True)
        return sorted(by_recent, key=lambda e: not e.pinned)


def _key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


# --- oluşturma -------------------------------------------------------------------------


@dataclass
class NewProject:
    name: str
    parent: Path
    template: str
    python: str  # temel yorumlayıcı
    python_version: str  # "3.13.1"
    create_venv: bool = True
    install_packages: bool = True
    extra_packages: list[str] = field(default_factory=list)
    vscode_files: bool = True
    git: bool = True
    readme: bool = True

    @property
    def target(self) -> Path:
        return self.parent / self.name


def target_problem(target: Path) -> str | None:
    """Hedef klasörde proje oluşturulamıyorsa hata anahtarı döner."""
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        return "project.err_exists"
    return None


def pyproject_text(project: NewProject) -> str:
    major_minor = ".".join(project.python_version.split(".")[:2]) or "3"
    return (
        "[project]\n"
        f'name = "{package_name(project.name)}"\n'
        'version = "0.1.0"\n'
        'description = ""\n'
        + ('readme = "README.md"\n' if project.readme else "")
        + f'requires-python = ">={major_minor}"\n'
        "dependencies = []\n"
        + (
            '\n[tool.pytest.ini_options]\npythonpath = ["."]\ntestpaths = ["tests"]\n'
            if TEMPLATES[project.template].pytest
            else ""
        )
    )


def write_template_files(project: NewProject, language: str) -> list[Path]:
    template = TEMPLATES[project.template]
    values = {
        "name": project.name,
        "package": package_name(project.name),
        "python": project.python_version,
        "template": i18n.TR.get(template.title_key, template.id)
        if language == "tr"
        else i18n.EN.get(template.title_key, template.id),
    }
    target = project.target
    written: list[Path] = []

    def put(relative: Path, text: str) -> None:
        dest = target / relative
        if dest.exists():
            return  # var olan dosyanın üzerine asla yazma
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8", newline="\n")
        written.append(dest)

    for source in sorted(template.folder.rglob("*")):
        if source.is_file() and "__pycache__" not in source.parts:
            put(source.relative_to(template.folder), render(source.read_text(encoding="utf-8"), values, language))
    common = TEMPLATES_DIR / "_common"
    put(Path(".gitignore"), (common / "gitignore.txt").read_text(encoding="utf-8"))
    if project.readme:
        put(Path("README.md"), render((common / "README.md").read_text(encoding="utf-8"), values, language))
    return written


def create(
    project: NewProject,
    uv: str | None,
    log: Log,
    cancel: threading.Event | None = None,
    language: str | None = None,
) -> Path:
    """Projeyi adım adım oluşturur. Hata olursa ProjectError yükseltir."""
    language = language or i18n.current_language()
    t = i18n.tr
    if not uv:
        raise ProjectError(t("project.err_no_uv"))
    problem = validate_name(project.name) or target_problem(project.target)
    if problem:
        raise ProjectError(t(problem))

    target = project.target

    def check_cancel() -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled(t("project.cancelled"))

    def run(cmd: list[str]) -> None:
        check_cancel()
        log("$ " + " ".join(cmd))
        try:
            code = proc.stream(cmd, log, cwd=str(target), cancel=cancel)
        except OSError as exc:
            raise ProjectError(str(exc)) from exc
        check_cancel()
        if code != 0:
            raise ProjectError(t("project.err_step", code=code))

    log(t("project.step_folder", path=str(target)))
    target.mkdir(parents=True, exist_ok=True)
    (target / "pyproject.toml").write_text(pyproject_text(project), encoding="utf-8", newline="\n")
    write_template_files(project, language)
    check_cancel()

    template = TEMPLATES[project.template]
    packages = list(template.packages if project.install_packages else ()) + list(project.extra_packages)
    dev_packages = list(template.dev_packages if project.install_packages else ())
    no_sync = [] if project.create_venv else ["--no-sync"]

    if project.create_venv:
        log(t("project.step_venv", version=project.python_version))
        run([uv, "sync", "--python", project.python])
    if packages:
        key = "project.step_packages" if project.create_venv else "project.step_packages_nosync"
        log(t(key, packages=", ".join(packages)))
        run([uv, "add", *no_sync, "--python", project.python, *packages])
    if dev_packages:
        log(t("project.step_dev_packages", packages=", ".join(dev_packages)))
        run([uv, "add", "--dev", *no_sync, "--python", project.python, *dev_packages])

    if project.vscode_files:
        log(t("project.step_vscode"))
        vscode.write_files(target, template.launch_args, template.extensions, run=template.run, tests=template.pytest)

    if project.git:
        git = shutil.which("git")
        if git:
            log(t("project.step_git"))
            run([git, "init", "--quiet"])
        else:
            log(t("project.git_missing"))

    log(t("project.created"))
    return target


def setup_existing(
    path: Path,
    python: str,
    uv: str | None,
    log: Log,
    *,
    create_venv: bool,
    vscode_files: bool,
    cancel: threading.Event | None = None,
) -> None:
    """Var olan bir projeye eksik olanları ekler (ortam, bağımlılıklar, VS Code)."""
    t = i18n.tr
    info = inspect(path)

    def run(cmd: list[str]) -> None:
        log("$ " + " ".join(cmd))
        try:
            code = proc.stream(cmd, log, cwd=str(path), cancel=cancel)
        except OSError as exc:
            raise ProjectError(str(exc)) from exc
        if cancel is not None and cancel.is_set():
            raise Cancelled(t("project.cancelled"))
        if code != 0:
            raise ProjectError(t("project.err_step", code=code))

    if create_venv:
        if not uv:
            raise ProjectError(t("project.err_no_uv"))
        if info.has_pyproject:
            log(t("project.step_sync"))
            run([uv, "sync", "--python", python])
        else:
            log(t("project.step_venv_plain"))
            run([uv, "venv", "--python", python, str(path / ".venv")])
            if info.has_requirements:
                log(t("project.step_requirements"))
                run([uv, "pip", "install", "--python", str(venv_python(path / ".venv")), "-r", "requirements.txt"])
    if vscode_files:
        log(t("project.step_vscode"))
        written = vscode.write_files(path, (), ())
        if not written:
            log(t("project.vscode_kept"))
    log(t("project.done"))
