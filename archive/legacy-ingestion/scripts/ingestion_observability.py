"""Bounded, credential-free operational events for packaged entry points."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import hashlib
import json
import re
from typing import Any, Callable, Iterable, Literal, TypeVar, TypedDict
from urllib.parse import urlparse

_SAFE = re.compile(r"[A-Za-z0-9_.:-]+\Z")
_SENSITIVE = re.compile(
    r"authorization|bearer|token|password|secret|api[_-]?key|email|uid|identifier|body",
    re.IGNORECASE,
)
_T = TypeVar("_T")
_ELIGIBLE_SOURCES = frozenset({"shares", "financials"})
_FINGERPRINT = re.compile(r"[a-f0-9]{64}\Z")
_FI1_PHASES = frozenset({"selection", "skip", "pdf", "text", "provider", "terminal"})
_FI1_OUTCOMES = frozenset({"selected", "skipped", "succeeded", "failed"})
_FI1_MODELS = frozenset({"gemma-4-31b-it", "nvidia/nemotron-3.5-lightning:free", "openai/gpt-4o-mini"})


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


def emit_fi1_candidate_diagnostic(
    phase: Literal["selection", "skip", "pdf", "text", "provider", "terminal"],
    outcome: Literal["selected", "skipped", "succeeded", "failed"],
    *,
    symbol: str,
    fiscal_year: int,
    announcement_title: str,
    document_link: str,
    duration_ms: int,
    error_class: str | None = None,
    model: str | None = None,
) -> None:
    """Emit the finite FI-1 development diagnostic schema, never generic fields."""
    try:
        parsed = urlparse(document_link)
        approved_link = (
            parsed.scheme == "https"
            and parsed.hostname == "www.richbourse.com"
            and parsed.port is None
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        approved_link = False
    if (
        phase not in _FI1_PHASES
        or outcome not in _FI1_OUTCOMES
        or _safe(symbol, limit=32) == "redacted"
        or not isinstance(fiscal_year, int)
        or not 1900 <= fiscal_year <= 3000
        or not announcement_title
        or len(announcement_title) > 256
        or not approved_link
        or not isinstance(duration_ms, int)
        or not 0 <= duration_ms <= 3_600_000
    ):
        raise ValueError("invalid FI-1 candidate diagnostic")
    fields: dict[str, Any] = {
        "event": "ingestion.fi1.candidate",
        "phase": phase,
        "outcome": outcome,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "symbol": _safe(symbol, limit=32),
        "fiscal_year": fiscal_year,
        "announcement_title": _safe(announcement_title, limit=256),
        "document_link": document_link,
        "duration_ms": duration_ms,
    }
    if error_class:
        fields["error_class"] = _safe(error_class, limit=128)
    if model is not None:
        if model not in _FI1_MODELS:
            raise ValueError("invalid FI-1 candidate diagnostic")
        fields["model"] = _safe(model, limit=128)
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
