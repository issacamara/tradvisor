"""Fixture coverage for bounded dividend research and deferred scores."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.analysis.dividend_research import (
    DividendResearchError,
    DividendResearchInput,
    ShareBasisAdjustment,
    calculate_dividend_research,
)
from backend.contracts.analysis import (
    NormalizedDividend,
    NormalizedDividendCoverage,
    NormalizedPrice,
    Provenance,
    Revision,
)
from backend.contracts.scalars import NonNegativeMoney

AS_OF = datetime(2026, 9, 23, 18, tzinfo=timezone.utc)
VALUATION_DATE = date(2026, 9, 23)
LOWER_BOUND = date(2025, 9, 23)


def revision(*, known_at: datetime = AS_OF, number: int = 1, basis: str = "actual") -> Revision:
    return Revision(
        revision=number,
        known_at=known_at,
        provenance=Provenance(
            source_id="fixture-source",
            collected_at=known_at,
            published_at=known_at,
            original_unit="XOF per share",
            basis=basis,
        ),
    )


def money(amount: str) -> NonNegativeMoney:
    return NonNegativeMoney(amount=amount, currency="XOF")


def payment(
    *,
    installment: str = "installment-1",
    payment_date: date | None = date(2026, 5, 1),
    status: str = "paid",
    kind: str = "ordinary",
    amount: str = "50",
    semantics: str = "gross",
    known_at: datetime = AS_OF,
    revision_number: int = 1,
) -> NormalizedDividend:
    return NormalizedDividend(
        dividend_id=f"payment-{installment}",
        company_id="company-1",
        installment_id=installment,
        payment_date=payment_date,
        fiscal_period_end=date(2025, 12, 31),
        gross_amount_per_share=money(amount),
        gross_total_amount=money("50000"),
        per_share_semantics=semantics,
        total_semantics="gross",
        payment_status=status,
        dividend_type=kind,
        reason_codes=("payment_unresolved",) if status == "unknown" else (),
        revision=revision(known_at=known_at, number=revision_number),
    )


def coverage(
    *,
    start: date = LOWER_BOUND,
    end: date = VALUATION_DATE,
    status: str = "complete",
    outcome: str = "payments_recorded",
    known_at: datetime = AS_OF,
    revision_number: int = 1,
) -> NormalizedDividendCoverage:
    return NormalizedDividendCoverage(
        company_id="company-1",
        covered_interval_start=start,
        covered_interval_end=end,
        coverage_basis="trailing_12_months",
        coverage_status=status,
        payment_outcome=outcome,
        reason_codes=() if status == "complete" else ("coverage_incomplete",),
        revision=revision(known_at=known_at, number=revision_number),
    )


def price(*, basis: str = "actual", session_date: date = VALUATION_DATE) -> NormalizedPrice:
    return NormalizedPrice(
        symbol="ABC",
        session_date=session_date,
        close=money("1000"),
        trade_status="traded",
        basis=basis,
        original_source_date=session_date,
        price_basis_ref="current-share-basis",
        validated_available_at=AS_OF,
        suspension_status="not_suspended",
        revision=revision(),
    )


def adjustment(
    installment: str = "installment-1",
    *,
    factor: str = "1",
    verified: bool = True,
    target: str = "current-share-basis",
    known_at: datetime = AS_OF,
    revision_number: int = 1,
) -> ShareBasisAdjustment:
    return ShareBasisAdjustment(
        installment_id=installment,
        source_share_basis_ref="payment-share-basis",
        target_share_basis_ref=target,
        dps_multiplier=Decimal(factor),
        known_at=known_at,
        revision=revision_number,
        evidence_ref=f"adjustment-{installment}",
        verified=verified,
    )


def source(
    *,
    symbol: str = "ABC",
    payments: tuple[NormalizedDividend, ...] | None = None,
    coverages: tuple[NormalizedDividendCoverage, ...] | None = None,
    adjustments: tuple[ShareBasisAdjustment, ...] | None = None,
    current_price: NormalizedPrice | None = None,
    valuation_date: date = VALUATION_DATE,
) -> DividendResearchInput:
    return DividendResearchInput(
        company_id="company-1",
        symbol=symbol,
        valuation_date=valuation_date,
        as_of=AS_OF,
        payments=(payment(),) if payments is None else payments,
        coverage=(coverage(),) if coverages is None else coverages,
        adjustments=(adjustment(),) if adjustments is None else adjustments,
        price=price() if current_price is None else current_price,
    )


def test_ttm_yield_sums_unique_paid_gross_ordinary_installments_on_current_basis() -> None:
    first = payment(installment="one", amount="50")
    second = payment(installment="two", amount="25", payment_date=date(2026, 8, 1))
    result = calculate_dividend_research(
        [
            source(
                payments=(first, first, second),
                adjustments=(adjustment("one", factor="2"), adjustment("two", factor="2")),
            )
        ]
    )[0]

    assert result.trailing_ordinary_yield.value == pytest.approx(0.15)
    assert [fact.payment.installment_id for fact in result.payments] == ["one", "two"]
    assert result.payments[0].adjusted_gross_dps == Decimal("100.000000")
    assert result.payments[0].adjustment is not None
    assert result.payments[0].adjustment.evidence_ref == "adjustment-one"
    assert result.payments[0].adjustment.dps_multiplier == Decimal("2")
    assert "fixture-source" in result.trailing_ordinary_yield.evidence_refs


def test_ttm_window_is_open_at_calendar_year_boundary_and_closed_at_valuation() -> None:
    in_window = payment(installment="start-inclusive", payment_date=LOWER_BOUND + timedelta(days=1))
    excluded_lower = payment(installment="lower-exclusive", payment_date=LOWER_BOUND)
    included_upper = payment(installment="upper-inclusive", payment_date=VALUATION_DATE)
    result = calculate_dividend_research(
        [
            source(
                payments=(in_window, excluded_lower, included_upper),
                adjustments=tuple(adjustment(item.installment_id) for item in (in_window, excluded_lower, included_upper)),
            )
        ]
    )[0]

    assert result.trailing_ordinary_yield.value == pytest.approx(0.1)


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (payment(installment="declared", status="declared"), None),
        (payment(installment="exceptional", kind="exceptional"), 0.0),
        (payment(installment="unclassified", kind="unclassified"), None),
        (payment(installment="net", semantics="net"), None),
    ],
)
def test_nonordinary_or_unpaid_items_remain_facts_but_do_not_enter_yield(
    record: NormalizedDividend, expected: float | None
) -> None:
    result = calculate_dividend_research(
        [source(payments=(record,), adjustments=(adjustment(record.installment_id),))]
    )[0]
    assert result.trailing_ordinary_yield.value == expected
    assert len(result.payments) == 1
    assert result.payments[0].payment is record


@pytest.mark.parametrize(
    ("invalid_source", "expected_status"),
    [
        (source(coverages=(coverage(status="partial"),)), "missing_inputs"),
        (source(coverages=(coverage(start=date(2025, 9, 22)),)), "missing_inputs"),
        (source(adjustments=(adjustment(verified=False),)), "unsupported_basis"),
        (source(adjustments=(adjustment(target="different-price-basis"),)), "unsupported_basis"),
        (source(current_price=price(basis="estimated")), "missing_inputs"),
        (source(current_price=price(session_date=date(2026, 9, 22))), "missing_inputs"),
        (source(coverages=(coverage(outcome="confirmed_no_payment"),)), "missing_inputs"),
    ],
)
def test_incomplete_coverage_or_incompatible_basis_keeps_yield_unknown(
    invalid_source: DividendResearchInput, expected_status: str,
) -> None:
    result = calculate_dividend_research([invalid_source])[0]
    assert result.trailing_ordinary_yield.value is None
    assert result.trailing_ordinary_yield.status == expected_status
    assert result.coverage is not None


def test_unknown_coverage_is_preserved_as_unknown_not_zero() -> None:
    result = calculate_dividend_research([source(coverages=())])[0]
    assert result.coverage is None
    assert result.trailing_ordinary_yield.value is None
    assert result.trailing_ordinary_yield.reason_codes == ("ttm_coverage_incomplete",)


def test_undated_unknown_payment_prevents_supported_ttm_yield() -> None:
    record = payment(installment="unknown-undated", status="unknown", payment_date=None)
    result = calculate_dividend_research(
        [
            source(
                payments=(record,),
                coverages=(coverage(outcome="payments_recorded"),),
                adjustments=(adjustment(record.installment_id),),
            )
        ]
    )[0]

    assert result.trailing_ordinary_yield.status == "missing_inputs"
    assert result.trailing_ordinary_yield.value is None
    assert result.trailing_ordinary_yield.reason_codes == ("payment_semantics_unknown",)


def test_complete_confirmed_no_payment_window_produces_a_zero_yield_fact() -> None:
    result = calculate_dividend_research(
        [source(payments=(), coverages=(coverage(outcome="confirmed_no_payment"),), adjustments=())]
    )[0]
    assert result.trailing_ordinary_yield.status == "assessable"
    assert result.trailing_ordinary_yield.value == 0.0


def test_exceptional_payments_are_excluded_but_support_zero_ordinary_yield() -> None:
    exceptional = payment(installment="exceptional-only", kind="exceptional")
    result = calculate_dividend_research(
        [
            source(
                payments=(exceptional,),
                coverages=(coverage(outcome="payments_recorded"),),
                adjustments=(),
            )
        ]
    )[0]
    assert result.trailing_ordinary_yield.status == "assessable"
    assert result.trailing_ordinary_yield.value == 0.0


def test_unknown_future_revision_is_not_used_for_historical_point_in_time_facts() -> None:
    future = datetime(2026, 9, 24, tzinfo=timezone.utc)
    old = payment(known_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
    corrected = payment(known_at=future, revision_number=2, amount="900")
    old_coverage = coverage(known_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
    future_coverage = coverage(known_at=future, revision_number=2, status="partial")
    result = calculate_dividend_research(
        [
            source(
                payments=(old, corrected),
                coverages=(old_coverage, future_coverage),
                adjustments=(adjustment(known_at=future),),
            )
        ]
    )[0]

    assert result.payments[0].payment is old
    assert result.payments[0].adjusted_gross_dps is None
    assert result.coverage is old_coverage
    assert result.trailing_ordinary_yield.value is None


def test_dividend_and_balanced_scores_are_always_explicitly_deferred() -> None:
    result = calculate_dividend_research([source()])[0]
    assert (result.dividend.overall_score.status, result.dividend.overall_score.value) == (
        "deferred_scope",
        None,
    )
    assert result.dividend.overall_score.reason_codes == ("dividend_scoring_deferred_v1",)
    assert (result.balanced.overall_score.status, result.balanced.overall_score.value) == (
        "deferred_scope",
        None,
    )
    assert result.balanced.overall_score.reason_codes == ("balanced_scoring_deferred_v1",)
    assert not hasattr(result, "recommendation")
    assert not hasattr(result, "confidence")


def test_results_are_symbol_ordered_and_duplicate_symbol_is_rejected() -> None:
    results = calculate_dividend_research([source(symbol="ZZZ"), source(symbol="ABC")])
    assert [item.symbol for item in results] == ["ABC", "ZZZ"]
    with pytest.raises(DividendResearchError, match="duplicate issuer symbol"):
        calculate_dividend_research([source(), source()])


@pytest.mark.parametrize(
    ("valuation", "expected_lower"),
    [
        (date(2024, 2, 29), date(2023, 2, 28)),
        (date(2024, 3, 31), date(2023, 3, 31)),
        (date(2024, 1, 31), date(2023, 1, 31)),
    ],
)
def test_calendar_month_subtraction(valuation: date, expected_lower: date) -> None:
    interval_coverage = coverage(
        start=expected_lower,
        end=valuation,
        outcome="confirmed_no_payment",
    )
    result = calculate_dividend_research(
        [
            source(
                valuation_date=valuation,
                payments=(),
                coverages=(interval_coverage,),
                adjustments=(),
                current_price=price(session_date=valuation),
            )
        ]
    )[0]
    assert result.trailing_ordinary_yield.value == 0.0
