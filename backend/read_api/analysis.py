"""Typed, bounded readers for the immutable analytical serving copy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
import re
from typing import Any, Callable, Literal, Mapping, TypeVar

from pydantic import BaseModel

from backend.openapi import (
    ChartPoint,
    ChartSeriesName,
    LongTermRankedCompany,
    LongTermRankingsData,
    ScoreMetric,
    StockChartData,
    StockDetailData,
    SwingRecommendation,
    SwingRecommendationsData,
)
from backend.publication.analysis import ActivePublication, PublicationError, ServingOutput, ServingStock
from backend.read_api.cursors import CursorError
from backend.read_api.readers import AnalysisPublisher, read_analysis_page

_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,127}$")
T = TypeVar("T", bound=BaseModel)


class AnalysisNotReady(RuntimeError):
    """The active pointer or its immutable serving copy is not readable."""


class InvalidAnalysisSymbol(ValueError):
    """The path symbol cannot identify a catalog company."""


@dataclass(frozen=True, slots=True)
class PublicationContext:
    active: ActivePublication
    market_session: date
    published_at: datetime
    strategy_id: str


def _context(publisher: AnalysisPublisher) -> PublicationContext:
    try:
        active = publisher.active_publication()
        if active is None or active.published_at is None or active.strategy_id is None:
            raise AnalysisNotReady
        published_at = datetime.fromisoformat(active.published_at.replace("Z", "+00:00"))
        if published_at.tzinfo is None:
            raise AnalysisNotReady
        return PublicationContext(
            active=active,
            market_session=date.fromisoformat(active.effective_session),
            published_at=published_at.astimezone(timezone.utc),
            strategy_id=active.strategy_id,
        )
    except (AnalysisNotReady, PublicationError, TypeError, ValueError) as error:
        raise AnalysisNotReady from error


def _output(stock: ServingStock, name: str) -> ServingOutput:
    for output in stock.outputs:
        if output.name == name:
            if output.status != "available" or output.value is None:
                raise AnalysisNotReady
            return output
    raise AnalysisNotReady


def _payload(stock: ServingStock, name: str, model: type[T]) -> T:
    try:
        # Firestore returns the stored JSON envelope as ordinary mappings and
        # lists; deserialize through JSON so strict contract models can restore
        # tuple, date, and datetime fields at the API boundary.
        return model.model_validate_json(json.dumps(_output(stock, name).value))
    except (AnalysisNotReady, TypeError, ValueError) as error:
        raise AnalysisNotReady from error


def _validate_symbol(symbol: str) -> str:
    if not _SYMBOL.fullmatch(symbol):
        raise InvalidAnalysisSymbol
    return symbol


def _page(
    publisher: AnalysisPublisher,
    *,
    context: PublicationContext,
    limit: int,
    cursor: str | None,
    cursor_secret: bytes,
    now: Callable[[], datetime],
    symbol: str | None = None,
    sector: str | None = None,
) -> tuple[tuple[ServingStock, ...], str | None]:
    items, next_cursor = read_analysis_page(
        publisher,
        batch_id=context.active.batch_id,
        limit=limit,
        cursor=cursor,
        cursor_secret=cursor_secret,
        now=now(),
    )
    selected = tuple(
        stock
        for stock in items.items
        if (symbol is None or stock.symbol == symbol)
        and (sector is None or _stock_sector(stock) == sector)
    )
    return selected, next_cursor


def _stock_sector(stock: ServingStock) -> str | None:
    try:
        value = _output(stock, "company").value
        return value.get("sector") if isinstance(value, Mapping) else None
    except AnalysisNotReady:
        return None


def read_swing(
    publisher: AnalysisPublisher, *, limit: int, cursor: str | None, symbol: str | None,
    sector: str | None, cursor_secret: bytes, now: Callable[[], datetime],
) -> SwingRecommendationsData:
    context = _context(publisher)
    if symbol is not None:
        symbol = _validate_symbol(symbol)
    stocks, next_cursor = _page(publisher, context=context, limit=limit, cursor=cursor, cursor_secret=cursor_secret, now=now, symbol=symbol, sector=sector)
    items = []
    for stock in stocks:
        try:
            items.append(_payload(stock, "swing", SwingRecommendation))
        except AnalysisNotReady:
            # Market-data publication is useful before recommendation rules are
            # ready. Keep the symbol selectable and make the missing analysis
            # explicit instead of turning the whole endpoint into a 422.
            missing = {
                "status": "missing_inputs", "value": None,
                "unit": "points", "reason_codes": ("analysis_not_published",),
            }
            items.append(SwingRecommendation(
                symbol=stock.symbol,
                entry_action="insufficient_data",
                buy_strength=ScoreMetric(**missing),
                indicators={name: NumericMetric(**{**missing, "unit": "value"}) for name in ("ema20", "ema50", "rsi14", "atr14", "traded_value20")},
                eligibility_guards=(), holding_advice=None,
            ))
    return SwingRecommendationsData(
        batch_id=context.active.batch_id, market_session=context.market_session,
        published_at=context.published_at, input_snapshot_id=context.active.input_snapshot_id,
        rule_version=context.active.rule_version, strategy_id=context.strategy_id,
        generation=None, state_version=None, items=tuple(items), next_cursor=next_cursor,
    )


def read_long_term(
    publisher: AnalysisPublisher, *, objective: Literal["growth", "dividend", "balanced"], limit: int, cursor: str | None,
    symbol: str | None, sector: str | None, cursor_secret: bytes, now: Callable[[], datetime],
) -> LongTermRankingsData:
    context = _context(publisher)
    if symbol is not None:
        symbol = _validate_symbol(symbol)
    stocks, next_cursor = _page(publisher, context=context, limit=limit, cursor=cursor, cursor_secret=cursor_secret, now=now, symbol=symbol, sector=sector)
    items = () if objective == "balanced" else tuple(
        _payload(stock, "long_term", LongTermRankedCompany) for stock in stocks
    )
    overall_score = (
        ScoreMetric(
            status="deferred_scope",
            value=None,
            unit="score",
            reason_codes=("balanced_scoring_deferred_v1",),
        )
        if objective == "balanced"
        else None
    )
    return LongTermRankingsData(
        objective=objective, batch_id=context.active.batch_id, market_session=context.market_session,
        published_at=context.published_at, input_snapshot_id=context.active.input_snapshot_id,
        rule_version=context.active.rule_version, strategy_id=context.strategy_id,
        items=items, next_cursor=next_cursor, overall_score=overall_score,
    )


def read_stock(publisher: AnalysisPublisher, *, symbol: str, cursor_secret: bytes, now: Callable[[], datetime]) -> StockDetailData:
    symbol = _validate_symbol(symbol)
    context = _context(publisher)
    stocks, _ = _page(publisher, context=context, limit=100, cursor=None, cursor_secret=cursor_secret, now=now, symbol=symbol)
    if not stocks:
        raise KeyError(symbol)
    value = _output(stocks[0], "stock").value
    if not isinstance(value, Mapping):
        raise AnalysisNotReady
    payload = dict(value)
    payload.update(
        batch_id=context.active.batch_id, market_session=context.market_session,
        published_at=context.published_at, input_snapshot_id=context.active.input_snapshot_id,
        rule_version=context.active.rule_version, strategy_id=context.strategy_id,
    )
    try:
        return StockDetailData.model_validate(payload)
    except (TypeError, ValueError) as error:
        raise AnalysisNotReady from error


def read_chart(
    publisher: AnalysisPublisher, *, symbol: str, from_date: date, to_date: date,
    series: tuple[ChartSeriesName, ...] | None, cursor_secret: bytes, now: Callable[[], datetime],
) -> StockChartData:
    symbol = _validate_symbol(symbol)
    context = _context(publisher)
    stocks, _ = _page(publisher, context=context, limit=100, cursor=None, cursor_secret=cursor_secret, now=now, symbol=symbol)
    if not stocks:
        raise KeyError(symbol)
    raw = _output(stocks[0], "chart").value
    if not isinstance(raw, Mapping):
        raise AnalysisNotReady
    payload = dict(raw)
    payload.update({"symbol": symbol, "from": from_date, "to": to_date, "batch_id": context.active.batch_id})
    try:
        chart = StockChartData.model_validate(payload)
    except (TypeError, ValueError) as error:
        raise AnalysisNotReady from error
    points = tuple(point for point in chart.points if from_date <= point.session_date <= to_date)
    if series is not None:
        selected_points = []
        for point in points:
            selected_points.append(ChartPoint.model_validate({
                **point.model_dump(mode="python"),
                "indicators": {
                    name: point.indicators[name]
                    for name in series
                    if name != "ohlcv" and name in point.indicators
                },
            }))
        points = tuple(selected_points)
    return StockChartData.model_validate({
        "symbol": symbol,
        "from": from_date,
        "to": to_date,
        "batch_id": chart.batch_id,
        "points": points,
    })


__all__ = [
    "AnalysisNotReady", "CursorError", "InvalidAnalysisSymbol", "read_chart",
    "read_long_term", "read_stock", "read_swing",
]
