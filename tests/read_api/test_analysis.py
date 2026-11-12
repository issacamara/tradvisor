from datetime import date, datetime, timezone

from backend.publication.analysis import ActivePublication, ServingOutput, ServingStock
from backend.read_api.analysis import read_chart
from backend.store.repositories import Page


class Publisher:
    def __init__(self, stock: ServingStock) -> None:
        self.stock = stock

    def active_publication(self) -> ActivePublication:
        return ActivePublication(
            batch_id="batch-1",
            catalog_id="catalog-1",
            effective_session="2026-01-03",
            input_snapshot_id="snapshot-1",
            rule_version="rules-1",
            revision=1,
            content_sha256="a" * 64,
            published_at="2026-01-03T12:00:00Z",
            strategy_id="strategy-1",
        )

    def read_batch(self, batch_id: str, *, limit: int, cursor: str | None = None) -> Page[ServingStock]:
        return Page(items=(self.stock,), next_cursor=None)


def test_read_chart_accepts_firestore_lists_and_preserves_filters() -> None:
    source_evidence = [{
        "source_id": "daily-prices",
        "collected_at": "2026-01-03T10:00:00Z",
        "basis": "actual",
    }]
    points = [
        {
            "session_date": "2026-01-01",
            "status": "traded",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "last_traded_close": None,
            "analytical_carried_close": None,
            "volume": None,
            "indicators": {"ema20": {"status": "assessable", "value": 12.0, "unit": "xof"}},
            "source_evidence": source_evidence,
        },
        {
            "session_date": "2026-01-02",
            "status": "traded",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "last_traded_close": None,
            "analytical_carried_close": None,
            "volume": None,
            "indicators": {
                "ema20": {"status": "assessable", "value": 13.0, "unit": "xof"},
                "rsi14": {"status": "assessable", "value": 55.0, "unit": "ratio"},
            },
            "source_evidence": source_evidence,
        },
    ]
    stock = ServingStock(
        batch_id="batch-1",
        catalog_id="catalog-1",
        effective_session="2026-01-03",
        input_snapshot_id="snapshot-1",
        rule_version="rules-1",
        revision=1,
        symbol="AAA",
        outputs=(
            ServingOutput(
                name="chart",
                status="available",
                value={
                    "symbol": "AAA",
                    "from": "2026-01-01",
                    "to": "2026-01-02",
                    "batch_id": "batch-pending",
                    "points": points,
                },
            ),
        ),
    )

    chart = read_chart(
        Publisher(stock),
        symbol="AAA",
        from_date=date(2026, 1, 2),
        to_date=date(2026, 1, 3),
        series=("ema20",),
        cursor_secret=b"test-secret",
        now=lambda: datetime(2026, 1, 3, tzinfo=timezone.utc),
    )

    assert [point.session_date for point in chart.points] == [date(2026, 1, 2)]
    assert chart.points[0].indicators["ema20"].value == 13.0
    assert "rsi14" not in chart.points[0].indicators
    assert chart.points[0].source_evidence[0].source_id == "daily-prices"
