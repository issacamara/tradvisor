"""Regression tests for the recurring RichBourse transport settings."""

from __future__ import annotations

import ast
import importlib.util
import sys
from types import ModuleType, SimpleNamespace
from pathlib import Path

import pytest


SCRAPER = (
    Path(__file__).resolve().parents[3]
    / "functions"
    / "financials"
    / "scrape_financials.py"
)


def test_all_recurring_richbourse_requests_force_http11() -> None:
    tree = ast.parse(SCRAPER.read_text())
    constants = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "HTTP_VERSION_1_1"
    }
    http_version = constants["HTTP_VERSION_1_1"]
    assert isinstance(http_version, ast.Attribute)
    assert http_version.attr == "V1_1"
    assert "User-Agent" not in SCRAPER.read_text()

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "session"
    ]

    assert len(calls) == 1
    helper = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_richbourse_get"
    )
    helper_call = next(
        node
        for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
    )
    keywords = {keyword.arg: keyword.value for keyword in helper_call.keywords}
    assert isinstance(keywords["http_version"], ast.Name)
    assert keywords["http_version"].id == "HTTP_VERSION_1_1"
    assert ast.literal_eval(keywords["impersonate"]) == "chrome"
    assert "headers" in keywords
    assert "timeout" in keywords
    assert ast.literal_eval(keywords["allow_redirects"]) is True

    richbourse_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_richbourse_get"
    ]
    assert len(richbourse_calls) == 3


def _load_scraper(monkeypatch: pytest.MonkeyPatch):
    functions_framework = ModuleType("functions_framework")
    functions_framework.http = lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "functions_framework", functions_framework)
    observability = ModuleType("ingestion_observability")
    observability.emit_event = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    observability.managed_import_completion = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    observability.observed_entrypoint = lambda *args, **kwargs: (lambda function: function)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ingestion_observability", observability)
    helper = ModuleType("helper")
    for name in ("save_dataframe_as_csv", "table_exists", "upsert_financial_report_current_and_revision"):
        setattr(helper, name, lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, "helper", helper)
    google = ModuleType("google")
    google_auth = ModuleType("google.auth")
    google_auth.default = lambda: (None, "fixture-project")  # type: ignore[attr-defined]
    google.auth = google_auth  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.auth", google_auth)
    curl = ModuleType("curl_cffi")
    curl.CurlHttpVersion = SimpleNamespace(V1_1=object())  # type: ignore[attr-defined]
    curl.requests = SimpleNamespace()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "curl_cffi", curl)
    spec = importlib.util.spec_from_file_location("financials_transport_fixture", SCRAPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transport_retries_connection_then_returns_success(monkeypatch: pytest.MonkeyPatch) -> None:
    scraper = _load_scraper(monkeypatch)
    calls: list[dict[str, object]] = []

    class Response:
        status_code = 200
        content = b"<html>listing</html>"

    class Session:
        def get(self, url, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise ConnectionError("empty reply")
            return Response()

    sleeps: list[int] = []
    monkeypatch.setattr(scraper.time, "sleep", sleeps.append)
    response = scraper._richbourse_get(Session(), "https://fixture.invalid", {}, timeout=3)
    assert response.status_code == 200
    assert len(calls) == 2
    assert sleeps == [1]
    assert calls[0]["http_version"] is scraper.HTTP_VERSION_1_1
    assert calls[0]["impersonate"] == "chrome"


@pytest.mark.parametrize("content", [b"", b"Just a moment..."])
def test_transport_rejects_unusable_content_after_bounded_retries(
    monkeypatch: pytest.MonkeyPatch, content: bytes
) -> None:
    scraper = _load_scraper(monkeypatch)

    class Response:
        status_code = 200

        def __init__(self):
            self.content = content

    class Session:
        def get(self, url, **kwargs):
            return Response()

    monkeypatch.setattr(scraper.time, "sleep", lambda seconds: None)
    with pytest.raises(scraper.RichBourseTransportError, match="3 attempts"):
        scraper._richbourse_get(Session(), "https://fixture.invalid", {}, timeout=3)
