"""Behaviour of the shared RichBourse HTTP client."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from functions.financials import richbourse_client as client

URL = "https://www.richbourse.com/page"
HTTP_V11 = object()


class Response:
    def __init__(self, status: int = 200, content: bytes = b"<html>ok</html>", location: str | None = None):
        self.status_code = status
        self.content = content
        self.headers = {"Location": location} if location else {}


class Getter:
    """Scripted stand-in for curl_cffi get; items are responses or exceptions."""

    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, url: str, **kwargs: Any) -> Response:
        self.calls.append((url, kwargs))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch):
    def install(getter: Getter) -> list[float]:
        module = ModuleType("curl_cffi")
        module.CurlHttpVersion = SimpleNamespace(V1_1=HTTP_V11)  # type: ignore[attr-defined]
        module.requests = SimpleNamespace(get=getter)  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "curl_cffi", module)
        sleeps: list[float] = []
        monkeypatch.setattr(client.time, "sleep", sleeps.append)
        return sleeps

    return install


def test_success_uses_chrome_profile_over_http11_without_auto_redirects(transport) -> None:
    getter = Getter(Response())
    transport(getter)
    response = client.fetch(URL, accept="text/html", headers={"Referer": "r"}, params={"page": 2})
    assert response.status_code == 200
    (url, kwargs), = getter.calls
    assert url == URL
    assert kwargs["impersonate"] == "chrome"
    assert kwargs["http_version"] is HTTP_V11
    assert kwargs["allow_redirects"] is False
    assert kwargs["params"] == {"page": 2}
    assert kwargs["headers"]["Accept"] == "text/html"
    assert kwargs["headers"]["Referer"] == "r"
    assert "Accept-Language" in kwargs["headers"]


def test_session_is_used_when_given(transport) -> None:
    transport(Getter())
    session = SimpleNamespace(get=Getter(Response()))
    client.fetch(URL, session=session)
    assert len(session.get.calls) == 1


def test_connection_error_then_success_retries_with_backoff(transport) -> None:
    getter = Getter(ConnectionError("reset"), Response())
    sleeps = transport(getter)
    events: list[tuple[str, int, str | None]] = []
    client.fetch(URL, on_event=lambda *event: events.append(event))
    assert len(getter.calls) == 2
    assert sleeps == [1]
    assert events == [("retry", 1, "ConnectionError"), ("succeeded", 2, None)]


def test_http_403_is_blocked_and_not_retried(transport) -> None:
    getter = Getter(Response(403, b"denied"))
    transport(getter)
    with pytest.raises(client.RichBourseBlocked, match="HTTP 403") as caught:
        client.fetch(URL)
    assert caught.value.status_code == 403
    assert len(getter.calls) == 1


def test_other_status_is_a_typed_http_error(transport) -> None:
    transport(Getter(Response(404, b"gone")))
    with pytest.raises(client.RichBourseHTTPError, match="HTTP 404") as caught:
        client.fetch(URL)
    assert caught.value.status_code == 404


def test_challenge_page_is_blocked_after_bounded_retries(transport) -> None:
    getter = Getter(*[Response(200, b"<title>Just a moment...</title>")] * 3)
    transport(getter)
    with pytest.raises(client.RichBourseBlocked, match="3 attempts"):
        client.fetch(URL)
    assert len(getter.calls) == 3


@pytest.mark.parametrize("response", [Response(200, b""), Response(503, b"busy"), ConnectionError("x")])
def test_unavailable_after_bounded_retries(transport, response: Any) -> None:
    getter = Getter(*[response] * 3)
    transport(getter)
    with pytest.raises(client.RichBourseUnavailable, match="3 attempts"):
        client.fetch(URL)
    assert len(getter.calls) == 3


def test_pdf_bytes_are_never_treated_as_a_challenge(transport) -> None:
    pdf = b"%PDF-1.7 access denied inside the document"
    transport(Getter(Response(200, pdf)))
    assert client.fetch(URL, accept="application/pdf").content == pdf


def test_redirect_is_followed_within_origin_without_repeating_params(transport) -> None:
    getter = Getter(Response(302, b"", "/final?x=1"), Response())
    transport(getter)
    client.fetch(URL, params={"page": 1})
    assert getter.calls[1][0] == "https://www.richbourse.com/final?x=1"
    assert "params" not in getter.calls[1][1]


def test_off_origin_redirect_is_rejected_before_following(transport) -> None:
    getter = Getter(Response(302, b"", "https://files.invalid/report.pdf"))
    transport(getter)
    with pytest.raises(client.RichBourseOriginError, match="outside the approved origin"):
        client.fetch(URL)
    assert len(getter.calls) == 1


def test_off_origin_start_url_is_rejected_without_a_request(transport) -> None:
    getter = Getter()
    transport(getter)
    with pytest.raises(client.RichBourseOriginError):
        client.fetch("https://evil.invalid/page")
    assert getter.calls == []


def test_redirect_loop_hits_the_limit(transport) -> None:
    getter = Getter(*[Response(302, b"", "/again")] * (client.MAX_REDIRECTS + 1))
    transport(getter)
    with pytest.raises(client.RichBourseRedirectError):
        client.fetch(URL)


def test_total_deadline_stops_retries(transport) -> None:
    getter = Getter(ConnectionError("x"), ConnectionError("x"), ConnectionError("x"))
    transport(getter)
    clock = iter([0.0, 0.0, 5.0, 5.0])
    with pytest.raises(TimeoutError):
        client.fetch(URL, timeout=1, monotonic=lambda: next(clock))
    assert len(getter.calls) == 1


@pytest.mark.parametrize(
    "url, expected",
    [
        (URL, True),
        ("http://www.richbourse.com/x", False),
        ("https://www.richbourse.com:8443/x", False),
        ("https://user@www.richbourse.com/x", False),
        ("https://richbourse.com.evil.invalid/x", False),
    ],
)
def test_approved_url(url: str, expected: bool) -> None:
    assert client.is_approved_url(url) is expected
