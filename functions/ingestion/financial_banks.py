"""Normalize bank-specific annual evidence without industrial fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from financial_normalization import AnnualFinancialRecord, NormalizedAmount, _amount, _date, normalize_annual_report


@dataclass(frozen=True)
class BankCapitalConstraint:
    constraint_id: str | None
    disclosed_ratio: Decimal | None
    required_ratio: Decimal | None
    period_end: date | None
    jurisdiction: str | None
    report_scope: str
    applicable: bool | None
    unavailable_reasons: tuple[str, ...]

    @property
    def coverage(self) -> Decimal | None:
        if self.disclosed_ratio is None or self.required_ratio is None or self.required_ratio <= 0:
            return None
        return self.disclosed_ratio / self.required_ratio


@dataclass(frozen=True)
class BankFinancialInputs:
    annual_record: AnnualFinancialRecord
    regulatory_jurisdiction: str | None
    net_banking_income: NormalizedAmount | None
    capital_constraints: tuple[BankCapitalConstraint, ...]
    minimum_capital_coverage: Decimal | None
    unavailable_reasons: tuple[str, ...]


def _annual_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    nested = report.get("annual_report")
    merged = dict(report)
    if isinstance(nested, Mapping):
        merged.update(nested)
    return merged


def _ratio(value: Any) -> Decimal | None:
    if not isinstance(value, Mapping) or value.get("evidenced") is not True:
        return None
    raw, unit = value.get("value"), value.get("unit")
    if not isinstance(raw, (str, int)) or isinstance(raw, bool):
        return None
    if unit not in {"ratio", "percent"}:
        return None
    try:
        result = Decimal(str(raw))
    except InvalidOperation:
        return None
    if not result.is_finite() or result < 0:
        return None
    return result / Decimal("100") if unit == "percent" else result


def _constraint(raw: Any, annual: AnnualFinancialRecord, jurisdiction: Any) -> BankCapitalConstraint:
    reasons: list[str] = []
    if not isinstance(raw, Mapping):
        return BankCapitalConstraint(None, None, None, None, None, "unknown", None, ("capital_constraint_invalid",))

    constraint_id = raw.get("constraint_id")
    if not isinstance(constraint_id, str) or not constraint_id.strip():
        constraint_id = None
        reasons.append("capital_constraint_id_unknown")
    else:
        constraint_id = constraint_id.strip()

    period_end = _date(raw.get("period_end"))
    scope = raw.get("report_scope")
    scope = scope if isinstance(scope, str) and scope in {"standalone", "consolidated"} else "unknown"
    item_jurisdiction = raw.get("jurisdiction")
    if not isinstance(item_jurisdiction, str) or not item_jurisdiction.strip():
        item_jurisdiction = None
    else:
        item_jurisdiction = item_jurisdiction.strip()
    applicable = raw.get("applicable") if isinstance(raw.get("applicable"), bool) else None

    disclosed = _ratio(raw.get("disclosed"))
    required = _ratio(raw.get("required"))
    if disclosed is None:
        reasons.append("disclosed_capital_ratio_unavailable")
    if required is None or required <= 0:
        required = None
        reasons.append("required_capital_ratio_unavailable")
    if period_end is None or period_end != annual.period_end:
        reasons.append("capital_constraint_date_mismatch")
    if scope == "unknown" or scope != annual.report_scope:
        reasons.append("capital_constraint_scope_mismatch")
    expected_jurisdiction = jurisdiction.strip() if isinstance(jurisdiction, str) and jurisdiction.strip() else None
    if item_jurisdiction is None or expected_jurisdiction is None or item_jurisdiction != expected_jurisdiction:
        reasons.append("capital_constraint_jurisdiction_mismatch")
    if applicable is None:
        reasons.append("capital_constraint_applicability_unknown")

    if reasons:
        disclosed = None
        required = None
    return BankCapitalConstraint(
        constraint_id,
        disclosed,
        required,
        period_end,
        item_jurisdiction,
        scope,
        applicable,
        tuple(dict.fromkeys(reasons)),
    )


def normalize_bank_report(report: Mapping[str, Any]) -> BankFinancialInputs:
    """Normalize bank activity and applicable capital evidence from a recorded report."""
    source = _annual_payload(report)
    annual = normalize_annual_report(source)
    reasons: list[str] = []
    pnb: NormalizedAmount | None = None
    if annual.financial_category != "bank":
        reasons.append("bank_category_unverified")
    else:
        pnb_reasons: list[str] = []
        pnb = _amount(source, "pnb", pnb_reasons)
        pnb_evidence = source.get("pnb")
        if not isinstance(pnb_evidence, Mapping):
            pnb = None
            pnb_reasons.append("pnb_evidence_unavailable")
        else:
            if _date(pnb_evidence.get("period_end")) != annual.period_end:
                pnb = None
                pnb_reasons.append("pnb_date_mismatch")
            if pnb_evidence.get("report_scope") != annual.report_scope:
                pnb = None
                pnb_reasons.append("pnb_scope_mismatch")
        reasons.extend(pnb_reasons)

    raw_constraints = source.get("capital_constraints")
    if not isinstance(raw_constraints, Sequence) or isinstance(raw_constraints, (str, bytes)):
        raw_constraints = ()
    constraints = tuple(_constraint(item, annual, source.get("regulatory_jurisdiction")) for item in raw_constraints)
    complete = source.get("applicable_constraints_complete") is True
    minimum: Decimal | None = None
    if annual.financial_category != "bank":
        reasons.append("bank_capital_not_applicable")
    elif not complete:
        reasons.append("applicable_capital_constraints_incomplete")
    elif not constraints:
        reasons.append("applicable_capital_constraints_missing")
    elif any(item.applicable is True and item.coverage is None for item in constraints) or any(
        item.applicable is None for item in constraints
    ):
        reasons.append("applicable_capital_constraint_unavailable")
    else:
        applicable = [item.coverage for item in constraints if item.applicable is True]
        if not applicable or any(value is None for value in applicable):
            reasons.append("applicable_capital_constraints_missing")
        else:
            minimum = min(value for value in applicable if value is not None)
    for constraint in constraints:
        reasons.extend(constraint.unavailable_reasons)
    raw_jurisdiction = source.get("regulatory_jurisdiction")
    regulatory_jurisdiction = (
        raw_jurisdiction.strip()
        if isinstance(raw_jurisdiction, str) and raw_jurisdiction.strip()
        else None
    )
    return BankFinancialInputs(
        annual,
        regulatory_jurisdiction,
        pnb,
        constraints,
        minimum,
        tuple(dict.fromkeys(reasons)),
    )


def assess_bank_capital_history(records: Sequence[BankFinancialInputs]) -> bool:
    """Return true only when every annual record has dated, comparable capital coverage."""
    if not records:
        return False
    ordered = sorted(records, key=lambda item: item.annual_record.fiscal_year or -1)
    first = ordered[0]
    years = [
        item.annual_record.fiscal_year
        for item in ordered
        if item.annual_record.fiscal_year is not None
    ]
    return (
        len(years) == len(ordered)
        and all(later == earlier + 1 for earlier, later in zip(years, years[1:]))
        and all(
            item.annual_record.financial_category == "bank"
            and item.annual_record.company_id == first.annual_record.company_id
            and item.annual_record.report_scope == first.annual_record.report_scope
            and item.regulatory_jurisdiction == first.regulatory_jurisdiction
            and item.regulatory_jurisdiction is not None
            and item.minimum_capital_coverage is not None
            and item.annual_record.period_end is not None
            for item in ordered
        )
    )
