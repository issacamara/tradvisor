"""Bounded retention planning that protects active and restorable evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
RETENTION_DAYS = {"reset": 7, "receipt": 30, "recommendation": 365}


@dataclass(frozen=True, slots=True)
class RetentionItem:
    item_id: str
    kind: str
    created_at: datetime
    generation: str | None = None
    active: bool = False
    restore_protected: bool = False
    cleanup_known: bool = True


@dataclass(frozen=True, slots=True)
class CleanupDecision:
    deletable: tuple[str, ...]
    protected: tuple[tuple[str, str], ...]


def plan_cleanup(items: tuple[RetentionItem, ...], *, now: datetime, limit: int = 100) -> CleanupDecision:
    if not 1 <= limit <= 1000:
        raise ValueError("cleanup limit must be between 1 and 1000")
    deletable: list[str] = []
    protected: list[tuple[str, str]] = []
    for item in sorted(items, key=lambda value: (value.created_at, value.item_id)):
        if len(deletable) >= limit:
            break
        if item.active or item.restore_protected:
            protected.append((item.item_id, "protected_reference"))
            continue
        if not item.cleanup_known:
            protected.append((item.item_id, "cleanup_eligibility_unknown"))
            continue
        days = RETENTION_DAYS.get(item.kind)
        if days is None:
            protected.append((item.item_id, "unknown_retention_policy"))
            continue
        if now.astimezone(UTC) - item.created_at.astimezone(UTC) >= timedelta(days=days):
            deletable.append(item.item_id)
        else:
            protected.append((item.item_id, "retention_window_open"))
    return CleanupDecision(tuple(deletable), tuple(protected))
