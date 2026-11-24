"""Single RichBourse HTTP client for the financial ingestion jobs.

One place owns the transport settings that RichBourse needs (browser
impersonation over HTTP/1.1), the retry policy, redirect handling, the
approved-origin check and the classification of failures, so a fix reaches
every caller.

Failures are typed so callers and logs can tell a blocked request from an
outage:

- ``RichBourseBlocked``: HTTP 403 or a bot-challenge page. Retrying the same
  request does not help; the transport profile or headers must change.
- ``RichBourseUnavailable``: retryable statuses, empty bodies or connection
  errors that persisted for every attempt.
- ``RichBourseHTTPError``: any other non-200 status.
- ``RichBourseRedirectError``: redirect limit exceeded.
- ``RichBourseOriginError``: a URL or redirect outside the approved origin.

Messages carry the status and attempt count only, never URLs or headers.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlparse

APPROVED_HOST = "www.richbourse.com"
MAX_ATTEMPTS = 3
RETRY_DELAYS = (1, 2)
RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
MAX_REDIRECTS = 5
DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
DEFAULT_ACCEPT_LANGUAGE = "fr-FR,fr;q=0.9,en;q=0.8"
# Challenge pages put their markers near the top; scan a bounded prefix.
CHALLENGE_SCAN_BYTES = 16_384
CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "cf-chl-",
    "enable javascript and cookies",
    "access denied",
)

Sleep = Callable[[float], None]
Monotonic = Callable[[], float]
EventHook = Callable[[str, int, "str | None"], None]


class RichBourseError(RuntimeError):
    """Base class for RichBourse transport failures."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RichBourseBlocked(RichBourseError):
    """RichBourse refused the request (HTTP 403 or a challenge page)."""


class RichBourseUnavailable(RichBourseError):
    """RichBourse stayed unavailable for every attempt."""


class RichBourseHTTPError(RichBourseError):
    """RichBourse answered with a non-retryable, non-200 status."""


class RichBourseRedirectError(RichBourseError):
    """The redirect limit was exceeded."""


class RichBourseOriginError(ValueError):
    """A URL or redirect target is outside the approved origin."""


def is_approved_url(url: str) -> bool:
    """Return True only for https URLs on the approved host, without userinfo or port."""
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme.casefold() == "https"
            and parsed.hostname is not None
            and parsed.hostname.casefold() == APPROVED_HOST
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def is_challenge_page(content: bytes) -> bool:
    """Detect a bot-challenge or interstitial page; PDFs are never challenges."""
    if content.startswith(b"%PDF-"):
        return False
    text = content[:CHALLENGE_SCAN_BYTES].decode("utf-8", errors="ignore").lower()
    return any(marker in text for marker in CHALLENGE_MARKERS)


def _retry_reason(response: Any) -> str | None:
    """Return why a response must be retried, or None when it needs no retry."""
    status = response.status_code
    if status in RETRYABLE_STATUSES:
        return f"HTTP {status}"
    if status == 200:
        content = response.content or b""
        if not content:
            return "empty body"
        if is_challenge_page(content):
            return "challenge page"
    return None


def fetch(
    url: str,
    *,
    accept: str = DEFAULT_ACCEPT,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    timeout: float = 30.0,
    session: Any | None = None,
    on_event: EventHook | None = None,
    sleep: Sleep | None = None,
    monotonic: Monotonic | None = None,
) -> Any:
    """GET one RichBourse resource and return a usable 200 response.

    Redirects are followed by hand so every hop is checked against the approved
    origin. ``timeout`` is a total budget across attempts and redirects.
    ``session`` is an optional curl-cffi session whose cookies are reused.
    ``on_event(status, attempt, error_class)`` reports "retry" and "succeeded".
    """
    from curl_cffi import CurlHttpVersion, requests

    sleep = sleep or time.sleep
    monotonic = monotonic or time.monotonic
    getter = session.get if session is not None else requests.get
    request_headers = {"Accept": accept, "Accept-Language": DEFAULT_ACCEPT_LANGUAGE}
    request_headers.update(headers or {})
    deadline = monotonic() + timeout
    current_url = url
    pending_params = dict(params) if params else None

    for redirect_count in range(MAX_REDIRECTS + 1):
        if not is_approved_url(current_url):
            raise RichBourseOriginError("RichBourse URL is outside the approved origin")
        response = _get_with_retries(
            getter,
            current_url,
            headers=request_headers,
            params=pending_params,
            deadline=deadline,
            http_version=CurlHttpVersion.V1_1,
            on_event=on_event,
            sleep=sleep,
            monotonic=monotonic,
        )
        if response.status_code not in REDIRECT_STATUSES:
            return response
        location = response.headers.get("Location")
        if not location or redirect_count == MAX_REDIRECTS:
            raise RichBourseRedirectError("RichBourse redirect limit exceeded")
        target = urljoin(current_url, location)
        if not is_approved_url(target):
            raise RichBourseOriginError("RichBourse redirect is outside the approved origin")
        current_url = target
        pending_params = None  # the redirect target already carries its query
    raise RichBourseRedirectError("RichBourse redirect limit exceeded")


def _get_with_retries(
    getter: Callable[..., Any],
    url: str,
    *,
    headers: Mapping[str, str],
    params: Mapping[str, Any] | None,
    deadline: float,
    http_version: Any,
    on_event: EventHook | None,
    sleep: Sleep,
    monotonic: Monotonic,
) -> Any:
    """Return a 200 or redirect response; retry transient failures within the budget."""
    reason = "transport error"
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("RichBourse request deadline exceeded")
        kwargs: dict[str, Any] = {
            "headers": dict(headers),
            "timeout": remaining,
            "impersonate": "chrome",
            "http_version": http_version,
            "allow_redirects": False,
        }
        if params:
            kwargs["params"] = dict(params)
        try:
            response = getter(url, **kwargs)
        except Exception as error:
            last_error = error
            reason = "transport error"
            event_class = type(error).__name__
        else:
            last_error = None
            status = response.status_code
            retry_reason = _retry_reason(response)
            if retry_reason is None:
                if status in REDIRECT_STATUSES:
                    return response
                if status == 200:
                    if on_event is not None:
                        on_event("succeeded", attempt + 1, None)
                    return response
                if status == 403:
                    raise RichBourseBlocked("RichBourse blocked the request (HTTP 403)", status_code=403)
                raise RichBourseHTTPError(f"RichBourse HTTP {status}", status_code=status)
            reason = retry_reason
            event_class = retry_reason
        if attempt == MAX_ATTEMPTS - 1:
            break
        if on_event is not None:
            on_event("retry", attempt + 1, event_class)
        sleep(min(RETRY_DELAYS[attempt], max(0.0, deadline - monotonic())))

    message = f"RichBourse request unusable after {MAX_ATTEMPTS} attempts ({reason})"
    if reason == "challenge page":
        raise RichBourseBlocked(message) from last_error
    raise RichBourseUnavailable(message) from last_error
