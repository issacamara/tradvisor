"""Cloud Run composition for one development analytical publication.

BigQuery owns the expensive daily calculations.  This module only reads the
named immutable result envelope and hands its already-calculated outputs to
the existing atomic Firestore publisher.
"""

from __future__ import annotations

import json
import os
import hashlib
from datetime import date, datetime
from typing import Any, Callable, Literal, Mapping, Protocol, cast

from backend.analysis.batch import CalculationOutput, StockCalculation
from backend.jobs.daily import (
    AnalyticalInputSnapshot,
    AnalyticalSnapshotReader,
    DailyAnalyticalWorker,
    VersionedCalculator,
)
from backend.publication.analysis import AnalyticalPublisher
from backend.store.firestore_sdk import FirestoreSdkStore


class QueryClient(Protocol):
    def query(self, query: str, *, job_config: Any) -> Any: ...


class ActivePublicationReader(Protocol):
    def active_publication(self) -> Any | None: ...


class BigQuerySnapshotReader(AnalyticalSnapshotReader):
    """Read exactly one immutable JSON snapshot from a BigQuery table."""

    def __init__(self, client: QueryClient, table: str, active_publication: Callable[[], Any | None] | None = None) -> None:
        if not table or "`" in table or ";" in table:
            raise ValueError("snapshot table must be a plain project.dataset.table identifier")
        self._client = client
        self._table = table
        self._active_publication = active_publication

    def read(self, snapshot_name: str) -> AnalyticalInputSnapshot | None:
        from google.cloud import bigquery  # type: ignore[import-untyped]

        query = (
            f"SELECT snapshot_json FROM `{self._table}` "
            "WHERE snapshot_name = @snapshot_name "
            "AND publication_status = 'published' "
            "ORDER BY published_at DESC LIMIT 1"
        )
        config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("snapshot_name", "STRING", snapshot_name)]
        )
        rows = list(self._client.query(query, job_config=config).result())
        if not rows:
            return None
        if len(rows) != 1:
            raise ValueError("BigQuery snapshot lookup returned more than one row")
        raw = rows[0]["snapshot_json"]
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(payload, Mapping):
            raise ValueError("snapshot_json must be a JSON object")
        # The analytical snapshot currently contains indicators only. Enrich it
        # with a bounded market-data window so the serving copy can expose the
        # close-price chart and provide enough history for the V1 calculations.
        market_table = os.environ.get("MARKET_DATA_TABLE", "dev-tradvisor.stocks.shares").strip()
        analytical_table = os.environ.get("ANALYTICAL_MARKET_DATA_TABLE", "dev-tradvisor.stocks.shares_analytical").strip()
        for name, value in (("market data", market_table), ("analytical market data", analytical_table)):
            if not value or "`" in value or ";" in value:
                raise ValueError(f"{name} table must be a plain project.dataset.table identifier")
        self._client.query(
            "CREATE OR REPLACE TABLE `" + analytical_table + "` "
            "PARTITION BY date CLUSTER BY symbol AS "
            "SELECT symbol, name, open, high, low, close, volume, date "
            "FROM `" + market_table + "` "
            "WHERE date IS NOT NULL AND date >= DATE_SUB((SELECT MAX(date) FROM `" + market_table + "`), INTERVAL 400 DAY)",
            job_config=bigquery.QueryJobConfig(),
        ).result()
        market_rows = list(self._client.query(
            "SELECT symbol, date, open, high, low, close, volume "
            f"FROM `{analytical_table}` "
            "WHERE date IS NOT NULL "
            "ORDER BY symbol, date",
            job_config=bigquery.QueryJobConfig(),
        ).result())
        market_data = [
            {
                "symbol": str(row["symbol"]),
                "session_date": row["date"].isoformat(),
                "open": row["open"], "high": row["high"], "low": row["low"],
                "close": row["close"], "volume": row["volume"],
            }
            for row in market_rows
            if row["date"] is not None
        ]
        market_data_fingerprint = hashlib.sha256(
            json.dumps(market_data, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        symbols = tuple(sorted({item["symbol"] for item in market_data}))
        effective_session = max((date.fromisoformat(item["session_date"]) for item in market_data), default=date.fromisoformat(str(payload["effective_session"])))
        enriched_payload = dict(cast(Mapping[str, Any], payload.get("payload", {})))
        enriched_payload["market_data"] = market_data
        expected_output_names = tuple(dict.fromkeys((*map(str, payload["expected_output_names"]), "chart")))
        active = self._active_publication() if self._active_publication is not None else None
        revision = int(payload.get("revision", 1))
        supersedes_batch_id = payload.get("supersedes_batch_id")
        if active is not None and active.effective_session == effective_session.isoformat():
            revision = max(revision, int(active.revision) + 1)
            supersedes_batch_id = str(active.batch_id)
        return AnalyticalInputSnapshot(
            name=str(payload["name"]),
            catalog_id=str(payload["catalog_id"]),
            effective_session=effective_session,
            # The chart is derived from the bounded shares window as well as
            # the named analytical snapshot. Include both in the immutable
            # batch identity so changed market data cannot collide with an
            # earlier partially published batch.
            input_snapshot_id=f"{payload['input_snapshot_id']}:market-{market_data_fingerprint}",
            rule_version=str(payload["rule_version"]),
            expected_symbols=symbols or tuple(str(item) for item in payload["expected_symbols"]),
            expected_output_names=expected_output_names,
            payload=enriched_payload,
            inputs_ready=bool(payload.get("inputs_ready", True)),
            pending_inputs=tuple(str(item) for item in payload.get("pending_inputs", ())),
            revision=revision,
            supersedes_batch_id=supersedes_batch_id,
            published_at=(
                None
                if payload.get("published_at") is None
                else datetime.fromisoformat(str(payload["published_at"]))
            ),
            strategy_id=payload.get("strategy_id"),
        )


class BigQueryOutputCalculator(VersionedCalculator):
    """Expose BigQuery's versioned EMA/RSI/ATR/liquidity output envelope."""

    def calculate(self, snapshot: AnalyticalInputSnapshot, *, symbol: str) -> StockCalculation:
        calculations = snapshot.payload.get("calculations", {})
        outputs = calculations.get(symbol)
        result = tuple(
            CalculationOutput(
                name=name,
                status=_status(item.get("status")),
                value=item.get("value"),
                reason_codes=tuple(str(reason) for reason in item.get("reason_codes", ())),
            )
            for name, item in outputs.items()
        ) if isinstance(outputs, Mapping) else ()
        present = {item.name for item in result}
        result += tuple(
            CalculationOutput(name=name, status="unavailable", reason_codes=("analysis_not_published",))
            for name in snapshot.expected_output_names
            if name not in present and name != "chart"
        )
        market = [item for item in snapshot.payload.get("market_data", ()) if item.get("symbol") == symbol]
        if market:
            points = tuple({
                "session_date": item["session_date"], "status": "traded" if item.get("close") is not None else "missing_price",
                "open": _money(item.get("open")), "high": _money(item.get("high")),
                "low": _money(item.get("low")), "close": _money(item.get("close")),
                "last_traded_close": _money(item.get("close")),
                "analytical_carried_close": None, "volume": int(item["volume"]) if item.get("volume") is not None else None,
                "indicators": {}, "source_evidence": [],
            } for item in market)
            result += (CalculationOutput(
                name="chart", status="available", value={
                    "symbol": symbol, "from": points[0]["session_date"], "to": points[-1]["session_date"],
                    "batch_id": "batch-pending", "points": points,
                },
            ),)
        return StockCalculation(symbol=symbol, outputs=result)


def _money(value: object) -> dict[str, str] | None:
    """Serialize BigQuery XOF values into the exact API money contract."""
    if value is None:
        return None
    return {"amount": str(value), "currency": "XOF"}


def build_worker() -> DailyAnalyticalWorker:
    project_id = _required("GOOGLE_CLOUD_PROJECT")
    table = _required("ANALYTICAL_SNAPSHOT_TABLE")
    secret = _required("FIRESTORE_CURSOR_SECRET")
    from google.cloud import bigquery

    store = FirestoreSdkStore(project_id=project_id, cursor_secret=secret)
    publisher = AnalyticalPublisher(store)
    return DailyAnalyticalWorker(
        snapshots=BigQuerySnapshotReader(bigquery.Client(project=project_id), table, publisher.active_publication),
        calculator=BigQueryOutputCalculator(),
        publisher=publisher,
    )


def run_from_environment() -> None:
    snapshot_name = _required("ANALYTICAL_SNAPSHOT_NAME")
    result = build_worker().run(snapshot_name)
    print(json.dumps({"run_id": result.run_id, "status": result.status, "batch_id": result.batch_id}))


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _status(value: object) -> Literal["available", "unavailable"]:
    if value not in {"available", "unavailable"}:
        raise ValueError("calculation status must be available or unavailable")
    return cast(Literal["available", "unavailable"], value)
