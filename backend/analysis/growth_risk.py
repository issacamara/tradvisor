"""Sector resilience and earnings/book valuation for Growth research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from backend.analysis.growth_core import TermResult

FinancialCategory = Literal["non_financial", "bank", "insurer", "unsupported"]

RESILIENCE_POINTS = Decimal("20")
DEBT_POINTS = Decimal("12")
LIQUIDITY_POINTS = Decimal("8")
EARNINGS_VALUE_POINTS = Decimal("15")
BOOK_VALUE_POINTS = Decimal("10")


@dataclass(frozen=True)
class NonFinancialBalanceSheet:
    company_id: str
    period_end: date
    report_scope: Literal["standalone", "consolidated"]
    basis_id: str
    interest_bearing_debt: Decimal | None
    unrestricted_cash: Decimal | None
    current_assets: Decimal | None
    current_liabilities: Decimal | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class RegulatoryCoverage:
    company_id: str
    effective_date: date
    basis_id: str
    jurisdiction: str
    report_scope: Literal["standalone", "consolidated"]
    capital_amount: Decimal
    required_amount: Decimal
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class GrowthRiskSnapshot:
    """Matched category and financial evidence for the two risk dimensions.

    ``market_capitalization`` must represent a positive ordinary claim on the
    same share basis as the latest annual accounts.
    """

    company_id: str
    category: FinancialCategory
    jurisdiction: str
    period_end: date
    report_scope: Literal["standalone", "consolidated"]
    basis_id: str
    ordinary_owner_earnings: Decimal | None
    equity: Decimal | None
    market_capitalization: Decimal | None
    capitalization_basis_id: str | None
    evidence_refs: tuple[str, ...]
    regulatory_constraints_complete: bool
    balance_sheet: NonFinancialBalanceSheet | None = None
    regulatory_coverages: tuple[RegulatoryCoverage, ...] = ()


@dataclass(frozen=True)
class GrowthRiskResult:
    sector_resilience: TermResult
    earnings_book_valuation: TermResult


def _unavailable(reason: str, evidence: tuple[str, ...] = ()) -> TermResult:
    return TermResult("unavailable", None, evidence, (reason,))


def _matched_balance_sheet(snapshot: GrowthRiskSnapshot) -> NonFinancialBalanceSheet | None:
    balance = snapshot.balance_sheet
    if balance is None:
        return None
    if (
        balance.company_id != snapshot.company_id
        or balance.period_end != snapshot.period_end
        or balance.report_scope != snapshot.report_scope
        or balance.basis_id != snapshot.basis_id
    ):
        return None
    return balance


def _clamp(value: Decimal) -> Decimal:
    return min(Decimal(1), max(Decimal(0), value))


def _non_financial_resilience(snapshot: GrowthRiskSnapshot) -> TermResult:
    balance = _matched_balance_sheet(snapshot)
    if balance is None:
        return _unavailable("matched_non_financial_balance_sheet_unavailable", snapshot.evidence_refs)
    refs = tuple(dict.fromkeys(snapshot.evidence_refs + balance.evidence_refs))
    values = (
        balance.interest_bearing_debt,
        balance.unrestricted_cash,
        balance.current_assets,
        balance.current_liabilities,
        snapshot.equity,
    )
    if any(value is None for value in values):
        return _unavailable("non_financial_resilience_inputs_incomplete", refs)
    debt, cash, assets, liabilities, equity = values
    assert debt is not None and cash is not None and assets is not None
    assert liabilities is not None and equity is not None
    if any(value < 0 for value in (debt, cash, assets, liabilities)):
        return _unavailable("negative_balance_sheet_input_unsupported", refs)

    reasons: list[str] = []
    if equity <= 0:
        debt_points = Decimal(0)
        reasons.append("nonpositive_equity_zero_debt_factor")
    else:
        net_debt_to_equity = (debt - cash) / equity
        debt_points = DEBT_POINTS * _clamp(Decimal(1) - max(net_debt_to_equity, Decimal(0)))

    if liabilities == 0:
        if assets > 0:
            liquidity_points = LIQUIDITY_POINTS
            reasons.append("zero_current_liabilities_positive_assets_full_credit")
        else:
            liquidity_points = Decimal(0)
            reasons.append("zero_current_assets_and_liabilities")
    else:
        current_ratio = assets / liabilities
        liquidity_points = LIQUIDITY_POINTS * _clamp(current_ratio - Decimal(1))

    return TermResult(
        "assessable", debt_points + liquidity_points, refs, tuple(reasons),
        (("debt_points", debt_points), ("liquidity_points", liquidity_points)),
    )


def _financial_institution_resilience(snapshot: GrowthRiskSnapshot) -> TermResult:
    coverages = snapshot.regulatory_coverages
    refs = tuple(dict.fromkeys(
        snapshot.evidence_refs + tuple(ref for item in coverages for ref in item.evidence_refs)
    ))
    if not coverages:
        return _unavailable("regulatory_constraints_missing", refs)
    if not snapshot.regulatory_constraints_complete:
        return _unavailable("regulatory_constraints_incomplete", refs)
    if any(
        item.company_id != snapshot.company_id
        or item.basis_id != snapshot.basis_id
        or item.jurisdiction != snapshot.jurisdiction
        or item.report_scope != snapshot.report_scope
        for item in coverages
    ):
        return _unavailable("regulatory_constraints_unmatched", refs)
    if any(item.effective_date != snapshot.period_end for item in coverages):
        return _unavailable("regulatory_constraints_not_applicable_as_of_period_end", refs)
    if any(
        item.required_amount <= 0
        or item.capital_amount < 0
        for item in coverages
    ):
        return _unavailable("regulatory_constraints_invalid", refs)
    coverage = min(item.capital_amount / item.required_amount for item in coverages)
    points = RESILIENCE_POINTS * _clamp((coverage - Decimal(1)) / Decimal("0.5"))
    return TermResult(
        "assessable", points, refs, (),
        (("minimum_regulatory_coverage", coverage), ("resilience_points", points)),
    )


def _valuation(snapshot: GrowthRiskSnapshot) -> TermResult:
    refs = snapshot.evidence_refs
    if snapshot.ordinary_owner_earnings is None or snapshot.equity is None:
        return _unavailable("latest_earnings_or_equity_missing", refs)
    market_cap = snapshot.market_capitalization
    if market_cap is None or market_cap <= 0:
        return _unavailable("positive_matching_ordinary_market_capitalization_required", refs)
    if snapshot.capitalization_basis_id is None or snapshot.capitalization_basis_id != snapshot.basis_id:
        return _unavailable("ordinary_market_capitalization_basis_mismatch", refs)

    earnings = snapshot.ordinary_owner_earnings
    equity = snapshot.equity
    earnings_yield: Decimal | None = None
    price_to_book: Decimal | None = None
    if earnings <= 0:
        earnings_points = Decimal(0)
        book_points = Decimal(0)
        reasons: tuple[str, ...] = ("nonpositive_earnings_zero_valuation_factors",)
    else:
        earnings_yield = earnings / market_cap
        earnings_points = EARNINGS_VALUE_POINTS * _clamp(earnings_yield / Decimal("0.10"))
        if equity <= 0:
            book_points = Decimal(0)
            reasons = ("nonpositive_equity_zero_book_value_factor",)
        else:
            price_to_book = market_cap / equity
            book_points = BOOK_VALUE_POINTS * _clamp((Decimal(3) - price_to_book) / Decimal(2))
            reasons = ()

    return TermResult(
        "assessable", earnings_points + book_points, refs, reasons,
        (("earnings_yield", earnings_yield), ("price_to_book", price_to_book),
         ("earnings_value_points", earnings_points), ("book_value_points", book_points)),
    )


def calculate_growth_risk(snapshot: GrowthRiskSnapshot) -> GrowthRiskResult:
    """Calculate category-appropriate resilience and earnings/book points."""

    if snapshot.category == "non_financial":
        resilience = _non_financial_resilience(snapshot)
    elif snapshot.category in ("bank", "insurer"):
        resilience = _financial_institution_resilience(snapshot)
    else:
        resilience = _unavailable("unsupported_financial_category", snapshot.evidence_refs)
    valuation = _valuation(snapshot)
    return GrowthRiskResult(resilience, valuation)
