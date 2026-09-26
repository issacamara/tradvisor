"""Focused fixtures for the approved Growth core dimensions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.analysis.growth_core import (
    GrowthCalculationError,
    GrowthInput,
    calculate_growth_core,
)
from backend.contracts.analysis import NormalizedFinancial, Provenance, Revision
from backend.contracts.scalars import NonNegativeMoney, SignedMoney

NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)


def _money(value: str, *, signed: bool = False) -> SignedMoney | NonNegativeMoney:
    cls = SignedMoney if signed else NonNegativeMoney
    return cls(amount=value, currency="XOF")


def _input(
    *,
    earnings: tuple[str | None, ...] = ("10",) * 5,
    opening_equity: tuple[str | None, ...] = ("100",) * 5,
    equity: tuple[str | None, ...] = ("100",) * 5,
) -> GrowthInput:
    rows: list[NormalizedFinancial] = []
    for index in range(5):
        start = date(2020 + index, 1, 1)
        end = date(2020 + index, 12, 31)
        provenance = Provenance(
            source_id=f"annual-source-{index}", collected_at=NOW, original_unit="XOF", basis="actual"
        )
        revision = Revision(revision=index, known_at=NOW, provenance=provenance)
        rows.append(
            NormalizedFinancial(
                company_id="company-1", fiscal_period_start=start, fiscal_period_end=end,
                report_scope="consolidated", currency="XOF", original_scale="units",
                revenue=_money("100"),
                ordinary_owner_earnings=None if earnings[index] is None else _money(earnings[index], signed=True),
                opening_equity=None if opening_equity[index] is None else _money(opening_equity[index], signed=True),
                equity=None if equity[index] is None else _money(equity[index], signed=True),
                publication_status="published", revision=revision,
            )
        )
    return GrowthInput("company-1", tuple(rows))


def test_normalized_earnings_scores_but_growth_composite_is_unavailable_without_activity() -> None:
    result = calculate_growth_core(_input(earnings=("10", "10", "10", "10", "17.28")))
    assert result.activity_growth.status == "unavailable"
    assert result.activity_growth.reason_codes == ("normalized_activity_measure_unavailable",)
    assert result.earnings_growth.status == "assessable"
    assert result.earnings_growth.points == Decimal("18")
    assert result.growth.status == "unavailable"
    assert result.growth.points is None
    assert result.growth.reason_codes == ("normalized_activity_measure_unavailable",)


def test_earnings_uses_three_year_endpoints_and_caps_contribution() -> None:
    result = calculate_growth_core(_input(earnings=("1", "10", "10", "10", "21.6")))
    assert result.earnings_growth.points == Decimal("18")
    assert dict(result.earnings_growth.details)["starting_earnings"] == Decimal("10")

    half_credit = calculate_growth_core(
        _input(earnings=("1", "100", "100", "100", "133.1"))
    )
    assert half_credit.earnings_growth.points == pytest.approx(9)
    assert half_credit.growth.status == "unavailable"


def test_bank_activity_remains_unavailable_and_detached_activity_cannot_be_scored() -> None:
    bank = calculate_growth_core(_input())
    assert bank.activity_growth.status == "unavailable"
    assert bank.activity_growth.points is None
    assert bank.activity_growth.reason_codes == ("normalized_activity_measure_unavailable",)
    assert bank.earnings_growth.status == "assessable"
    assert bank.growth.status == "unavailable"

    with pytest.raises(TypeError):
        GrowthInput("company-1", _input().financials, activity=())  # type: ignore[call-arg]


def test_latest_losses_and_recoveries_earn_zero_growth_and_report_reasons() -> None:
    loss = calculate_growth_core(_input(earnings=("10", "10", "10", "10", "0")))
    assert loss.earnings_growth.points == 0
    assert "latest_earnings_nonpositive" in loss.earnings_growth.reason_codes
    assert dict(loss.earnings_growth.details)["cagr"] is None

    recovery = calculate_growth_core(_input(earnings=("-10", "-5", "2", "3", "10")))
    assert recovery.earnings_growth.points == 0
    assert "nonpositive_earnings_base_recovery" in recovery.earnings_growth.reason_codes


def test_small_base_warning_is_strict_and_uses_all_five_years_including_zero() -> None:
    equality = calculate_growth_core(
        _input(earnings=("100", "10", "100", "100", "100"))
    )
    assert dict(equality.earnings_growth.details)["five_year_absolute_earnings_median"] == Decimal("100")
    assert dict(equality.earnings_growth.details)["small_base_warning"] is False

    below = calculate_growth_core(
        _input(earnings=("100", "9.9", "100", "100", "100"))
    )
    assert dict(below.earnings_growth.details)["small_base_warning"] is True
    assert "small_earnings_base" in below.earnings_growth.reason_codes

    zero_median = calculate_growth_core(_input(earnings=("0", "1", "0", "0", "0")))
    assert dict(zero_median.earnings_growth.details)["five_year_absolute_earnings_median"] == 0
    assert dict(zero_median.earnings_growth.details)["small_base_warning"] is False


def test_profitability_fixtures_are_25_and_15_point_5() -> None:
    full = calculate_growth_core(_input(earnings=("15",) * 5))
    assert full.profitability.points == Decimal("25")

    partial = calculate_growth_core(
        _input(earnings=("-1", "7.5", "7.5", "7.5", "7.5"))
    )
    assert partial.profitability.points == Decimal("15.5")


@pytest.mark.parametrize(
    "opening_equity,equity",
    [(("0",) + ("100",) * 4, ("100",) * 5), (("100",) * 5, ("100",) * 4 + ("-1",))],
)
def test_nonpositive_equity_is_zero_factor_with_reason(
    opening_equity: tuple[str, ...], equity: tuple[str, ...]
) -> None:
    result = calculate_growth_core(_input(opening_equity=opening_equity, equity=equity))
    assert result.profitability.status == "assessable"
    assert result.profitability.points is not None
    assert "nonpositive_equity_zero_roe_factor" in result.profitability.reason_codes


def test_unknown_equity_or_earnings_makes_only_profitability_unavailable() -> None:
    result = calculate_growth_core(
        _input(opening_equity=("100", "100", None, "100", "100"))
    )
    assert result.earnings_growth.status == "assessable"
    assert result.growth.status == "unavailable"
    assert result.growth.reason_codes == ("normalized_activity_measure_unavailable",)
    assert result.profitability.status == "unavailable"
    assert result.profitability.points is None

    missing_earnings = calculate_growth_core(_input(earnings=("10", "10", None, "10", "10")))
    assert missing_earnings.growth.status == "unavailable"
    assert missing_earnings.profitability.status == "unavailable"


def test_unavailable_activity_is_not_redistributed_to_growth_or_profitability() -> None:
    result = calculate_growth_core(_input(earnings=("10", "10", "10", "10", "17.28")))
    assert result.growth.status == "unavailable"
    assert result.growth.points is None
    assert result.earnings_growth.points == Decimal("18")
    assert result.profitability.status == "assessable"


def test_unpublished_or_incomparable_financial_history_has_explicit_unavailable_reason() -> None:
    source = _input()
    rows = list(source.financials)
    rows[2] = rows[2].model_copy(update={"publication_status": "unknown", "reason_codes": ("source_unknown",)})
    unpublished = calculate_growth_core(GrowthInput(source.company_id, tuple(rows)))
    assert unpublished.earnings_growth.reason_codes == ("annual_report_unavailable",)
    assert unpublished.profitability.reason_codes == ("annual_report_unavailable",)

    rows = list(source.financials)
    rows[2] = rows[2].model_copy(update={"report_scope": "unknown"})
    unknown_scope = calculate_growth_core(GrowthInput(source.company_id, tuple(rows)))
    assert unknown_scope.earnings_growth.reason_codes == ("reporting_scope_unknown",)


def test_gap_in_annual_history_is_rejected_instead_of_interpolated() -> None:
    source = _input()
    rows = list(source.financials)
    row = rows[2].model_copy(update={"fiscal_period_start": date(2022, 2, 1)})
    rows[2] = row
    with pytest.raises(GrowthCalculationError, match="consecutive"):
        calculate_growth_core(GrowthInput(source.company_id, tuple(rows)))


def test_six_annual_equity_dates_must_reconcile() -> None:
    source = _input()
    rows = list(source.financials)
    rows[2] = rows[2].model_copy(update={"opening_equity": _money("101", signed=True)})
    result = calculate_growth_core(GrowthInput(source.company_id, tuple(rows)))
    assert result.profitability.status == "unavailable"
    assert result.profitability.reason_codes == ("six_equity_dates_inconsistent",)


def test_results_retain_unrounded_points_evidence_and_unavailability_reasons() -> None:
    result = calculate_growth_core(
        _input(earnings=("10", "10", "10", "10", "11.5"))
    )
    assert result.activity_growth.points is None
    assert result.activity_growth.reason_codes == ("normalized_activity_measure_unavailable",)
    assert "annual-source-0" in result.profitability.evidence_refs
