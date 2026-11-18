"""Bounded, credential-free operational events for packaged entry points."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import re
from typing import Any, Callable, Iterable, Literal, TypeVar, TypedDict

_SAFE = re.compile(r"[A-Za-z0-9_.:-]+\Z")
_SENSITIVE = re.compile(
    r"authorization|bearer|token|password|secret|api[_-]?key|email|uid|identifier|body",
    re.IGNORECASE,
)
_T = TypeVar("_T")
_ELIGIBLE_SOURCES = frozenset({"shares", "financials"})
_FINGERPRINT = re.compile(r"[a-f0-9]{64}\Z")


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


class ManagedWriteReceipt(TypedDict):
    """Portable subset of the #253 managed-write receipt contract."""

    revision_fingerprint: str
    completed_at: str



class ManagedImportCompletion(TypedDict):
    """Portable successful-completion shape consumed by publication control."""

    source: Literal["shares", "financials"]
    status: Literal["succeeded"]
    managed_write: ManagedWriteReceipt


def managed_import_completion(
    source: Literal["shares", "financials"],
    revisions: Iterable[str],
    *,
    completed_at: datetime | None = None,
) -> ManagedImportCompletion:
    """Build one deterministic, sanitized completion after all writes succeed."""
    if source not in _ELIGIBLE_SOURCES:
        raise ValueError("only eligible ingestion sources may emit a completion")
    canonical_revisions = tuple(sorted(set(revisions)))
    if not canonical_revisions or any(_FINGERPRINT.fullmatch(value) is None for value in canonical_revisions):
        raise ValueError("completion requires successful managed-write revision fingerprints")
    fingerprint = hashlib.sha256(
        json.dumps(canonical_revisions, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    finished = completed_at or datetime.now(timezone.utc)
    if finished.tzinfo is None or finished.utcoffset() != timezone.utc.utcoffset(finished):
        raise ValueError("completion time must be an explicit UTC instant")
    return {
        "source": source,
        "status": "succeeded",
        "managed_write": {
            "revision_fingerprint": fingerprint,
            "completed_at": finished.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }


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
