"""Regression tests for the recurring RichBourse transport settings."""

from __future__ import annotations

import ast
from pathlib import Path


SCRAPER = (
    Path(__file__).resolve().parents[3]
    / "functions"
    / "financials"
    / "scrape_financials.py"
)


def test_all_recurring_richbourse_requests_force_http11() -> None:
    tree = ast.parse(SCRAPER.read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "session"
    ]

    assert len(calls) == 3
    for call in calls:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert ast.literal_eval(keywords["http_version"]) == "v1"
        assert ast.literal_eval(keywords["impersonate"]) == "chrome"
        assert "headers" in keywords
        assert "timeout" in keywords
        assert ast.literal_eval(keywords["allow_redirects"]) is True
