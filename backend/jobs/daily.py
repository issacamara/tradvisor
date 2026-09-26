"""Retry-stable daily orchestration over recorded, local source fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class DailyError(RuntimeError):
    """A daily run failed before a new publication could be promoted."""


class BatchFactory(Protocol):
    def build(self, *, run_id: str) -> Any | None: ...


class Publisher(Protocol):
    def publish(self, batch: Any) -> object: ...


@dataclass(frozen=True, slots=True)
class DailyRunResult:
    run_id: str
    status: str
    batch_id: str | None
    publication: object | None


def run_daily(*, run_id: str, factory: BatchFactory, publisher: Publisher) -> DailyRunResult:
    """Build and publish once; no external extraction or order creation occurs here."""
    if not run_id or len(run_id) > 128:
        raise ValueError("run_id is required and bounded")
    batch = factory.build(run_id=run_id)
    if batch is None:
        return DailyRunResult(run_id, "unchanged", None, None)
    try:
        publication = publisher.publish(batch)
    except Exception as error:
        raise DailyError("daily publication failed; previous publication remains active") from error
    return DailyRunResult(run_id, "published", batch.batch_id, publication)
