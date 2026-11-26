from __future__ import annotations

import gzip
import json

import pytest

from pyvot.core import pypi

SAMPLE = {
    "info": {
        "name": "Demo-Pkg",
        "version": "2.0.0",
        "summary": "A demo",
        "license": "",
        "license_expression": None,
        "classifiers": ["License :: OSI Approved :: MIT License"],
        "requires_python": ">=3.9",
        "author": "",
        "author_email": "dev@example.com",
        "home_page": None,
        "project_urls": {"Source": "https://example.com/src", "Empty": None},
        "requires_dist": ["requests>=2", "pytest; extra == 'test'"],
    },
    "releases": {
        "1.0.0": [{"yanked": False}],
        "1.10.0": [{"yanked": False}],
        "2.0.0": [{"yanked": False}],
        "1.5.0": [{"yanked": True}],  # tamamen geri çekilmiş
        "0.1.dev0": [],
        "not-a-version": [{"yanked": False}],
    },
}


def test_parse_info():
    info = pypi.parse_info(SAMPLE)
    assert info.name == "Demo-Pkg"
    assert info.license == "MIT License"
    assert info.author == "dev@example.com"
    assert info.project_urls == {"Source": "https://example.com/src"}
    assert info.releases[:4] == ["2.0.0", "1.10.0", "1.0.0", "0.1.dev0"]
    assert "1.5.0" not in info.releases
    assert info.releases[-1] == "not-a-version"


def test_license_prefers_expression():
    data = json.loads(json.dumps(SAMPLE))
    data["info"]["license_expression"] = "Apache-2.0"
    assert pypi.parse_info(data).license == "Apache-2.0"
    data["info"]["license_expression"] = None
    data["info"]["license"] = "BSD\n\nlong license text..."
    data["info"]["classifiers"] = []
    assert pypi.parse_info(data).license == "BSD"


def test_normalize():
    assert pypi.normalize("Foo_Bar.baz--Qux") == "foo-bar-baz-qux"


def test_search_names_ranking():
    names = ["requests-oauthlib", "Requests", "grequests", "requests_toolbelt", "flask", "requests2"]
    result = pypi.search_names(names, "requests")
    assert result[0] == "Requests"
    assert result[1] == "requests2"  # en kısa ön ek eşleşmesi
    assert set(result[2:4]) == {"requests_toolbelt", "requests-oauthlib"}
    assert result[-1] == "grequests"
    assert "flask" not in result
    assert pypi.search_names(names, "  ") == []
    assert pypi.search_names(names, "requests.toolbelt") == ["requests_toolbelt"]


def test_index_uses_fresh_cache(tmp_path):
    cache = tmp_path / "index.txt.gz"
    cache.write_bytes(gzip.compress("alpha\nbeta\nalpha-tools".encode()))
    index = pypi.PypiIndex(cache)
    assert index.cache_is_fresh()
    index.load()
    assert index.search("alpha") == ["alpha", "alpha-tools"]


def test_parse_simple_index():
    raw = json.dumps({"meta": {}, "projects": [{"name": "a"}, {"name": "B"}, {}]}).encode()
    assert pypi.parse_simple_index(raw) == ["a", "B"]


@pytest.mark.network
def test_fetch_info_live():
    info = pypi.fetch_info("Requests")
    assert info is not None and info.name.lower() == "requests"
    assert pypi.fetch_info("this-package-should-not-exist-pyvot-xyz") is None
