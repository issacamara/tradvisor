"""Bounded, credential-free operational events for packaged entry points."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import json
import re
from typing import Any, Callable, TypeVar

_SAFE = re.compile(r"[A-Za-z0-9_.:-]+\Z")
_SENSITIVE = re.compile(
    r"authorization|bearer|token|password|secret|api[_-]?key|email|uid|identifier|body",
    re.IGNORECASE,
)
_T = TypeVar("_T")


def _safe(value: str, *, limit: int = 128) -> str:
    if not value or len(value) > limit or _SENSITIVE.search(value) or _SAFE.fullmatch(value) is None:
        return "redacted"
    return value


def emit_event(name: str, outcome: str, *, count: int | None = None, error_class: str | None = None) -> None:
    """Write one bounded JSON event; never serialize provider/error details."""
    fields: dict[str, Any] = {
        "event": _safe(name, limit=64),
        "outcome": _safe(outcome, limit=64),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 0,
    }
    if count is not None and isinstance(count, int) and 0 <= count <= 1_000_000_000:
        fields["count"] = count
    if error_class:
        fields["error_class"] = _safe(error_class, limit=128)
    print(json.dumps(fields, separators=(",", ":"), sort_keys=True))


def observed_entrypoint(name: str) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Capture success and failure without exposing exception or provider text."""
    def decorate(function: Callable[..., _T]) -> Callable[..., _T]:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> _T:
            try:
                result = function(*args, **kwargs)
            except Exception as error:
                emit_event(name, "failed", error_class=type(error).__name__)
                raise
            emit_event(name, "succeeded")
            return result

        return wrapped

    return decorate
