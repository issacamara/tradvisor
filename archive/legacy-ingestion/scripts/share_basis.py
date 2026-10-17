"""Evidence-driven analytical share-basis normalization without source mutation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


class ShareBasisError(ValueError):
    """Raised when source share-basis evidence is malformed."""


@dataclass(frozen=True)
class ShareObservation:
    """Original exchange observation, retained unchanged beside its analytical basis."""

    symbol: str
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    known_at: datetime


@dataclass(frozen=True)
class ShareBasisEvent:
    """A corporate-action observation with point-in-time evidence."""

    symbol: str
    event_type: str
    effective_date: date
    known_at: datetime
    evidence_ref: str
    new_shares_per_old_share: Decimal | None


@dataclass(frozen=True)
class AnalyticalShareObservation:
    """Comparable analytical values or an explicit basis-unavailable result."""

    original: ShareObservation
    target_date: date
    price_factor: Decimal | None
    volume_factor: Decimal | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: Decimal | None
    status: str
    advice_eligible: bool
    unavailable_reason: str | None
    applied_events: tuple[ShareBasisEvent, ...]


def _date(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        raise ShareBasisError(f"{field} must be a date, not a datetime")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ShareBasisError(f"{field} must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ShareBasisError(f"{field} must use YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ShareBasisError(f"{field} must use YYYY-MM-DD")
    return parsed


def _instant(value: Any, field: str = "known_at") -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ShareBasisError(f"{field} must be an ISO timestamp with an offset") from error
    else:
        raise ShareBasisError(f"{field} must be an ISO timestamp with an offset")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ShareBasisError(f"{field} must be an ISO timestamp with an offset")
    return parsed.astimezone(timezone.utc)


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ShareBasisError(f"{field} must be a finite {'positive' if positive else 'nonnegative'} number")
    try:
        text = str(value).strip()
        if "/" in text:
            numerator, denominator = (part.strip() for part in text.split("/", 1))
            parsed = Decimal(numerator) / Decimal(denominator)
        else:
            parsed = Decimal(text)
    except (InvalidOperation, ValueError, ZeroDivisionError) as error:
        raise ShareBasisError(f"{field} must be a finite number") from error
    if not parsed.is_finite() or (parsed <= 0 if positive else parsed < 0):
        qualifier = "positive" if positive else "nonnegative"
        raise ShareBasisError(f"{field} must be finite and {qualifier}")
    return parsed


def normalize_observation(row: Mapping[str, Any]) -> ShareObservation:
    """Parse one raw exchange observation without changing any supplied value."""
    symbol = row.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ShareBasisError("symbol is required")
    prices = {
        name: _decimal(row.get(name), name, positive=True)
        for name in ("open", "high", "low", "close")
    }
    if not prices["low"] <= min(prices["open"], prices["close"]) or not max(
        prices["open"], prices["close"]
    ) <= prices["high"]:
        raise ShareBasisError("OHLC values are inconsistent")
    return ShareObservation(
        symbol=symbol.strip().upper(),
        session_date=_date(row.get("session_date"), "session_date"),
        **prices,
        volume=_decimal(row.get("volume"), "volume"),
        known_at=_instant(row.get("known_at")),
    )


def normalize_event(row: Mapping[str, Any]) -> ShareBasisEvent:
    """Parse split/bonus evidence; unsupported event kinds remain explicit barriers."""
    symbol = row.get("symbol")
    event_type = row.get("event_type")
    evidence_ref = row.get("evidence_ref")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ShareBasisError("symbol is required")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ShareBasisError("event_type is required")
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        raise ShareBasisError("evidence_ref is required")
    kind = event_type.strip().casefold()
    ratio_value = row.get("new_shares_per_old_share")
    ratio = (
        _decimal(ratio_value, "new_shares_per_old_share", positive=True)
        if kind in {"split", "bonus"} and ratio_value is not None
        else None
    )
    if kind in {"split", "bonus"} and ratio is None:
        raise ShareBasisError("split and bonus events require an evidenced share ratio")
    if kind not in {"split", "bonus"}:
        ratio = None
    return ShareBasisEvent(
        symbol=symbol.strip().upper(),
        event_type=kind,
        effective_date=_date(row.get("effective_date"), "effective_date"),
        known_at=_instant(row.get("known_at")),
        evidence_ref=evidence_ref.strip(),
        new_shares_per_old_share=ratio,
    )


def normalize_share_basis(
    observations: Iterable[ShareObservation | Mapping[str, Any]],
    events: Iterable[ShareBasisEvent | Mapping[str, Any]],
    *,
    target_date: date | str,
    known_at: datetime | str,
) -> tuple[AnalyticalShareObservation, ...]:
    """Normalize eligible historical OHLCV to ``target_date``'s share basis.

    Only events effective after an observation and no later than the target date,
    and known by the supplied analysis timestamp, are considered. A known event
    outside the supported split/bonus set blocks that observation's advice.
    Cash dividends are never interpreted as share-basis events.
    """
    target = _date(target_date, "target_date")
    analysis_time = _instant(known_at, "known_at")
    parsed_observations = tuple(
        item if isinstance(item, ShareObservation) else normalize_observation(item)
        for item in observations
    )
    parsed_events = tuple(
        item if isinstance(item, ShareBasisEvent) else normalize_event(item)
        for item in events
    )
    results: list[AnalyticalShareObservation] = []
    for observation in parsed_observations:
        if observation.session_date > target:
            raise ShareBasisError("observation session_date cannot exceed target_date")
        if observation.known_at > analysis_time:
            results.append(AnalyticalShareObservation(
                original=observation, target_date=target,
                price_factor=None, volume_factor=None,
                open=None, high=None, low=None, close=None, volume=None,
                status="not_yet_known", advice_eligible=False,
                unavailable_reason="observation_not_yet_known",
                applied_events=(),
            ))
            continue
        applicable = tuple(
            event for event in parsed_events
            if event.symbol == observation.symbol
            and observation.session_date < event.effective_date <= target
            and event.known_at <= analysis_time
        )
        unsupported = next(
            (
                event
                for event in applicable
                if event.event_type not in {"split", "bonus", "cash_dividend"}
            ),
            None,
        )
        if unsupported is not None:
            results.append(AnalyticalShareObservation(
                original=observation, target_date=target,
                price_factor=None, volume_factor=None,
                open=None, high=None, low=None, close=None, volume=None,
                status="unsupported_basis", advice_eligible=False,
                unavailable_reason="unsupported_corporate_action",
                applied_events=applicable,
            ))
            continue
        volume_factor = Decimal(1)
        for event in applicable:
            if event.event_type == "cash_dividend":
                continue
            assert event.new_shares_per_old_share is not None
            volume_factor *= event.new_shares_per_old_share
        price_factor = Decimal(1) / volume_factor
        results.append(AnalyticalShareObservation(
            original=observation, target_date=target,
            price_factor=price_factor, volume_factor=volume_factor,
            open=observation.open * price_factor,
            high=observation.high * price_factor,
            low=observation.low * price_factor,
            close=observation.close * price_factor,
            volume=observation.volume * volume_factor,
            status="comparable", advice_eligible=True,
            unavailable_reason=None, applied_events=applicable,
        ))
    return tuple(results)
