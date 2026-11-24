"""Normalize insurer-specific premium and solvency evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Mapping, Sequence

from financial_normalization import AnnualFinancialRecord, NormalizedAmount, _amount, _date, normalize_annual_report


@dataclass(frozen=True)
class InsurerFinancialInputs:
    annual_record: AnnualFinancialRecord
    gross_written_premiums: NormalizedAmount | None
    premium_basis: str | None
    premium_period_start: date | None
    premium_period_end: date | None
    premium_scope: str
    premium_regulatory_basis: str | None
    eligible_solvency_amount: NormalizedAmount | None
    required_solvency_amount: NormalizedAmount | None
    solvency_period_end: date | None
    solvency_jurisdiction: str | None
    solvency_scope: str
    solvency_regulatory_basis: str | None
    solvency_coverage: Decimal | None
    unavailable_reasons: tuple[str, ...]


@dataclass(frozen=True)
class PremiumComparability:
    comparable: bool
    reason: str | None


def _annual_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    nested = report.get("annual_report")
    merged = dict(report)
    if isinstance(nested, Mapping):
        merged.update(nested)
    return merged


def normalize_insurer_report(report: Mapping[str, Any]) -> InsurerFinancialInputs:
    """Normalize premiums and solvency only when report evidence is matched."""
    source = _annual_payload(report)
    annual = normalize_annual_report(source)
    reasons: list[str] = []
    premium: NormalizedAmount | None = None
    premium_basis: str | None = None
    premium_start: date | None = None
    premium_end: date | None = None
    premium_scope = "unknown"
    premium_regulatory_basis: str | None = None

    raw_premium = source.get("gross_written_premiums")
    if annual.financial_category != "insurer":
        reasons.append("insurer_category_unverified")
    elif isinstance(raw_premium, Mapping):
        premium_reasons: list[str] = []
        premium = _amount(source, "gross_written_premiums", premium_reasons)
        reasons.extend(premium_reasons)
        basis = raw_premium.get("premium_basis")
        if isinstance(basis, str) and basis.strip():
            premium_basis = basis.strip()
        else:
            reasons.append("premium_basis_unavailable")
        premium_start = _date(raw_premium.get("period_start"))
        premium_end = _date(raw_premium.get("period_end"))
        if premium_start is None or premium_end is None or premium_start > premium_end:
            reasons.append("premium_period_unavailable")
        if (
            not annual.full_year
            or premium_start != annual.period_start
            or premium_end != annual.period_end
        ):
            reasons.append("premium_period_mismatch")
        scope = raw_premium.get("report_scope")
        premium_scope = scope if isinstance(scope, str) and scope in {"standalone", "consolidated"} else "unknown"
        if premium_scope == "unknown" or premium_scope != annual.report_scope:
            reasons.append("premium_scope_mismatch")
        regulatory_basis = raw_premium.get("regulatory_basis")
        if isinstance(regulatory_basis, str) and regulatory_basis.strip():
            premium_regulatory_basis = regulatory_basis.strip()
        else:
            reasons.append("premium_regulatory_basis_unavailable")
        if reasons:
            premium = None
    else:
        reasons.append("gross_written_premiums_unavailable")

    eligible: NormalizedAmount | None = None
    required: NormalizedAmount | None = None
    solvency_end: date | None = None
    solvency_jurisdiction: str | None = None
    solvency_scope = "unknown"
    solvency_basis: str | None = None
    solvency = source.get("solvency")
    if annual.financial_category != "insurer":
        reasons.append("insurer_solvency_not_applicable")
    elif not isinstance(solvency, Mapping):
        reasons.append("solvency_evidence_unavailable")
    elif solvency.get("evidenced") is not True:
        reasons.append("solvency_evidence_unverified")
    else:
        amount_reasons: list[str] = []
        solvency_amounts = dict(solvency)
        solvency_amounts.setdefault("currency", source.get("currency"))
        eligible = _amount(solvency_amounts, "eligible", amount_reasons)
        required = _amount(solvency_amounts, "required", amount_reasons)
        reasons.extend(amount_reasons)
        solvency_end = _date(solvency.get("period_end"))
        if solvency_end is None or solvency_end != annual.period_end:
            reasons.append("solvency_date_mismatch")
        scope = solvency.get("report_scope")
        solvency_scope = scope if isinstance(scope, str) and scope in {"standalone", "consolidated"} else "unknown"
        if solvency_scope == "unknown" or solvency_scope != annual.report_scope:
            reasons.append("solvency_scope_mismatch")
        jurisdiction = solvency.get("jurisdiction")
        solvency_jurisdiction = jurisdiction.strip() if isinstance(jurisdiction, str) and jurisdiction.strip() else None
        if solvency_jurisdiction is None:
            reasons.append("solvency_jurisdiction_unavailable")
        basis = solvency.get("regulatory_basis")
        solvency_basis = basis.strip() if isinstance(basis, str) and basis.strip() else None
        if solvency_basis is None:
            reasons.append("solvency_regulatory_basis_unavailable")
        if eligible is None or eligible.value < 0:
            eligible = None
            reasons.append("eligible_solvency_amount_invalid")
        if required is None or required.value <= 0:
            required = None
            reasons.append("required_solvency_amount_invalid")
        if any(
            reason.startswith("solvency_")
            for reason in reasons
        ):
            eligible = required = None

    coverage = None
    if eligible is not None and required is not None and required.value > 0:
        coverage = eligible.value / required.value
    return InsurerFinancialInputs(
        annual,
        premium,
        premium_basis,
        premium_start,
        premium_end,
        premium_scope,
        premium_regulatory_basis,
        eligible,
        required,
        solvency_end,
        solvency_jurisdiction,
        solvency_scope,
        solvency_basis,
        coverage,
        tuple(dict.fromkeys(reasons)),
    )


def assess_premium_comparability(records: Sequence[InsurerFinancialInputs]) -> PremiumComparability:
    """Require a consistent gross premium basis across a fiscal-year series."""
    if not records:
        return PremiumComparability(False, "premium_history_missing")
    first = records[0]
    if any(item.gross_written_premiums is None for item in records):
        return PremiumComparability(False, "gross_written_premiums_unavailable")
    for item in records:
        annual = item.annual_record
        if (
            annual.financial_category != "insurer"
            or annual.fiscal_year is None
            or not annual.full_year
            or item.premium_period_start != annual.period_start
            or item.premium_period_end != annual.period_end
            or item.premium_scope != annual.report_scope
            or item.premium_basis is None
            or item.premium_regulatory_basis is None
        ):
            return PremiumComparability(False, "premium_period_or_scope_mismatch")
        if (
            item.premium_basis != first.premium_basis
            or item.premium_regulatory_basis != first.premium_regulatory_basis
            or annual.currency != first.annual_record.currency
            or annual.accounting_basis != first.annual_record.accounting_basis
            or item.premium_scope != first.premium_scope
        ):
            return PremiumComparability(False, "premium_basis_or_scope_incomparable")
        if item.annual_record.company_id != first.annual_record.company_id:
            return PremiumComparability(False, "premium_company_mismatch")
    ordered = sorted(records, key=lambda item: item.annual_record.fiscal_year or -1)
    years = [
        item.annual_record.fiscal_year
        for item in ordered
        if item.annual_record.fiscal_year is not None
    ]
    if len(years) != len(records) or any(later != earlier + 1 for earlier, later in zip(years, years[1:])):
        return PremiumComparability(False, "premium_periods_not_consecutive")
    first_start = first.annual_record.period_start
    first_end = first.annual_record.period_end
    if any(
        item.annual_record.period_start is None
        or item.annual_record.period_end is None
        or first_start is None
        or first_end is None
        or (item.annual_record.period_start.month, item.annual_record.period_start.day)
        != (first_start.month, first_start.day)
        or (item.annual_record.period_end.month, item.annual_record.period_end.day)
        != (first_end.month, first_end.day)
        or not 360 <= (item.annual_record.period_end - item.annual_record.period_start).days <= 370
        for item in ordered
    ) or any(
        earlier.annual_record.period_end is None
        or later.annual_record.period_start is None
        or later.annual_record.period_start != earlier.annual_record.period_end + timedelta(days=1)
        for earlier, later in zip(ordered, ordered[1:])
    ):
        return PremiumComparability(False, "premium_periods_incomparable")
    return PremiumComparability(True, None)
