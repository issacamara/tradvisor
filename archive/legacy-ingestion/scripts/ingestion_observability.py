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
_FI1_SYMBOL_OUTCOMES = frozenset({"succeeded", "failed"})
_FI1_FAILURE_STAGES = frozenset({"state", "selector", "lease", "writer", "completion"})


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


def emit_fi1_symbol_outcome(
    symbol: str, outcome: Literal["succeeded", "failed"], *, error_class: str | None = None
) -> None:
    """Emit one bounded terminal outcome for one processed symbol."""
    safe_symbol = _safe(symbol, limit=32)
    if safe_symbol == "redacted" or outcome not in _FI1_SYMBOL_OUTCOMES:
        raise ValueError("invalid FI-1 symbol outcome")
    if outcome == "succeeded" and error_class is not None:
        raise ValueError("successful FI-1 symbol outcome cannot include an error")
    fields: dict[str, Any] = {
        "event": "ingestion.fi1.symbol",
        "outcome": outcome,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "symbol": safe_symbol,
    }
    if error_class is not None:
        fields["error_class"] = _safe(error_class, limit=128)
    print(json.dumps(fields, separators=(",", ":"), sort_keys=True))


def emit_fi1_commit_counts(*, inserted: int, updated: int) -> None:
    """Emit mutation counts only after a managed write receipt is validated."""
    if (
        not isinstance(inserted, int)
        or not isinstance(updated, int)
        or inserted < 0
        or updated < 0
        or inserted + updated <= 0
        or inserted + updated > 1_000_000_000
    ):
        raise ValueError("invalid FI-1 commit counts")
    fields = {
        "event": "ingestion.fi1.commit",
        "outcome": "committed",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "inserted": inserted,
        "updated": updated,
    }
    print(json.dumps(fields, separators=(",", ":"), sort_keys=True))


def emit_fi1_stage_failure(
    stage: Literal["state", "selector", "lease", "writer", "completion"],
    *,
    error_class: str,
) -> None:
    """Emit only the bounded FI-1 stages that can fail before an outcome."""
    if stage not in _FI1_FAILURE_STAGES or _safe(error_class, limit=128) == "redacted":
        raise ValueError("invalid FI-1 stage failure")
    fields = {
        "event": "ingestion.fi1.failure",
        "outcome": "failed",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "error_class": _safe(error_class, limit=128),
    }
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
