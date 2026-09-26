"""Normalize evidenced ordinary-share capitalization records without I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping


class CapitalizationError(ValueError):
    """Raised when a capitalization record cannot represent ordinary capital."""


_BASIS_ALIASES = {
    "issued": "issued",
    "ordinary issued": "issued",
    "ordinary shares issued": "issued",
    "outstanding": "outstanding",
    "ordinary outstanding": "outstanding",
    "ordinary shares outstanding": "outstanding",
}
_REJECTED_BASIS_MARKERS = ("free float", "free_float", "weighted", "eps")


@dataclass(frozen=True)
class OrdinaryCapitalization:
    """An evidenced capitalization record and its valuation usability."""

    symbol: str
    ordinary_shares: Decimal
    market_cap: Decimal | None
    market_cap_source_value: Decimal | None
    market_cap_currency: str | None
    market_cap_source_unit: str | None
    market_cap_scale_to_xof: Decimal | None
    ownership_basis: str | None
    matching_basis: str | None
    source_ownership_basis: str | None
    source_matching_basis: str | None
    treasury_shares: Decimal | None
    share_class: str
    source_url: str
    source_date: date
    known_at: datetime | None
    valuation_eligible: bool
    unavailable_reasons: tuple[str, ...]


def _text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise CapitalizationError(f"{field} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        if required:
            raise CapitalizationError(f"{field} is required")
        return None
    return value.strip()


def _decimal(value: Any, field: str, *, required: bool = False) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise CapitalizationError(f"{field} is required")
        return None
    if isinstance(value, bool):
        raise CapitalizationError(f"{field} must be a finite nonnegative number")
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError) as error:
        raise CapitalizationError(f"{field} must be a finite nonnegative number") from error
    if not parsed.is_finite() or parsed < 0:
        raise CapitalizationError(f"{field} must be a finite nonnegative number")
    return parsed


def _date(value: Any, field: str) -> date:
    text = _text(value, field, required=True)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise CapitalizationError(f"{field} must use YYYY-MM-DD") from error
    if parsed.isoformat() != text:
        raise CapitalizationError(f"{field} must use YYYY-MM-DD")
    return parsed


def _instant(value: Any) -> datetime | None:
    text = _text(value, "known_at")
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise CapitalizationError("known_at must be an ISO timestamp with an offset") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CapitalizationError("known_at must be an ISO timestamp with an offset")
    return parsed.astimezone(timezone.utc)


def _basis(value: Any, field: str) -> tuple[str | None, str | None]:
    text = _text(value, field)
    if text is None:
        return None, None
    normalized = " ".join(text.casefold().replace("_", " ").replace("-", " ").split())
    if any(marker in normalized for marker in _REJECTED_BASIS_MARKERS):
        raise CapitalizationError(f"{field} is not an ordinary-share ownership basis")
    return _BASIS_ALIASES.get(normalized), text


def _validate_single_class(row: Mapping[str, Any]) -> str:
    supplied_class = _text(row.get("share_class", row.get("class")), "share_class")
    share_class = supplied_class.casefold() if supplied_class else None
    class_count = row.get("class_count")
    has_cardinality_evidence = class_count is not None
    if class_count is not None and (isinstance(class_count, bool) or class_count != 1):
        raise CapitalizationError("multiclass capitalization is not supported")
    classes = row.get("share_classes")
    if classes is not None:
        has_cardinality_evidence = True
        if not isinstance(classes, (list, tuple, set)) or len(classes) != 1:
            raise CapitalizationError("multiclass capitalization is not supported")
        only_class = _text(next(iter(classes)), "share_classes", required=True)
        if only_class.casefold() != "ordinary":
            raise CapitalizationError("only ordinary share class is supported")
    if share_class is None or not has_cardinality_evidence:
        return "unknown"
    if share_class != "ordinary":
        raise CapitalizationError("only ordinary share class is supported")
    return "ordinary"


def _market_cap_amount(row: Mapping[str, Any]) -> tuple[Decimal | None, Decimal | None, str | None, str | None, Decimal | None]:
    raw = row.get("market_cap", row.get("market_capitalization"))
    if isinstance(raw, Mapping):
        source_value = _decimal(raw.get("value"), "market_cap.value")
        currency = _text(raw.get("currency"), "market_cap.currency")
        unit = _text(raw.get("unit"), "market_cap.unit")
        scale = _decimal(raw.get("scale_to_xof"), "market_cap.scale_to_xof")
        if source_value is None or currency is None or unit is None or scale is None:
            return None, source_value, currency, unit, scale
        return source_value * scale, source_value, currency, unit, scale
    source_value = _decimal(raw, "market_cap")
    currency = _text(row.get("market_cap_currency"), "market_cap_currency")
    unit = _text(row.get("market_cap_unit"), "market_cap_unit")
    scale = _decimal(row.get("market_cap_scale_to_xof"), "market_cap_scale_to_xof")
    normalized = source_value * scale if source_value is not None and scale is not None else source_value
    return normalized, source_value, currency, unit, scale


def normalize_ordinary_capitalization(row: Mapping[str, Any]) -> OrdinaryCapitalization:
    """Normalize one recorded capitalization observation without provider calls."""
    symbol = _text(row.get("symbol", row.get("ticker")), "symbol", required=True).upper()
    source_url = _text(row.get("source_url", row.get("source_ref")), "source_url", required=True)
    source_date = _date(row.get("source_date"), "source_date")
    share_class = _validate_single_class(row)
    ordinary_shares = _decimal(
        row.get("ordinary_shares", row.get("issued_shares", row.get("shares"))),
        "ordinary_shares",
        required=True,
    )
    market_cap, market_cap_source_value, market_cap_currency, market_cap_source_unit, market_cap_scale = _market_cap_amount(row)
    treasury_shares = _decimal(row.get("treasury_shares"), "treasury_shares")
    ownership_basis, source_ownership_basis = _basis(
        row.get("ownership_basis", row.get("share_basis", row.get("basis"))),
        "ownership_basis",
    )
    matching_basis, source_matching_basis = _basis(
        row.get("matching_basis", row.get("earnings_share_basis", row.get("valuation_basis"))),
        "matching_basis",
    )

    reasons: list[str] = []
    if share_class == "unknown":
        reasons.append("share_class_unknown")
    if ordinary_shares <= 0:
        reasons.append("ordinary_shares_non_positive")
    if ownership_basis is None:
        reasons.append("ownership_basis_unknown")
    if matching_basis is None:
        reasons.append("matching_basis_unknown")
    elif ownership_basis != matching_basis:
        reasons.append("share_basis_mismatch")
    if market_cap is None:
        reasons.append("market_cap_unknown")
    elif market_cap <= 0:
        reasons.append("market_cap_non_positive")
    if market_cap_currency != "XOF":
        reasons.append("market_cap_currency_unknown")
    if market_cap_scale is None:
        reasons.append("market_cap_scale_unknown")
    valuation_eligible = not reasons and market_cap is not None
    return OrdinaryCapitalization(
        symbol=symbol,
        ordinary_shares=ordinary_shares,
        market_cap=market_cap,
        market_cap_source_value=market_cap_source_value,
        market_cap_currency=market_cap_currency,
        market_cap_source_unit=market_cap_source_unit,
        market_cap_scale_to_xof=market_cap_scale,
        ownership_basis=ownership_basis,
        matching_basis=matching_basis,
        source_ownership_basis=source_ownership_basis,
        source_matching_basis=source_matching_basis,
        treasury_shares=treasury_shares,
        share_class=share_class,
        source_url=source_url,
        source_date=source_date,
        known_at=_instant(row.get("known_at")),
        valuation_eligible=valuation_eligible,
        unavailable_reasons=tuple(reasons),
    )


def normalize_ordinary_capitalizations(rows: Iterable[Mapping[str, Any]]) -> list[OrdinaryCapitalization]:
    """Normalize a finite collection while retaining each source observation."""
    return [normalize_ordinary_capitalization(row) for row in rows]
