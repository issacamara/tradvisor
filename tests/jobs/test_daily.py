from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone

import pytest

from backend.analysis.batch import CalculationOutput, StockCalculation
from backend.jobs.daily import (
    AnalyticalInputSnapshot,
    DailyAnalyticalWorker,
    DailyError,
    _run_identity,
)


NOW = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)


def _snapshot(*, ready: bool = True, pending: tuple[str, ...] = ()) -> AnalyticalInputSnapshot:
    return AnalyticalInputSnapshot(
        name="brvm-close-2026-09-27",
        catalog_id="brvm",
        effective_session=date(2026, 9, 27),
        input_snapshot_id="bq-snapshot-2026-09-27",
        rule_version="analysis-v1",
        expected_symbols=("AAA", "BBB"),
        expected_output_names=("long_term", "swing"),
        payload={"source": "fixture"},
        inputs_ready=ready,
        pending_inputs=pending,
        published_at=NOW,
        strategy_id="swing-v1",
    )


class SnapshotReader:
    def __init__(self, snapshot: AnalyticalInputSnapshot | None) -> None:
        self.snapshot = snapshot
        self.names: list[str] = []

    def read(self, snapshot_name: str) -> AnalyticalInputSnapshot | None:
        self.names.append(snapshot_name)
        return self.snapshot


class Calculator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def calculate(self, snapshot: AnalyticalInputSnapshot, *, symbol: str) -> StockCalculation:
        self.calls.append(symbol)
        assert snapshot.payload["source"] == "fixture"
        return StockCalculation(
            symbol,
            (
                CalculationOutput("long_term", "unavailable", reason_codes=("missing_inputs",)),
                CalculationOutput("swing", "available", {"action": "keep"}),
            ),
        )


@dataclass
class Publisher:
    publications: list[object]
    fail: bool = False

    def publish(self, batch: object) -> object:
        if self.fail:
            raise RuntimeError("mid-copy")
        self.publications.append(batch)
        return {"batch_id": getattr(batch, "batch_id")}


def test_worker_reads_one_named_snapshot_and_calculates_each_symbol_once() -> None:
    reader = SnapshotReader(_snapshot())
    calculator = Calculator()
    publisher = Publisher([])

    result = DailyAnalyticalWorker(
        snapshots=reader, calculator=calculator, publisher=publisher
    ).run("brvm-close-2026-09-27")

    assert result.status == "published"
    assert result.batch_id is not None
    assert reader.names == ["brvm-close-2026-09-27"]
    assert calculator.calls == ["AAA", "BBB"]
    batch = publisher.publications[0]
    assert {stock.symbol for stock in batch.stocks} == {"AAA", "BBB"}
    assert batch.published_at == NOW
    assert batch.strategy_id == "swing-v1"


@pytest.mark.parametrize(
    ("snapshot",),
    [(_snapshot(ready=False),), (_snapshot(pending=("financials",)),)],
)
def test_worker_does_not_publish_when_snapshot_is_not_ready(
    snapshot: AnalyticalInputSnapshot,
) -> None:
    calculator = Calculator()
    publisher = Publisher([])

    result = DailyAnalyticalWorker(
        snapshots=SnapshotReader(snapshot), calculator=calculator, publisher=publisher
    ).run(snapshot.name)

    assert result.status == "unchanged"
    assert calculator.calls == []
    assert publisher.publications == []


def test_worker_rejects_reader_name_mismatch_without_publishing() -> None:
    snapshot = replace(_snapshot(), name="other")

    with pytest.raises(DailyError, match="different named snapshot"):
        DailyAnalyticalWorker(
            snapshots=SnapshotReader(snapshot), calculator=Calculator(), publisher=Publisher([])
        ).run("brvm-close-2026-09-27")


def test_retry_identity_is_stable_for_the_same_input_session_and_rule() -> None:
    first = _run_identity(_snapshot())
    second = _run_identity(_snapshot())

    assert first == second
    assert first.startswith("analysis-run-v1:")


def test_worker_preserves_publication_failure_as_daily_error() -> None:
    with pytest.raises(DailyError, match="previous publication remains active"):
        DailyAnalyticalWorker(
            snapshots=SnapshotReader(_snapshot()),
            calculator=Calculator(),
            publisher=Publisher([], fail=True),
        ).run("brvm-close-2026-09-27")
