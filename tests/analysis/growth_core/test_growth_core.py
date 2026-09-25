"""Focused fixtures for the approved Growth core dimensions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.analysis.growth_core import (
    ActivityObservation,
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
    activity: tuple[str | None, ...] = ("100", "100", "100", "100", "100"),
    kind: str = "revenue",
) -> GrowthInput:
    rows: list[NormalizedFinancial] = []
    activity_rows: list[ActivityObservation] = []
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
        activity_rows.append(
            ActivityObservation(
                fiscal_period_end=end,
                kind=kind,  # type: ignore[arg-type]
                value=None if activity[index] is None else Decimal(activity[index]),
                evidence_refs=(f"activity-source-{index}",),
            )
        )
    return GrowthInput("company-1", tuple(rows), tuple(activity_rows))


@pytest.mark.parametrize(
    ("activity_factor", "earnings_factor", "expected"),
    [(0, 0, 0), (1, 0, 12), (0, 1, 18), (1, 1, 30)],
)
def test_growth_dimension_preserves_12_18_point_allocation(
    activity_factor: int, earnings_factor: int, expected: int
) -> None:
    activity_latest = "152.0875" if activity_factor else "100"
    earnings_latest = "17.28" if earnings_factor else "10"
    result = calculate_growth_core(
        _input(activity=("100", "100", "100", "100", activity_latest),
               earnings=("10", "10", "10", "10", earnings_latest))
    )
    assert result.growth.status == "assessable"
    assert result.growth.points == Decimal(expected)


def test_growth_uses_three_year_endpoints_and_caps_contributions() -> None:
    result = calculate_growth_core(
        _input(
            activity=("1", "100", "100", "100", "172.8"),
            earnings=("1", "10", "10", "10", "21.6"),
        )
    )
    assert result.activity_growth.points == Decimal("12")
    assert result.earnings_growth.points == Decimal("18")
    assert dict(result.activity_growth.details)["starting_value"] == Decimal("100")

    half_credit = calculate_growth_core(
        _input(activity=("1", "100", "100", "100", "124.2296875"),
               earnings=("1", "100", "100", "100", "133.1"))
    )
    assert half_credit.activity_growth.points == pytest.approx(6)
    assert half_credit.earnings_growth.points == pytest.approx(9)
    assert half_credit.growth.points == pytest.approx(15)


@pytest.mark.parametrize(
    ("activity_values", "expected_reason"),
    [(("10", "10", "10", "10", "0"), "nonpositive_latest_activity"),
     (("10", "0", "10", "10", "20"), "nonpositive_activity_base_recovery")],
)
def test_nonpositive_activity_endpoints_earn_zero_without_cagr(
    activity_values: tuple[str, ...], expected_reason: str
) -> None:
    result = calculate_growth_core(_input(activity=activity_values))
    assert result.activity_growth.points == 0
    assert expected_reason in result.activity_growth.reason_codes
    assert dict(result.activity_growth.details)["cagr"] is None


def test_negative_bank_activity_is_observed_zero_and_negative_revenue_is_unsupported() -> None:
    bank = calculate_growth_core(
        _input(kind="net_banking_income", activity=("10", "-10", "10", "10", "20"))
    )
    assert bank.activity_growth.status == "assessable"
    assert bank.activity_growth.points == 0
    assert "nonpositive_activity_base_recovery" in bank.activity_growth.reason_codes

    industrial = calculate_growth_core(
        _input(kind="revenue", activity=("10", "-1", "10", "10", "20"))
    )
    assert industrial.activity_growth.status == "unavailable"
    assert industrial.activity_growth.reason_codes == ("unsupported_negative_activity_semantics",)


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
    assert result.growth.status == "assessable"
    assert result.profitability.status == "unavailable"
    assert result.profitability.points is None

    missing_earnings = calculate_growth_core(_input(earnings=("10", "10", None, "10", "10")))
    assert missing_earnings.growth.status == "unavailable"
    assert missing_earnings.profitability.status == "unavailable"


def test_missing_activity_is_unavailable_and_no_points_are_redistributed() -> None:
    result = calculate_growth_core(_input(activity=("100", "100", "100", None, "200")))
    assert result.activity_growth.status == "unavailable"
    assert result.growth.status == "unavailable"
    assert result.profitability.status == "assessable"


def test_unpublished_or_incomparable_financial_history_has_explicit_unavailable_reason() -> None:
    source = _input()
    rows = list(source.financials)
    rows[2] = rows[2].model_copy(update={"publication_status": "unknown", "reason_codes": ("source_unknown",)})
    unpublished = calculate_growth_core(GrowthInput(source.company_id, tuple(rows), source.activity))
    assert unpublished.earnings_growth.reason_codes == ("annual_report_unavailable",)
    assert unpublished.profitability.reason_codes == ("annual_report_unavailable",)

    rows = list(source.financials)
    rows[2] = rows[2].model_copy(update={"report_scope": "unknown"})
    unknown_scope = calculate_growth_core(GrowthInput(source.company_id, tuple(rows), source.activity))
    assert unknown_scope.earnings_growth.reason_codes == ("reporting_scope_unknown",)


def test_mixed_activity_measure_is_unavailable_and_latest_change_is_context_only() -> None:
    source = _input(activity=("100", "100", "100", "100", "152.0875"))
    baseline = calculate_growth_core(source)
    activity = list(source.activity)
    activity[-2] = ActivityObservation(
        activity[-2].fiscal_period_end, activity[-2].kind, Decimal("80"), activity[-2].evidence_refs
    )
    revised_context = calculate_growth_core(GrowthInput(source.company_id, source.financials, tuple(activity)))
    assert revised_context.activity_growth.points == baseline.activity_growth.points

    activity[2] = ActivityObservation(
        activity[2].fiscal_period_end, "net_banking_income", activity[2].value, activity[2].evidence_refs
    )
    mixed = calculate_growth_core(GrowthInput(source.company_id, source.financials, tuple(activity)))
    assert mixed.activity_growth.status == "unavailable"
    assert mixed.activity_growth.reason_codes == ("incomparable_activity_measure",)


def test_gap_in_annual_history_is_rejected_instead_of_interpolated() -> None:
    source = _input()
    rows = list(source.financials)
    row = rows[2].model_copy(update={"fiscal_period_start": date(2022, 2, 1)})
    rows[2] = row
    with pytest.raises(GrowthCalculationError, match="consecutive"):
        calculate_growth_core(GrowthInput(source.company_id, tuple(rows), source.activity))


def test_six_annual_equity_dates_must_reconcile() -> None:
    source = _input()
    rows = list(source.financials)
    rows[2] = rows[2].model_copy(update={"opening_equity": _money("101", signed=True)})
    result = calculate_growth_core(GrowthInput(source.company_id, tuple(rows), source.activity))
    assert result.profitability.status == "unavailable"
    assert result.profitability.reason_codes == ("six_equity_dates_inconsistent",)


def test_results_retain_unrounded_points_evidence_and_unavailability_reasons() -> None:
    result = calculate_growth_core(
        _input(activity=("100", "100", "100", "100", "115"))
    )
    assert result.activity_growth.points == Decimal("3.81516425373178325564700024")
    assert "activity-source-0" in result.activity_growth.evidence_refs
    assert "annual-source-0" in result.profitability.evidence_refs
