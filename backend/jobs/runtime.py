"""Cloud Run composition for one development analytical publication.

BigQuery owns the expensive daily calculations.  This module only reads the
named immutable result envelope and hands its already-calculated outputs to
the existing atomic Firestore publisher.
"""

from __future__ import annotations

import json
import os
import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Literal, Mapping, Protocol, cast

from backend.analysis.batch import CalculationOutput, StockCalculation
from backend.analysis.atr import calculate_atr14
from backend.analysis.ema import calculate_ema20_50
from backend.analysis.inputs import AnalyticalInputSnapshot as TechnicalSnapshot, SessionInput
from backend.analysis.liquidity import CurrentTradeGate as LiquidityTradeGate, LiquidityResult
from backend.analysis.rsi import calculate_rsi14
from backend.analysis.swing import CurrentTradeGate, SwingStrategyInput, evaluate_swing
from backend.analysis.growth_core import GrowthInput, calculate_growth_core
from backend.contracts.analysis import NormalizedFinancial, Provenance, Revision
from backend.contracts.scalars import NonNegativeMoney, SignedMoney
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
        financial_data: list[dict[str, Any]] = []
        financial_table = os.environ.get("ANALYTICAL_FINANCIALS_TABLE", "").strip()
        if financial_table:
            if "`" in financial_table or ";" in financial_table or any(char.isspace() for char in financial_table):
                raise ValueError("analytical financials table must be a plain project.dataset.table identifier")
            financial_rows = list(self._client.query(
                "SELECT symbol, fiscal_year, revenue, net_income, total_equity, collected_at, document_link "
                f"FROM `{financial_table}` ORDER BY symbol, fiscal_year",
                job_config=bigquery.QueryJobConfig(),
            ).result())
            financial_data = [
                {
                    "symbol": str(row["symbol"]), "fiscal_year": int(row["fiscal_year"]),
                    "revenue": row["revenue"], "net_income": row["net_income"],
                    "total_equity": row["total_equity"],
                    "collected_at": row["collected_at"].isoformat() if row["collected_at"] is not None else None,
                    "document_link": row["document_link"],
                }
                for row in financial_rows
            ]
        market_data_fingerprint = hashlib.sha256(
            json.dumps({"market": market_data, "financial": financial_data}, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        symbols = tuple(sorted({item["symbol"] for item in market_data}))
        effective_session = max((date.fromisoformat(item["session_date"]) for item in market_data), default=date.fromisoformat(str(payload["effective_session"])))
        enriched_payload = dict(cast(Mapping[str, Any], payload.get("payload", {})))
        enriched_payload["market_data"] = market_data
        if financial_table:
            enriched_payload["financial_data"] = financial_data
        expected_output_names = tuple(
            dict.fromkeys((*map(str, payload["expected_output_names"]), "chart", "swing", "long_term"))
        )
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
        result = [
            CalculationOutput(
                name=name,
                status=_status(item.get("status")),
                value=item.get("value"),
                reason_codes=tuple(str(reason) for reason in item.get("reason_codes", ())),
            )
            for name, item in outputs.items()
        ] if isinstance(outputs, Mapping) else []
        market = [item for item in snapshot.payload.get("market_data", ()) if item.get("symbol") == symbol]
        if market:
            # Prefer the development-derived recommendation when the named
            # snapshot has no usable Swing result. Keep one output per family;
            # batch validation intentionally rejects duplicate families.
            existing_swing = next((item for item in result if item.name == "swing"), None)
            if existing_swing is None or existing_swing.status == "unavailable":
                result = [item for item in result if item.name != "swing"]
                result.append(_development_swing_output(snapshot, symbol, market))
        if market:
            points = tuple({
                "session_date": item["session_date"], "status": "traded" if item.get("close") is not None else "missing_price",
                "open": _money(item.get("open")), "high": _money(item.get("high")),
                "low": _money(item.get("low")), "close": _money(item.get("close")),
                "last_traded_close": _money(item.get("close")),
                "analytical_carried_close": None, "volume": int(item["volume"]) if item.get("volume") is not None else None,
                "indicators": {}, "source_evidence": [],
            } for item in market)
            result.append(CalculationOutput(
                name="chart", status="available", value={
                    "symbol": symbol, "from": points[0]["session_date"], "to": points[-1]["session_date"],
                    "batch_id": "batch-pending", "points": points,
                },
            ))
        existing_long_term = next((item for item in result if item.name == "long_term"), None)
        # A development financial snapshot is authoritative for this adapter.
        # Recompute even when an older publication contains an available but
        # incomplete placeholder; otherwise stale missing-input rows persist.
        if "financial_data" in snapshot.payload or existing_long_term is None or existing_long_term.status == "unavailable":
            result = [item for item in result if item.name != "long_term"]
            result.append(_development_long_term_output(snapshot, symbol))
        present = {item.name for item in result}
        result.extend(
            CalculationOutput(name=name, status="unavailable", reason_codes=("analysis_not_published",))
            for name in snapshot.expected_output_names
            if name not in present
        )
        return StockCalculation(symbol=symbol, outputs=tuple(result))


def _development_long_term_output(
    snapshot: AnalyticalInputSnapshot, symbol: str
) -> CalculationOutput:
    """Publish an explicit Long-Term research row when financial inputs are absent.

    The development shares snapshot is sufficient to identify a catalog symbol,
    but it is not sufficient to manufacture a Growth score. Keeping the row in
    the serving copy lets the UI expose the company and its evidence state while
    preserving the V1-deferred Dividend and Balanced objectives.
    """
    financials = tuple(
        _normalized_financial(row, symbol=symbol)
        for row in snapshot.payload.get("financial_data", ())
        if isinstance(row, Mapping) and row.get("symbol") == symbol
    )
    core = None
    score_status = "missing_inputs"
    score_value: float | None = None
    score_reasons = ["annual_financial_history_incomplete"]
    if len(financials) == 3:
        try:
            core = calculate_growth_core(GrowthInput(company_id=f"brvm:{symbol}", financials=financials))
        except (TypeError, ValueError):
            core = None
    reason = "annual_financial_history_incomplete" if core is None else "growth_inputs_partial"
    score = {
        "status": "missing_inputs",
        "value": None,
        "unit": "score",
        "reason_codes": [reason],
    }
    dimensions = {}
    if core is not None:
        for name, term in (("earnings_growth", core.earnings_growth), ("profitability", core.profitability)):
            if term.status == "assessable":
                dimensions[name] = {
                    "status": "assessable", "value": float(term.points or 0), "unit": "points",
                    "reason_codes": list(term.reason_codes), "evidence_refs": list(term.evidence_refs),
                }
        score_value = sum(
            float(term.points or 0)
            for term in (core.earnings_growth, core.profitability)
            if term.status == "assessable"
        )
        score_status = "warming_up"
        score_reasons = ["partial_dimension_coverage"]
        if any(
            "annual_history_gap" in term.reason_codes
            for term in (core.earnings_growth, core.profitability)
        ):
            score_reasons.append("annual_history_gap")
    deferred_dividend = {
        "status": "deferred_scope",
        "value": None,
        "unit": "score",
        "reason_codes": ["dividend_scoring_deferred_v1"],
    }
    deferred_balanced = {
        "status": "deferred_scope",
        "value": None,
        "unit": "score",
        "reason_codes": ["balanced_scoring_deferred_v1"],
    }
    revision = {
        "revision": snapshot.revision,
        "known_at": "1970-01-01T00:00:00Z",
        "provenance": {
            "source_id": "development-publication",
            "collected_at": "1970-01-01T00:00:00Z",
            "published_at": None,
            "source_url": None,
            "original_unit": None,
            "basis": "modeled",
        },
    }
    value = {
        "company_id": f"brvm:{symbol}",
        "symbol": symbol,
        "result": {
            "company_id": f"brvm:{symbol}",
            "growth": {"objective": "growth", "overall_score": {**score, "status": score_status, "value": score_value, "reason_codes": score_reasons}},
            "dividend": {"objective": "dividend", "overall_score": deferred_dividend},
            "balanced": {"objective": "balanced", "overall_score": deferred_balanced},
            "revision": revision,
        },
        "growth": {
            "growth_score": {**score, "status": score_status, "value": score_value, "reason_codes": score_reasons},
            "overall_score": {**score, "status": score_status, "value": score_value, "reason_codes": score_reasons},
            "dimension_contributions": dimensions,
            "advisory_state": "insufficient_evidence" if not dimensions else "low_score",
                "reasons": [{"code": reason, "message": "Three consecutive comparable annual reports are not available."}],
        },
        "dividend_research": {
            "payments": [],
            "coverage": [],
            "trailing_ordinary_yield": None,
            "dividend_score": deferred_dividend,
        },
    }
    return CalculationOutput(name="long_term", status="available", value=value)


def _normalized_financial(row: Mapping[str, Any], *, symbol: str) -> NormalizedFinancial:
    year = int(row["fiscal_year"])
    collected = row.get("collected_at")
    known_at = (
        datetime.fromisoformat(str(collected).replace("Z", "+00:00"))
        if collected else datetime(1970, 1, 1, tzinfo=timezone.utc)
    )
    provenance = Provenance(
        source_id="development-financials",
        collected_at=known_at, source_url=row.get("document_link"), basis="actual",
    )
    def money(value: Any, *, non_negative: bool = False) -> Any:
        if value is None:
            return None
        cls = NonNegativeMoney if non_negative else SignedMoney
        return cls(amount=str(value), currency="XOF")
    return NormalizedFinancial(
        company_id=f"brvm:{symbol}", fiscal_period_start=date(year, 1, 1), fiscal_period_end=date(year, 12, 31),
        report_scope="standalone", currency="XOF", original_scale="units",
        revenue=money(row.get("revenue"), non_negative=True), ordinary_owner_earnings=money(row.get("net_income")),
        equity=money(row.get("total_equity")), opening_equity=money(row.get("total_equity")),
        publication_status="published", revision=Revision(revision=1, known_at=known_at, provenance=provenance),
    )


def _development_swing_output(
    snapshot: AnalyticalInputSnapshot, symbol: str, market: list[Mapping[str, Any]]
) -> CalculationOutput:
    """Derive a development Swing recommendation from the bounded shares feed.

    The source table has dated OHLCV rows but no normalized calendar or
    provenance contract.  This adapter therefore labels every metric as
    estimated and binds it to the source snapshot; it is intentionally kept in
    the development publication path until the normalized ingestion contract is
    available.
    """
    rows = sorted(market, key=lambda item: str(item["session_date"]))
    evidence = "development_shares_snapshot"
    sessions: list[SessionInput] = []
    previous_close: int | None = None
    for index, row in enumerate(rows):
        session_date = date.fromisoformat(str(row["session_date"]))
        close = _micros(row.get("close"))
        high = _micros(row.get("high"))
        low = _micros(row.get("low"))
        true_range = None
        true_range_state = "unknown"
        if close is not None and high is not None and low is not None:
            if previous_close is None:
                true_range = high - low
            else:
                true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
            true_range_state = "observed"
        sessions.append(SessionInput(
            session_id=f"dev-shares:{symbol}:{session_date.isoformat()}",
            session_date=session_date, session_index=index,
            price_basis_ref=evidence, close_micros=close,
            close_state="traded" if close is not None else "unknown",
            close_segment=0 if close is not None else None,
            true_range_state=true_range_state, true_range_micros=true_range,
            source_price_revision=1,
        ))
        previous_close = close
    if not sessions:
        return CalculationOutput(name="swing", status="unavailable", reason_codes=("history_incomplete",))
    technical = TechnicalSnapshot(
        snapshot_id=f"{snapshot.input_snapshot_id}:swing:{symbol}",
        contract_version="analysis-input-v1", symbol=symbol,
        as_of=datetime.now(timezone.utc), calendar_version="development-shares-calendar",
        sessions=tuple(sessions),
    )
    rule_version = snapshot.rule_version
    ema20, ema50 = calculate_ema20_50(technical, rule_version=rule_version)
    rsi14 = calculate_rsi14(technical, rule_version=rule_version)
    atr14 = calculate_atr14(technical, rule_version=rule_version)
    window = rows[-20:]
    turnovers = [
        Decimal(str(row["close"])) * Decimal(str(row["volume"]))
        for row in window
        if row.get("close") is not None and row.get("volume") is not None
    ]
    median = sorted(turnovers)[len(turnovers) // 2] if turnovers else None
    if len(turnovers) == 20 and len(turnovers) % 2 == 0:
        ordered = sorted(turnovers)
        median = (ordered[9] + ordered[10]) / Decimal(2)
    liquidity = LiquidityResult(
        technical.snapshot_id, "assessable" if len(turnovers) == 20 else "unavailable",
        median if len(turnovers) == 20 else None,
        len(turnovers) if len(turnovers) == 20 else None, "estimated" if len(turnovers) == 20 else None,
        None if len(turnovers) != 20 else median >= Decimal("5000000") and len(turnovers) >= 18,
        tuple(item.session_id for item in technical.sessions[-20:]), (evidence,),
        () if len(turnovers) == 20 else ("history_incomplete",),
    )
    current = technical.sessions[-1]
    strategy = evaluate_swing(SwingStrategyInput(
        snapshot=technical, ema20=ema20, ema50=ema50, rsi14=rsi14, atr14=atr14,
        liquidity=liquidity,
        current_trade=CurrentTradeGate(
            str(technical.snapshot_id), str(current.session_id),
            "pass" if current.close_state == "traded" else "unknown", (evidence,),
            () if current.close_state == "traded" else ("current_price_missing",),
        ),
    ))
    points = {
        "ema20": _latest_metric(ema20.points, evidence, "value"),
        "ema50": _latest_metric(ema50.points, evidence, "value"),
        "rsi14": _latest_metric(rsi14.points, evidence, "value"),
        "atr14": _latest_metric(atr14.points, evidence, "value"),
        "traded_value20": _metric(median, evidence, "XOF"),
    }
    score = None if strategy.score is None else {
        "status": "assessable", "value": float(strategy.score.display_total), "unit": "points",
        "basis": "estimated", "reason_codes": list(strategy.reason_codes), "evidence_refs": [evidence],
    }
    value = {
        "symbol": symbol,
        "entry_action": {"buy": "buy", "not_buy": "no_clear_signal", "unavailable": "insufficient_data"}[strategy.decision],
        "buy_strength": score or {"status": "missing_inputs", "value": None, "unit": "points", "reason_codes": list(strategy.reason_codes or ("analysis_unavailable",))},
        "indicators": points,
        "eligibility_guards": [
            {"code": guard.code, "status": guard.status, "observed": None, "threshold": None, "evidence_refs": [evidence]}
            for guard in strategy.guards
        ],
        "holding_advice": None,
    }
    return CalculationOutput(name="swing", status="available", value=value)


def _micros(value: object) -> int | None:
    return None if value is None else int(Decimal(str(value)) * Decimal(1_000_000))


def _metric(value: Decimal | None, evidence: str, unit: str) -> dict[str, Any]:
    return {"status": "assessable" if value is not None else "missing_inputs", "value": None if value is None else float(value), "unit": unit, "basis": "estimated", "reason_codes": [] if value is not None else ["analysis_unavailable"], "evidence_refs": [evidence]}


def _latest_metric(points: Any, evidence: str, unit: str) -> dict[str, Any]:
    point = points[-1]
    return _metric(None if point.value is None else Decimal(str(point.value)), evidence, unit)


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
