"""Retry-stable daily orchestration over one immutable analytical snapshot.

The worker deliberately depends on protocols rather than cloud SDKs.  A
production adapter can read a named BigQuery snapshot, while local tests use
an in-memory reader and calculator.  The publisher remains responsible for
the complete-copy gate and active-pointer transition.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Protocol

from backend.analysis.batch import (
    AnalyticalBatch,
    StockCalculation,
    build_analytical_batch,
)


class DailyError(RuntimeError):
    """A daily run failed before a new publication could be promoted."""


class BatchFactory(Protocol):
    def build(self, *, run_id: str) -> Any | None: ...


class Publisher(Protocol):
    def publish(self, batch: Any) -> object: ...


@dataclass(frozen=True, slots=True)
class AnalyticalInputSnapshot:
    """The named, point-in-time BigQuery view consumed by one daily run."""

    name: str
    catalog_id: str
    effective_session: date | str
    input_snapshot_id: str
    rule_version: str
    expected_symbols: tuple[str, ...]
    expected_output_names: tuple[str, ...]
    payload: Mapping[str, Any]
    inputs_ready: bool = True
    pending_inputs: tuple[str, ...] = ()
    revision: int = 1
    supersedes_batch_id: str | None = None
    published_at: datetime | None = None
    strategy_id: str | None = None


class AnalyticalSnapshotReader(Protocol):
    def read(self, snapshot_name: str) -> AnalyticalInputSnapshot | None: ...


class VersionedCalculator(Protocol):
    def calculate(
        self, snapshot: AnalyticalInputSnapshot, *, symbol: str
    ) -> StockCalculation: ...


class SnapshotBatchFactory:
    """Invoke the selected calculator once for every expected symbol."""

    def __init__(
        self, snapshot: AnalyticalInputSnapshot, calculator: VersionedCalculator
    ) -> None:
        self._snapshot = snapshot
        self._calculator = calculator
        self._built: AnalyticalBatch | None = None

    def build(self, *, run_id: str) -> AnalyticalBatch:
        del run_id
        if self._built is None:
            stocks = tuple(
                self._calculator.calculate(self._snapshot, symbol=symbol)
                for symbol in self._snapshot.expected_symbols
            )
            self._built = build_analytical_batch(
                catalog_id=self._snapshot.catalog_id,
                effective_session=self._snapshot.effective_session,
                input_snapshot_id=self._snapshot.input_snapshot_id,
                rule_version=self._snapshot.rule_version,
                expected_symbols=self._snapshot.expected_symbols,
                expected_output_names=self._snapshot.expected_output_names,
                stocks=stocks,
                inputs_ready=self._snapshot.inputs_ready,
                pending_inputs=self._snapshot.pending_inputs,
                revision=self._snapshot.revision,
                supersedes_batch_id=self._snapshot.supersedes_batch_id,
                published_at=self._snapshot.published_at,
                strategy_id=self._snapshot.strategy_id,
            )
        return self._built


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


class DailyAnalyticalWorker:
    """Build and publish one named snapshot without running cloud work in reads."""

    def __init__(
        self,
        *,
        snapshots: AnalyticalSnapshotReader,
        calculator: VersionedCalculator,
        publisher: Publisher,
    ) -> None:
        self._snapshots = snapshots
        self._calculator = calculator
        self._publisher = publisher

    def run(self, snapshot_name: str) -> DailyRunResult:
        if not snapshot_name or len(snapshot_name) > 256:
            raise ValueError("snapshot_name is required and bounded")
        snapshot = self._snapshots.read(snapshot_name)
        if snapshot is None or not snapshot.inputs_ready or snapshot.pending_inputs:
            return DailyRunResult(snapshot_name, "unchanged", None, None)
        if snapshot.name != snapshot_name:
            raise DailyError("snapshot reader returned a different named snapshot")

        run_id = _run_identity(snapshot)
        factory = SnapshotBatchFactory(snapshot, self._calculator)
        return run_daily(run_id=run_id, factory=factory, publisher=self._publisher)


def _run_identity(snapshot: AnalyticalInputSnapshot) -> str:
    identity = "|".join(
        (
            snapshot.catalog_id,
            str(snapshot.effective_session),
            snapshot.input_snapshot_id,
            snapshot.rule_version,
        )
    )
    return f"analysis-run-v1:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"
