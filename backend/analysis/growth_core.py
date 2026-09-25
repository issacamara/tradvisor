"""Approved Growth activity, earnings, and profitability dimensions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Literal

from backend.contracts.analysis import NormalizedFinancial

ACTIVITY_POINTS = Decimal("12")
EARNINGS_POINTS = Decimal("18")
PROFITABILITY_POINTS = Decimal("25")
ROE_FULL_CREDIT = Decimal("0.15")
SMALL_BASE_FRACTION = Decimal("0.10")
HISTORY_YEARS = 5
CAGR_YEARS = 3

ActivityKind = Literal["revenue", "net_banking_income", "gross_written_premiums"]
DimensionStatus = Literal["assessable", "unavailable"]


class GrowthCalculationError(ValueError):
    """Raised when annual inputs cannot form one comparable snapshot."""


@dataclass(frozen=True)
class ActivityObservation:
    fiscal_period_end: date
    kind: ActivityKind
    value: Decimal | None
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class GrowthInput:
    """Five normalized annual financial rows and matching sector activity facts."""

    company_id: str
    financials: tuple[NormalizedFinancial, ...]
    activity: tuple[ActivityObservation, ...]


@dataclass(frozen=True)
class TermResult:
    status: DimensionStatus
    points: Decimal | None
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]
    details: tuple[tuple[str, Decimal | str | bool | None], ...] = ()


@dataclass(frozen=True)
class GrowthCoreResult:
    activity_growth: TermResult
    earnings_growth: TermResult
    growth: TermResult
    profitability: TermResult


def _money(value: object | None) -> Decimal | None:
    if value is None:
        return None
    amount = getattr(value, "amount", None)
    if amount is None:
        raise GrowthCalculationError("normalized money input has no amount")
    try:
        result = Decimal(str(amount))
    except InvalidOperation as error:
        raise GrowthCalculationError("normalized money input is not decimal") from error
    if not result.is_finite():
        raise GrowthCalculationError("normalized money input must be finite")
    return result


def _refs(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(ref for group in groups for ref in group))


def _unavailable(*, reason: str, evidence: tuple[str, ...] = ()) -> TermResult:
    return TermResult("unavailable", None, evidence, (reason,))


def _financial_unavailability(rows: tuple[NormalizedFinancial, ...]) -> str | None:
    if any(row.publication_status != "published" for row in rows):
        return "annual_report_unavailable"
    if any(row.report_scope == "unknown" for row in rows):
        return "reporting_scope_unknown"
    if len({(row.currency, row.report_scope) for row in rows}) != 1:
        return "incomparable_financial_basis"
    return None


def _cagr_and_factor(latest: Decimal, base: Decimal, ceiling: Decimal) -> tuple[Decimal, Decimal]:
    ratio = latest / base
    cagr = ratio ** (Decimal(1) / Decimal(CAGR_YEARS)) - Decimal(1)
    threshold_endpoint = (Decimal(1) + ceiling) ** CAGR_YEARS
    factor = Decimal(1) if ratio >= threshold_endpoint else max(Decimal(0), cagr / ceiling)
    return cagr, factor


def _require_history(inputs: GrowthInput) -> tuple[tuple[NormalizedFinancial, ...], tuple[ActivityObservation, ...]]:
    rows = tuple(sorted(inputs.financials, key=lambda row: row.fiscal_period_end))
    activity = tuple(sorted(inputs.activity, key=lambda row: row.fiscal_period_end))
    if len(rows) != HISTORY_YEARS or len(activity) != HISTORY_YEARS:
        raise GrowthCalculationError("exactly five annual financial and activity observations are required")
    if any(row.company_id != inputs.company_id for row in rows):
        raise GrowthCalculationError("annual financial rows must belong to one company")
    ends = tuple(row.fiscal_period_end for row in rows)
    if tuple(item.fiscal_period_end for item in activity) != ends:
        raise GrowthCalculationError("activity and financial fiscal periods must align exactly")
    if len(set(ends)) != HISTORY_YEARS:
        raise GrowthCalculationError("annual fiscal period ends must be unique")
    for prior, current in zip(rows, rows[1:]):
        if prior.fiscal_period_end >= current.fiscal_period_end:
            raise GrowthCalculationError("annual financial rows must be ordered by fiscal period")
        if prior.fiscal_period_start >= current.fiscal_period_start:
            raise GrowthCalculationError("annual financial periods must be ordered")
        if current.fiscal_period_start != prior.fiscal_period_end + timedelta(days=1):
            raise GrowthCalculationError("annual financial periods must be consecutive without interpolation")
    if any(not 350 <= (row.fiscal_period_end - row.fiscal_period_start).days + 1 <= 380 for row in rows):
        raise GrowthCalculationError("each normalized record must represent a full fiscal year")
    return rows, activity


def _activity_term(observations: tuple[ActivityObservation, ...]) -> TermResult:
    refs = _refs(*(item.evidence_refs for item in observations))
    if len({item.kind for item in observations}) != 1:
        return _unavailable(reason="incomparable_activity_measure", evidence=refs)
    if any(item.value is None for item in observations):
        missing_reasons = _refs(*(item.reason_codes for item in observations if item.value is None))
        return _unavailable(reason=missing_reasons[0] if missing_reasons else "activity_history_incomplete", evidence=refs)
    values = tuple(item.value for item in observations)
    assert all(value is not None for value in values)
    numeric = tuple(value for value in values if value is not None)
    kind = observations[0].kind
    if kind in {"revenue", "gross_written_premiums"} and any(value < 0 for value in numeric):
        return _unavailable(reason="unsupported_negative_activity_semantics", evidence=refs)
    base, latest = numeric[-1 - CAGR_YEARS], numeric[-1]
    reason_list: list[str] = []
    cagr: Decimal | None = None
    if latest <= 0:
        reason_list.append("nonpositive_latest_activity")
    elif base <= 0:
        reason_list.append("nonpositive_activity_base_recovery")
    else:
        cagr, factor = _cagr_and_factor(latest, base, Decimal("0.15"))
    if cagr is None:
        factor = Decimal(0)
    points = ACTIVITY_POINTS * factor
    return TermResult(
        "assessable", points, refs, tuple(reason_list),
        (("cagr", cagr), ("starting_value", base), ("latest_value", latest),
         ("latest_annual_change", numeric[-1] - numeric[-2])),
    )


def _earnings_term(rows: tuple[NormalizedFinancial, ...]) -> TermResult:
    refs = _refs(*(row.revision.provenance.source_id and (row.revision.provenance.source_id,) or () for row in rows))
    unavailable = _financial_unavailability(rows)
    if unavailable is not None:
        return _unavailable(reason=unavailable, evidence=refs)
    earnings = tuple(_money(row.ordinary_owner_earnings) for row in rows)
    if any(value is None for value in earnings):
        missing_reasons = _refs(*(row.reason_codes for row, value in zip(rows, earnings) if value is None))
        return _unavailable(reason=missing_reasons[0] if missing_reasons else "earnings_history_incomplete", evidence=refs)
    values = tuple(value for value in earnings if value is not None)
    base, latest = values[-1 - CAGR_YEARS], values[-1]
    reason_list: list[str] = []
    cagr: Decimal | None = None
    if latest <= 0:
        reason_list.append("latest_earnings_nonpositive")
    elif base <= 0:
        reason_list.append("nonpositive_earnings_base_recovery")
    else:
        cagr, factor = _cagr_and_factor(latest, base, Decimal("0.20"))
    if cagr is None:
        factor = Decimal(0)
    absolute_median = median(abs(value) for value in values)
    small_base = base > 0 and absolute_median > 0 and base < SMALL_BASE_FRACTION * absolute_median
    if small_base:
        reason_list.append("small_earnings_base")
    if any(value <= 0 for value in values[1:]) and base > 0 and latest > 0:
        reason_list.append("intervening_earnings_loss_or_break_even")
    return TermResult(
        "assessable", EARNINGS_POINTS * factor, refs, tuple(reason_list),
        (("cagr", cagr), ("starting_earnings", base), ("latest_earnings", latest),
         ("five_year_absolute_earnings_median", absolute_median), ("small_base_warning", small_base)),
    )


def _profitability_term(rows: tuple[NormalizedFinancial, ...]) -> TermResult:
    refs = _refs(*(row.revision.provenance.source_id and (row.revision.provenance.source_id,) or () for row in rows))
    unavailable = _financial_unavailability(rows)
    if unavailable is not None:
        return _unavailable(reason=unavailable, evidence=refs)
    earnings = tuple(_money(row.ordinary_owner_earnings) for row in rows)
    opening_equities = tuple(_money(row.opening_equity) for row in rows)
    closing_equities = tuple(_money(row.equity) for row in rows)
    if any(value is None for value in earnings + opening_equities + closing_equities):
        reasons = _refs(*(row.reason_codes for row, values in zip(rows, zip(earnings, opening_equities, closing_equities)) if any(value is None for value in values)))
        return _unavailable(reason=reasons[0] if reasons else "profitability_history_incomplete", evidence=refs)

    if any(
        opening_equities[index] != closing_equities[index - 1]
        for index in range(1, HISTORY_YEARS)
    ):
        return _unavailable(reason="six_equity_dates_inconsistent", evidence=refs)

    annual_factors: list[Decimal] = []
    annual_reasons: list[str] = []
    for year, income, opening, closing in zip(rows, earnings, opening_equities, closing_equities):
        assert income is not None and opening is not None and closing is not None
        if opening <= 0 or closing <= 0:
            annual_factors.append(Decimal(0))
            annual_reasons.append("nonpositive_equity_zero_roe_factor")
            continue
        average_equity = (opening + closing) / Decimal(2)
        roe = income / average_equity
        annual_factors.append(min(Decimal(1), max(Decimal(0), roe / ROE_FULL_CREDIT)))
    latest_points = Decimal(10) * annual_factors[-1]
    typical_points = Decimal(5) * Decimal(str(median(annual_factors)))
    profitable_years = sum(value is not None and value > 0 for value in earnings)
    consistency_points = Decimal(10) * Decimal(profitable_years) / Decimal(HISTORY_YEARS)
    return TermResult(
        "assessable", latest_points + typical_points + consistency_points, refs,
        tuple(dict.fromkeys(annual_reasons)),
        (("latest_roe_factor", annual_factors[-1]),
         ("median_five_year_roe_factor", Decimal(str(median(annual_factors)))),
         ("profitable_years", Decimal(profitable_years)),
         ("latest_roe_points", latest_points), ("typical_roe_points", typical_points),
         ("consistency_points", consistency_points),
         *((f"roe_factor_year_{index + 1}", factor) for index, factor in enumerate(annual_factors))),
    )


def calculate_growth_core(inputs: GrowthInput) -> GrowthCoreResult:
    """Calculate 30-point activity/earnings and 25-point profitability dimensions."""

    rows, activity = _require_history(inputs)
    activity_result = _activity_term(activity)
    earnings_result = _earnings_term(rows)
    if activity_result.status == "assessable" and earnings_result.status == "assessable":
        assert activity_result.points is not None and earnings_result.points is not None
        growth = TermResult(
            "assessable", activity_result.points + earnings_result.points,
            _refs(activity_result.evidence_refs, earnings_result.evidence_refs),
            _refs(activity_result.reason_codes, earnings_result.reason_codes),
            (("activity_points", activity_result.points), ("earnings_points", earnings_result.points)),
        )
    else:
        reasons = activity_result.reason_codes + earnings_result.reason_codes
        growth = _unavailable(
            reason=reasons[0] if reasons else "growth_terms_unavailable",
            evidence=_refs(activity_result.evidence_refs, earnings_result.evidence_refs),
        )
    return GrowthCoreResult(activity_result, earnings_result, growth, _profitability_term(rows))
