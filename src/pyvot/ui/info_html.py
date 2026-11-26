"""PyPI paket bilgisini QTextBrowser için güvenli HTML'e çevirir."""

from __future__ import annotations

from html import escape
from urllib.parse import urlparse

from pyvot.core.pypi import PackageInfo
from pyvot.i18n import tr


def _link(url: str, text: str | None = None) -> str:
    if urlparse(url).scheme not in ("http", "https"):
        return escape(text or url)
    return f'<a href="{escape(url, quote=True)}">{escape(text or url)}</a>'


def render(info: PackageInfo, installed: str | None = None) -> str:
    rows: list[tuple[str, str]] = [(tr("info.latest"), escape(info.version))]
    if installed:
        rows.insert(0, (tr("info.installed"), escape(installed)))
    if info.license:
        rows.append((tr("info.license"), escape(info.license)))
    if info.requires_python:
        rows.append((tr("info.requires_python"), escape(info.requires_python)))
    if info.author:
        rows.append((tr("info.author"), escape(info.author)))

    links = dict(info.project_urls)
    if info.home_page and info.home_page not in links.values():
        links = {"Homepage": info.home_page, **links}
    links.setdefault("PyPI", f"https://pypi.org/project/{info.name}/")

    parts = [f"<h2 style='margin-bottom:2px'>{escape(info.name)}</h2>"]
    if info.summary:
        parts.append(f"<p>{escape(info.summary)}</p>")
    parts.append("<table cellspacing='0' cellpadding='3'>")
    for label, value in rows:
        parts.append(f"<tr><td><b>{escape(label)}</b></td><td>{value}</td></tr>")
    parts.append("</table>")

    parts.append(f"<h4>{escape(tr('info.links'))}</h4><p>")
    parts.append(" · ".join(_link(url, name) for name, url in links.items()))
    parts.append("</p>")

    runtime_deps = [d for d in info.requires_dist if "extra ==" not in d]
    if runtime_deps:
        parts.append(f"<h4>{escape(tr('info.dependencies', count=len(runtime_deps)))}</h4><ul>")
        parts += [f"<li><code>{escape(dep)}</code></li>" for dep in runtime_deps[:40]]
        parts.append("</ul>")

    if info.releases:
        shown = info.releases[:15]
        parts.append(f"<h4>{escape(tr('info.releases', count=len(info.releases)))}</h4><p>")
        parts.append(", ".join(escape(v) for v in shown))
        if len(info.releases) > len(shown):
            parts.append(" …")
        parts.append("</p>")
    return "".join(parts)


def message(text: str) -> str:
    return f"<p style='color:gray'>{escape(text)}</p>"
