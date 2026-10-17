"""Deterministic normalization for already-recorded annual financial reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class NormalizedAmount:
    """An XOF amount with its reported unit and explicit conversion retained."""

    value: Decimal
    source_value: Decimal
    source_unit: str
    scale_to_xof: Decimal


@dataclass(frozen=True)
class AnnualFinancialRecord:
    company_id: str
    fiscal_year: int | None
    period_start: date | None
    period_end: date | None
    full_year: bool
    publication_status: str
    published_at: datetime | None
    collected_at: datetime | None
    source_ref: str
    currency: str | None
    report_scope: str
    accounting_basis: str | None
    financial_category: str
    revenue: NormalizedAmount | None
    ordinary_owner_earnings: NormalizedAmount | None
    earnings_basis: str | None
    equity: NormalizedAmount | None
    equity_basis: str | None
    opening_equity: NormalizedAmount | None
    opening_equity_date: date | None
    interest_bearing_debt: NormalizedAmount | None
    unrestricted_cash: NormalizedAmount | None
    current_assets: NormalizedAmount | None
    current_liabilities: NormalizedAmount | None
    unavailable_reasons: tuple[str, ...]


@dataclass(frozen=True)
class HistoryAssessment:
    comparable: bool
    years: tuple[int, ...]
    equity_dates: tuple[date, ...]
    reason: str | None


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("dates must be ISO strings")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("dates must be ISO strings") from exc
    if parsed.isoformat() != value:
        raise ValueError("dates must use YYYY-MM-DD")
    return parsed


def _instant(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamps must be ISO strings with an explicit offset")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp is invalid") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamps must have an explicit offset")
    return result.astimezone(timezone.utc)


def _amount(report: Mapping[str, Any], field: str, reasons: list[str]) -> NormalizedAmount | None:
    if report.get("currency") != "XOF":
        reasons.append(f"unsupported_{field}_currency")
        return None
    raw = report.get(field)
    if raw is None:
        reasons.append(f"missing_{field}")
        return None
    if not isinstance(raw, Mapping) or raw.get("evidenced") is not True:
        reasons.append(f"unsupported_{field}_evidence")
        return None
    value = raw.get("value")
    scale = raw.get("scale_to_xof")
    unit = raw.get("unit")
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        reasons.append(f"unsupported_{field}_value")
        return None
    if not isinstance(scale, (str, int)) or isinstance(scale, bool) or not isinstance(unit, str) or not unit.strip():
        reasons.append(f"unsupported_{field}_unit")
        return None
    try:
        source_value = Decimal(str(value))
        multiplier = Decimal(str(scale))
    except InvalidOperation:
        reasons.append(f"unsupported_{field}_number")
        return None
    if not source_value.is_finite() or not multiplier.is_finite() or multiplier <= 0:
        reasons.append(f"unsupported_{field}_number")
        return None
    if raw.get("currency") != "XOF":
        reasons.append(f"unsupported_{field}_currency")
        return None
    unit_key = " ".join(unit.casefold().split())
    unit_scales = {
        "xof": Decimal("1"),
        "fcfa": Decimal("1"),
        "thousand xof": Decimal("1000"),
        "thousand fcfa": Decimal("1000"),
        "million xof": Decimal("1000000"),
        "million fcfa": Decimal("1000000"),
        "billion xof": Decimal("1000000000"),
        "billion fcfa": Decimal("1000000000"),
    }
    if unit_scales.get(unit_key) != multiplier:
        reasons.append(f"unsupported_{field}_unit_scale")
        return None
    return NormalizedAmount(source_value * multiplier, source_value, unit.strip(), multiplier)


def normalize_annual_report(report: Mapping[str, Any]) -> AnnualFinancialRecord:
    """Normalize one recorded extraction; this function never performs I/O."""
    reasons: list[str] = []
    company_id = report.get("company_id")
    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError("company_id is required")
    source_ref = report.get("source_ref")
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise ValueError("source_ref is required")

    period = report.get("period") or {}
    if not isinstance(period, Mapping):
        raise ValueError("period must be an object")
    start, end = _date(period.get("start")), _date(period.get("end"))
    fiscal_year = period.get("fiscal_year")
    if fiscal_year is not None and (not isinstance(fiscal_year, int) or isinstance(fiscal_year, bool)):
        raise ValueError("fiscal_year must be an integer")
    full_year = period.get("full_year") is True
    if start is None or end is None or end < start or not full_year:
        reasons.append("unsupported_or_incomplete_annual_period")

    publication = report.get("publication") or {}
    if not isinstance(publication, Mapping):
        raise ValueError("publication must be an object")
    published_at = _instant(publication.get("published_at"))
    collected_at = _instant(report.get("collected_at"))
    publication_status = "published" if published_at is not None and publication.get("evidenced") is True else "unknown"
    if publication_status == "unknown":
        reasons.append("publication_time_unknown")
    if collected_at is None:
        reasons.append("collection_time_unknown")

    scope = report.get("report_scope")
    scope = scope if isinstance(scope, str) and scope in {"standalone", "consolidated"} else "unknown"
    if scope == "unknown":
        reasons.append("report_scope_unknown")
    accounting_basis = report.get("accounting_basis")
    if not isinstance(accounting_basis, str) or not accounting_basis.strip():
        accounting_basis = None
        reasons.append("accounting_basis_unknown")
    currency = report.get("currency")
    if currency != "XOF":
        currency = None
        reasons.append("unsupported_report_currency")

    category = report.get("financial_category")
    category = (
        category
        if isinstance(category, str) and category in {"bank", "insurer", "non_financial"}
        else "unsupported"
    )
    revenue = None
    if category == "non_financial":
        revenue = _amount(report, "revenue", reasons)
    elif report.get("revenue") is not None:
        reasons.append("revenue_not_applicable_for_financial_entity")

    earnings = _amount(report, "ordinary_owner_earnings", reasons)
    equity = _amount(report, "equity", reasons)
    earnings_scope = report.get("earnings_scope")
    equity_scope = report.get("equity_scope")
    if earnings is not None and (
        report.get("earnings_basis") != "ordinary_owner"
        or earnings_scope not in {"standalone", "consolidated"}
        or earnings_scope != scope
        or scope == "unknown"
    ):
        earnings = None
        reasons.append("earnings_owner_or_scope_unverified")
    if equity is not None and (
        report.get("equity_basis") != "ordinary_owner"
        or equity_scope not in {"standalone", "consolidated"}
        or equity_scope != scope
        or scope == "unknown"
    ):
        equity = None
        reasons.append("equity_owner_or_scope_unverified")
    if earnings is not None and equity is not None:
        if (
            report.get("earnings_basis") != report.get("equity_basis")
            or earnings_scope != equity_scope
        ):
            earnings = equity = None
            reasons.append("owner_or_consolidation_basis_mismatch")

    opening_equity = _amount(report, "opening_equity", reasons)
    opening_date = _date((report.get("opening_equity") or {}).get("date")) if isinstance(report.get("opening_equity"), Mapping) else None
    if opening_equity is not None and (
        report.get("opening_equity", {}).get("basis") != "ordinary_owner"
        or report.get("opening_equity", {}).get("scope") not in {"standalone", "consolidated"}
        or report.get("opening_equity", {}).get("scope") != scope
        or scope == "unknown"
        or opening_date is None
        or start is None
        or opening_date >= start
    ):
        opening_equity = None
        reasons.append("opening_equity_basis_or_date_unverified")

    balance: dict[str, NormalizedAmount | None] = {
        key: None for key in ("interest_bearing_debt", "unrestricted_cash", "current_assets", "current_liabilities")
    }
    if category == "non_financial" and scope != "unknown":
        balance["interest_bearing_debt"] = _amount(report, "interest_bearing_debt", reasons)
        balance["unrestricted_cash"] = _amount(report, "unrestricted_cash", reasons)
        balance["current_assets"] = _amount(report, "current_assets", reasons)
        balance["current_liabilities"] = _amount(report, "current_liabilities", reasons)
        for field, amount in tuple(balance.items()):
            evidence = report.get(field)
            if amount is None or not isinstance(evidence, Mapping):
                continue
            if evidence.get("scope", scope) != scope:
                balance[field] = None
                reasons.append(f"{field}_scope_mismatch")
        cash_evidence = report.get("unrestricted_cash")
        if balance["unrestricted_cash"] is not None and cash_evidence.get("restricted") is not False:
            balance["unrestricted_cash"] = None
            reasons.append("cash_restriction_unknown_or_restricted")
    elif category != "non_financial":
        reasons.append("non_financial_inputs_not_applicable")

    return AnnualFinancialRecord(
        company_id=company_id.strip(),
        fiscal_year=fiscal_year,
        period_start=start,
        period_end=end,
        full_year=full_year,
        publication_status=publication_status,
        published_at=published_at,
        collected_at=collected_at,
        source_ref=source_ref,
        currency=currency,
        report_scope=scope,
        accounting_basis=accounting_basis,
        financial_category=category,
        revenue=revenue,
        ordinary_owner_earnings=earnings,
        earnings_basis=report.get("earnings_basis") if earnings is not None else None,
        equity=equity,
        equity_basis=report.get("equity_basis") if equity is not None else None,
        opening_equity=opening_equity,
        opening_equity_date=opening_date if opening_equity is not None else None,
        interest_bearing_debt=balance["interest_bearing_debt"],
        unrestricted_cash=balance["unrestricted_cash"],
        current_assets=balance["current_assets"],
        current_liabilities=balance["current_liabilities"],
        unavailable_reasons=tuple(dict.fromkeys(reasons)),
    )


def normalize_extracted_annual_report(
    extraction: Mapping[str, Any],
    *,
    company_id: str,
    source_ref: str,
    collected_at: str,
) -> AnnualFinancialRecord:
    """Normalize recorded provider output with acquisition metadata from ingestion."""
    annual_report = extraction.get("annual_report")
    if isinstance(annual_report, Mapping):
        report = dict(extraction)
        report.update(annual_report)
    else:
        # Legacy rows may carry naive timestamps and do not contain the
        # evidence needed for the canonical annual contract.
        report = {key: value for key, value in extraction.items() if key != "collected_at"}
    report.setdefault("company_id", company_id)
    report.setdefault("source_ref", source_ref)
    report.setdefault("collected_at", collected_at)
    return normalize_annual_report(report)


def assess_five_year_history(records: Sequence[AnnualFinancialRecord]) -> HistoryAssessment:
    """Check five consecutive comparable annual reports and six equity dates."""
    ordered = sorted(records, key=lambda item: item.fiscal_year or -1)
    years = tuple(item.fiscal_year for item in ordered if item.fiscal_year is not None)
    dates = tuple(
        [ordered[0].opening_equity_date] if ordered and ordered[0].opening_equity_date else []
    ) + tuple(item.period_end for item in ordered if item.period_end is not None)
    if len(ordered) != 5 or len(years) != 5 or any(b != a + 1 for a, b in zip(years, years[1:])):
        return HistoryAssessment(False, years, dates, "five_consecutive_completed_years_required")
    first = ordered[0]
    if any(
        item.company_id != first.company_id
        or item.period_start is None
        or item.period_end is None
        or item.period_end < item.period_start
        or (index > 0 and item.period_start != ordered[index - 1].period_end + timedelta(days=1))
        for index, item in enumerate(ordered)
    ):
        return HistoryAssessment(False, years, dates, "annual_periods_not_contiguous")
    if any(
        not item.full_year
        or item.period_start is None
        or item.period_end is None
        or item.publication_status != "published"
        or item.currency != first.currency
        or item.report_scope != first.report_scope
        or item.accounting_basis != first.accounting_basis
        or item.accounting_basis is None
        or item.financial_category != first.financial_category
        or item.ordinary_owner_earnings is None
        or item.equity is None
        for item in ordered
    ):
        return HistoryAssessment(False, years, dates, "annual_reports_not_comparable_or_complete")
    if len(set(dates)) != 6 or ordered[0].opening_equity is None or any(item.equity is None for item in ordered):
        return HistoryAssessment(False, years, dates, "six_evidenced_equity_dates_required")
    if ordered[0].opening_equity_date + timedelta(days=1) != ordered[0].period_start:
        return HistoryAssessment(False, years, dates, "opening_equity_date_must_precede_first_year_start")
    return HistoryAssessment(True, years, dates, None)


def available_as_of(record: AnnualFinancialRecord, instant: datetime) -> bool:
    """Return true only after both publication and platform collection."""
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("as-of instant must have an explicit offset")
    cutoff = instant.astimezone(timezone.utc)
    return (
        record.publication_status == "published"
        and record.published_at is not None
        and record.collected_at is not None
        and record.published_at <= cutoff
        and record.collected_at <= cutoff
    )
