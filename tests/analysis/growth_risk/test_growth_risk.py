from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.analysis.growth_risk import (
    FinancialCategory,
    GrowthRiskSnapshot,
    NonFinancialBalanceSheet,
    RegulatoryCoverage,
    calculate_growth_risk,
)

PERIOD_END = date(2025, 12, 31)


def _balance(
    *,
    debt: str | None = "100",
    cash: str | None = "0",
    assets: str | None = "150",
    liabilities: str | None = "100",
    basis_id: str = "matched-basis",
    period_end: date = PERIOD_END,
    company_id: str = "company-1",
) -> NonFinancialBalanceSheet:
    return NonFinancialBalanceSheet(
        company_id, period_end, "consolidated", basis_id,
        None if debt is None else Decimal(debt),
        None if cash is None else Decimal(cash),
        None if assets is None else Decimal(assets),
        None if liabilities is None else Decimal(liabilities),
        ("balance-source",),
    )


def _snapshot(
    *,
    category: FinancialCategory = "non_financial",
    earnings: str | None = "20",
    equity: str | None = "200",
    market_cap: str | None = "400",
    cap_basis: str | None = "matched-basis",
    balance: NonFinancialBalanceSheet | None = None,
    regulations: tuple[RegulatoryCoverage, ...] = (),
) -> GrowthRiskSnapshot:
    return GrowthRiskSnapshot(
        "company-1", category, PERIOD_END, "consolidated", "matched-basis",
        None if earnings is None else Decimal(earnings),
        None if equity is None else Decimal(equity),
        None if market_cap is None else Decimal(market_cap), cap_basis,
        ("financial-source", "capital-source"),
        _balance() if balance is None and category == "non_financial" else balance,
        regulations,
    )


def test_non_financial_resilience_and_earnings_book_fixture_points() -> None:
    result = calculate_growth_risk(_snapshot())
    assert result.sector_resilience.status == "assessable"
    assert result.sector_resilience.points == Decimal("10")
    assert dict(result.sector_resilience.details) == {
        "debt_points": Decimal("6"), "liquidity_points": Decimal("4")
    }
    assert result.earnings_book_valuation.points == Decimal("12.5")
    assert dict(result.earnings_book_valuation.details)["earnings_yield"] == Decimal("0.05")
    assert dict(result.earnings_book_valuation.details)["price_to_book"] == Decimal("2")


def test_zero_current_liabilities_and_assets_are_distinct_assessable_cases() -> None:
    positive_assets = calculate_growth_risk(
        _snapshot(balance=_balance(debt="0", cash="0", assets="10", liabilities="0"))
    ).sector_resilience
    assert positive_assets.points == Decimal("20")
    assert "zero_current_liabilities_positive_assets_full_credit" in positive_assets.reason_codes

    no_assets = calculate_growth_risk(
        _snapshot(balance=_balance(debt="0", cash="0", assets="0", liabilities="0"))
    ).sector_resilience
    assert no_assets.points == Decimal("12")
    assert "zero_current_assets_and_liabilities" in no_assets.reason_codes


@pytest.mark.parametrize(
    ("debt", "cash", "assets", "liabilities", "expected"),
    [("200", "0", "100", "100", "0"), ("0", "100", "200", "100", "20")],
)
def test_non_financial_resilience_clamps_at_approved_endpoints(
    debt: str, cash: str, assets: str, liabilities: str, expected: str
) -> None:
    result = calculate_growth_risk(
        _snapshot(balance=_balance(debt=debt, cash=cash, assets=assets, liabilities=liabilities))
    ).sector_resilience
    assert result.points == Decimal(expected)


def test_nonpositive_equity_and_earnings_get_zero_applicable_factors() -> None:
    negative_equity = calculate_growth_risk(_snapshot(equity="-10"))
    assert negative_equity.sector_resilience.points == Decimal("4")
    assert "nonpositive_equity_zero_debt_factor" in negative_equity.sector_resilience.reason_codes
    assert negative_equity.earnings_book_valuation.points == Decimal("7.5")
    assert "nonpositive_equity_zero_book_value_factor" in negative_equity.earnings_book_valuation.reason_codes

    nonpositive_earnings = calculate_growth_risk(_snapshot(earnings="0"))
    assert nonpositive_earnings.earnings_book_valuation.points == Decimal("0")
    assert "nonpositive_earnings_zero_valuation_factors" in nonpositive_earnings.earnings_book_valuation.reason_codes


def test_financial_institution_uses_minimum_matched_regulatory_coverage() -> None:
    coverage = (
        RegulatoryCoverage("company-1", PERIOD_END, "matched-basis", Decimal("1.4"), Decimal("1"), ("capital-a",)),
        RegulatoryCoverage("company-1", PERIOD_END, "matched-basis", Decimal("1.25"), Decimal("1"), ("capital-b",)),
    )
    bank = calculate_growth_risk(_snapshot(category="bank", regulations=coverage))
    assert bank.sector_resilience.points == Decimal("10")
    assert dict(bank.sector_resilience.details)["minimum_regulatory_coverage"] == Decimal("1.25")
    assert "industrial" not in bank.sector_resilience.reason_codes


@pytest.mark.parametrize(("capital", "expected"), [("1", "0"), ("1.5", "20"), ("2", "20")])
def test_regulatory_coverage_clamps_at_requirement_and_full_credit(
    capital: str, expected: str
) -> None:
    coverage = RegulatoryCoverage(
        "company-1", PERIOD_END, "matched-basis", Decimal(capital), Decimal("1"), ("capital",)
    )
    result = calculate_growth_risk(_snapshot(category="bank", regulations=(coverage,))).sector_resilience
    assert result.points == Decimal(expected)


@pytest.mark.parametrize("category", ["bank", "insurer"])
def test_missing_regulatory_constraints_do_not_fall_back_to_industrial_formula(category: FinancialCategory) -> None:
    result = calculate_growth_risk(_snapshot(category=category))
    assert result.sector_resilience.status == "unavailable"
    assert result.sector_resilience.points is None
    assert result.sector_resilience.reason_codes == ("regulatory_constraints_missing",)


def test_zero_required_capital_is_unavailable_not_infinite_coverage() -> None:
    invalid = RegulatoryCoverage(
        "company-1", PERIOD_END, "matched-basis", Decimal("10"), Decimal("0"), ("capital",)
    )
    result = calculate_growth_risk(_snapshot(category="insurer", regulations=(invalid,)))
    assert result.sector_resilience.status == "unavailable"
    assert result.sector_resilience.reason_codes == ("regulatory_constraints_unmatched_or_invalid",)


def test_unmatched_inputs_are_unavailable_and_do_not_hide_independent_valuation() -> None:
    result = calculate_growth_risk(
        _snapshot(balance=_balance(basis_id="other-basis"), cap_basis="other-basis")
    )
    assert result.sector_resilience.reason_codes == ("matched_non_financial_balance_sheet_unavailable",)
    assert result.earnings_book_valuation.status == "unavailable"
    assert result.earnings_book_valuation.reason_codes == ("ordinary_market_capitalization_basis_mismatch",)


def test_missing_inputs_and_negative_balances_remain_explicit() -> None:
    missing = calculate_growth_risk(_snapshot(balance=_balance(assets=None))).sector_resilience
    assert missing.status == "unavailable"
    assert missing.reason_codes == ("non_financial_resilience_inputs_incomplete",)

    negative = calculate_growth_risk(_snapshot(balance=_balance(assets="-1"))).sector_resilience
    assert negative.status == "unavailable"
    assert negative.reason_codes == ("negative_balance_sheet_input_unsupported",)


def test_unsupported_category_and_missing_or_unmatched_capitalization_are_not_scored() -> None:
    unsupported = calculate_growth_risk(_snapshot(category="unsupported"))
    assert unsupported.sector_resilience.reason_codes == ("unsupported_financial_category",)

    missing = calculate_growth_risk(_snapshot(market_cap=None)).earnings_book_valuation
    assert missing.status == "unavailable"
    assert missing.reason_codes == ("positive_matching_ordinary_market_capitalization_required",)

    unmatched = calculate_growth_risk(_snapshot(cap_basis=None)).earnings_book_valuation
    assert unmatched.status == "unavailable"
    assert unmatched.reason_codes == ("ordinary_market_capitalization_basis_mismatch",)


@pytest.mark.parametrize(
    ("earnings", "equity", "market_cap", "expected"),
    [("100", "1000", "1000", "25"), ("90", "300", "900", "15"), ("1000", "1000", "1000", "25")],
)
def test_valuation_clamps_earnings_yield_and_book_value(
    earnings: str, equity: str, market_cap: str, expected: str
) -> None:
    result = calculate_growth_risk(
        _snapshot(earnings=earnings, equity=equity, market_cap=market_cap)
    ).earnings_book_valuation
    assert result.points == Decimal(expected)


def test_points_remain_unrounded_and_sources_are_preserved() -> None:
    result = calculate_growth_risk(
        _snapshot(balance=_balance(debt="127.123", cash="0", assets="175", liabilities="100"))
    )
    assert result.sector_resilience.points == Decimal("10.37262")
    assert result.earnings_book_valuation.points == Decimal("12.5")
    assert result.earnings_book_valuation.evidence_refs == ("financial-source", "capital-source")
