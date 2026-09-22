"""Contract tests for normalized analytical inputs and immutable publications."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from backend.contracts.analysis import (
    AnalyticalBatch,
    AnalyticalMetric,
    LongTermObjectiveState,
    LongTermResult,
    NormalizedCapital,
    NormalizedDividend,
    NormalizedPrice,
    NormalizedSession,
    Provenance,
    Revision,
)
from backend.contracts.scalars import NonNegativeMoney, Score, SignedMoney


@pytest.fixture
def provenance() -> Provenance:
    return Provenance(
        source_id="brvm-source-1",
        collected_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        published_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        original_unit="XOF",
        basis="actual",
    )


@pytest.fixture
def revision(provenance: Provenance) -> Revision:
    return Revision(revision=1, known_at=datetime(2026, 9, 22, tzinfo=timezone.utc), provenance=provenance)


@pytest.fixture
def company(revision: Revision) -> object:
    from backend.contracts.analysis import NormalizedCompany

    return NormalizedCompany(
        company_id="company-nsi", symbol="NSI", name="Nestle CI", financial_category="non_financial", revision=revision
    )


@pytest.fixture
def session(revision: Revision) -> object:
    return NormalizedSession(
        calendar_version="calendar-2026-1",
        session_id="brvm-2026-09-22",
        session_date=date(2026, 9, 22),
        session_index=100,
        exchange_timezone="Africa/Abidjan",
        status="trading",
        official_close_at=datetime(2026, 9, 22, 15, 1, tzinfo=timezone.utc),
        source_evidence=(revision.provenance,),
        revision=revision,
    )


@pytest.fixture
def price(revision: Revision) -> object:
    return NormalizedPrice(
        symbol="NSI", session_date=date(2026, 9, 22), close=_money("1000"),
        high=_money("1050"), low=_money("950"), volume=100,
        trade_status="traded", basis="actual", original_source_date=date(2026, 9, 22),
        price_basis_ref="price-basis-1", validated_available_at=datetime(2026, 9, 22, 15, 2, tzinfo=timezone.utc),
        actual_xof_turnover=_money("100000"), liquidity_basis="actual", suspension_status="not_suspended", revision=revision,
    )


@pytest.fixture
def financial(revision: Revision) -> object:
    from backend.contracts.analysis import NormalizedFinancial

    return NormalizedFinancial(
        company_id="company-nsi", fiscal_period_end=date(2025, 12, 31), report_scope="standalone", currency="XOF",
        fiscal_period_start=date(2025, 1, 1), original_scale="units", revenue=_money("1000000"),
        opening_equity=SignedMoney(amount="900", currency="XOF"), publication_status="published", revision=revision,
    )


def test_financial_records_preserve_observed_losses_and_nonpositive_equity(revision: Revision) -> None:
    from backend.contracts.analysis import NormalizedFinancial

    financial = NormalizedFinancial(
        company_id="company-nsi", fiscal_period_end=date(2025, 12, 31), report_scope="standalone", currency="XOF",
        fiscal_period_start=date(2025, 1, 1), original_scale="units",
        ordinary_owner_earnings=SignedMoney(amount="-100", currency="XOF"),
        equity=SignedMoney(amount="-50", currency="XOF"), publication_status="published", revision=revision,
    )
    assert financial.ordinary_owner_earnings is not None
    assert financial.ordinary_owner_earnings.amount == "-100.000000"


@pytest.fixture
def capital(revision: Revision) -> object:
    return NormalizedCapital(
        company_id="company-nsi", effective_date=date(2026, 9, 22), ordinary_shares=1000,
        share_basis="ordinary_outstanding", capitalization_basis="matched_ordinary_claim", revision=revision,
    )


@pytest.fixture
def dividend(revision: Revision) -> object:
    return NormalizedDividend(
        dividend_id="dividend-nsi-2025", company_id="company-nsi", payment_date=date(2026, 5, 1),
        installment_id="installment-nsi-2025-1", fiscal_period_end=date(2025, 12, 31), gross_amount_per_share=_money("50"),
        net_amount_per_share=_money("45"), gross_total_amount=_money("50000"), net_total_amount=_money("45000"),
        per_share_semantics="gross", total_semantics="gross", payment_status="paid",
        dividend_type="ordinary", coverage_status="partial", covered_interval_start=date(2025, 1, 1),
        covered_interval_end=date(2025, 12, 31), coverage_basis="fiscal_year", revision=revision,
    )


@pytest.fixture
def rating(revision: Revision) -> object:
    from backend.contracts.analysis import NormalizedRating

    return NormalizedRating(
        rating_id="rating-nsi-2026", company_id="company-nsi", agency="Agency", scale="local", subject="issuer",
        label="A", effective_date=date(2026, 1, 1), collected_at=datetime(2026, 9, 22, tzinfo=timezone.utc), revision=revision,
    )


@pytest.fixture
def assessable_growth() -> AnalyticalMetric[Score]:
    return AnalyticalMetric[Score](
        status="assessable", value=75.0, unit="points", evidence_refs=("growth-evidence-1",),
        effective_date=date(2026, 9, 22), basis="actual",
    )


def _money(amount: str) -> NonNegativeMoney:
    return NonNegativeMoney(amount=amount, currency="XOF")


def test_every_normalized_entity_fixture_is_constructed(
    company: object,
    session: object,
    price: object,
    financial: object,
    capital: object,
    dividend: object,
    rating: object,
) -> None:
    assert all((company, session, price, financial, capital, dividend, rating))


def test_provenance_requires_utc_and_records_actual_estimated_and_modeled_basis() -> None:
    for basis in ("actual", "estimated", "modeled"):
        assert Provenance(
            source_id="source-1",
            collected_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
            basis=basis,
        ).basis == basis

    with pytest.raises(ValidationError):
        Provenance(source_id="source-1", collected_at=datetime(2026, 9, 22), basis="actual")


def test_null_status_reason_combinations_are_explicit() -> None:
    unavailable = AnalyticalMetric[Score](
        status="missing_inputs",
        value=None,
        unit="points",
        reason_codes=("financial_inputs_missing",),
    )
    assert unavailable.value is None

    with pytest.raises(ValidationError):
        AnalyticalMetric[Score](status="missing_inputs", value=None, unit="points")
    with pytest.raises(ValidationError):
        AnalyticalMetric[Score](
            status="assessable", value=None, unit="points"
        )
    with pytest.raises(ValidationError):
        AnalyticalMetric[Score](
            status="warming_up", value=50.0, unit="points", reason_codes=("history_incomplete",)
        )


def test_normalized_entities_retain_revision_and_require_known_non_trade_evidence(
    revision: Revision,
) -> None:
    assert getattr(revision, "revision") == 1
    with pytest.raises(ValidationError):
        NormalizedSession(
            calendar_version="calendar-1", session_id="session-1", session_date=date(2026, 9, 22),
            session_index=1, exchange_timezone="Africa/Abidjan", status="holiday", official_close_at=None,
            source_evidence=(revision.provenance,), revision=revision,
        )
    with pytest.raises(ValidationError):
        NormalizedPrice(
            symbol="NSI", session_date=date(2026, 9, 22), close=None, trade_status="unknown", basis="actual",
            original_source_date=date(2026, 9, 22), price_basis_ref="basis-1", validated_available_at=None,
            suspension_status="not_suspended", revision=revision,
        )
    with pytest.raises(ValidationError):
        NormalizedCapital(
            company_id="company-nsi", effective_date=date(2026, 9, 22), ordinary_shares=100,
            share_basis="free_float", capitalization_basis="unmatched", revision=revision,
        )
    with pytest.raises(ValidationError):
        NormalizedDividend(
            dividend_id="dividend-1", company_id="company-nsi", installment_id="installment-1", payment_date=None,
            gross_amount_per_share=None, per_share_semantics="gross", total_semantics="unknown", payment_status="paid",
            dividend_type="ordinary", coverage_status="unknown", covered_interval_start=None, covered_interval_end=None,
            coverage_basis="unknown", revision=revision,
        )


def test_session_calendar_identity_and_price_execution_provenance_boundaries(
    revision: Revision,
) -> None:
    first = NormalizedSession(
        calendar_version="calendar-1", session_id="session-1", session_date=date(2026, 9, 21), session_index=99,
        exchange_timezone="Africa/Abidjan", status="trading", official_close_at=datetime(2026, 9, 21, 15, 1, tzinfo=timezone.utc),
        source_evidence=(revision.provenance,), revision=revision,
    )
    second = NormalizedSession(
        calendar_version="calendar-1", session_id="session-2", session_date=date(2026, 9, 22), session_index=100,
        exchange_timezone="Africa/Abidjan", status="trading", official_close_at=datetime(2026, 9, 22, 15, 1, tzinfo=timezone.utc),
        source_evidence=(revision.provenance,), revision=revision,
    )
    assert first.session_index < second.session_index

    with pytest.raises(ValidationError):
        NormalizedSession(
            calendar_version="calendar-1", session_id="session-3", session_date=date(2026, 9, 23), session_index=101,
            exchange_timezone="Africa/Abidjan", status="trading", official_close_at=None,
            source_evidence=(revision.provenance,), revision=revision,
        )
    with pytest.raises(ValidationError):
        NormalizedPrice(
            symbol="NSI", session_date=date(2026, 9, 22), close=_money("1000"), trade_status="traded", basis="actual",
            original_source_date=date(2026, 9, 22), price_basis_ref="basis-1", validated_available_at=None,
            suspension_status="not_suspended", revision=revision,
        )
    with pytest.raises(ValidationError):
        NormalizedPrice(
            symbol="NSI", session_date=date(2026, 9, 22), close=_money("1000"), trade_status="traded", basis="actual",
            original_source_date=date(2026, 9, 22), price_basis_ref="basis-1",
            validated_available_at=datetime(2026, 9, 22, 15, 2, tzinfo=timezone.utc), actual_xof_turnover=_money("1"),
            liquidity_basis="estimated", suspension_status="not_suspended", revision=revision,
        )


def test_dividend_and_capital_preserve_matching_basis_and_payment_semantics(
    capital: object, dividend: object, financial: object, price: object
) -> None:
    assert getattr(capital, "capitalization_basis") == "matched_ordinary_claim"
    assert getattr(dividend, "installment_id") == "installment-nsi-2025-1"
    assert getattr(dividend, "gross_amount_per_share").amount == "50.000000"
    assert getattr(dividend, "net_total_amount").amount == "45000.000000"
    assert getattr(financial, "opening_equity").amount == "900.000000"
    assert getattr(financial, "original_scale") == "units"
    assert getattr(price, "actual_xof_turnover").amount == "100000.000000"
    assert getattr(price, "validated_available_at") == datetime(2026, 9, 22, 15, 2, tzinfo=timezone.utc)


def test_suspension_and_unknown_price_states_require_source_evidence(revision: Revision) -> None:
    with pytest.raises(ValidationError):
        NormalizedPrice(
            symbol="NSI", session_date=date(2026, 9, 22), close=None, trade_status="unknown", basis="actual",
            original_source_date=date(2026, 9, 22), price_basis_ref="basis-1", validated_available_at=None,
            suspension_status="suspended", reason_codes=("suspension_reported",), revision=revision,
        )
    suspended = NormalizedPrice(
        symbol="NSI", session_date=date(2026, 9, 22), close=None, trade_status="unknown", basis="actual",
        original_source_date=date(2026, 9, 22), price_basis_ref="basis-1", validated_available_at=None,
        suspension_status="suspended", suspension_evidence=(revision.provenance,), reason_codes=("suspension_reported",),
        revision=revision,
    )
    assert suspended.suspension_evidence[0].source_id == "brvm-source-1"


def test_long_term_results_keep_deferred_scores_distinct_from_missing_growth(
    revision: Revision, assessable_growth: AnalyticalMetric[Score]
) -> None:
    deferred_dividend = AnalyticalMetric[Score](
        status="deferred_scope",
        value=None,
        unit="points",
        reason_codes=("dividend_scoring_deferred_v1",),
    )
    deferred_balanced = AnalyticalMetric[Score](
        status="deferred_scope",
        value=None,
        unit="points",
        reason_codes=("balanced_scoring_deferred_v1",),
    )
    result = LongTermResult(
        company_id="company-nsi",
        growth=LongTermObjectiveState(objective="growth", overall_score=assessable_growth),
        dividend=LongTermObjectiveState(objective="dividend", overall_score=deferred_dividend),
        balanced=LongTermObjectiveState(objective="balanced", overall_score=deferred_balanced),
        revision=revision,
    )
    assert result.dividend.overall_score.value is None
    assert result.growth.overall_score.status == "assessable"

    missing_growth = assessable_growth.model_copy(
        update={"status": "missing_inputs", "value": None, "reason_codes": ("history_incomplete",)}
    )
    assert LongTermResult(
        company_id="company-nsi",
        growth=LongTermObjectiveState(objective="growth", overall_score=missing_growth),
        dividend=LongTermObjectiveState(objective="dividend", overall_score=deferred_dividend),
        balanced=LongTermObjectiveState(objective="balanced", overall_score=deferred_balanced),
        revision=revision,
    ).growth.overall_score.status == "missing_inputs"

    with pytest.raises(ValidationError):
        LongTermObjectiveState(
            objective="balanced", overall_score=deferred_dividend
        )


def test_result_and_batch_are_immutable_and_keep_distinct_company_results(
    revision: Revision, assessable_growth: AnalyticalMetric[Score]
) -> None:
    deferred_dividend = AnalyticalMetric[Score](
        status="deferred_scope", value=None, unit="points", reason_codes=("dividend_scoring_deferred_v1",)
    )
    deferred_balanced = AnalyticalMetric[Score](
        status="deferred_scope", value=None, unit="points", reason_codes=("balanced_scoring_deferred_v1",)
    )
    result = LongTermResult(
        company_id="company-nsi",
        growth=LongTermObjectiveState(objective="growth", overall_score=assessable_growth),
        dividend=LongTermObjectiveState(objective="dividend", overall_score=deferred_dividend),
        balanced=LongTermObjectiveState(objective="balanced", overall_score=deferred_balanced),
        revision=revision,
    )
    with pytest.raises(ValidationError):
        result.company_id = "company-other"

    with pytest.raises(ValidationError):
        AnalyticalBatch(
            batch_id="batch-1",
            market_session=date(2026, 9, 22),
            published_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
            input_snapshot_id="snapshot-1",
            rule_version="rules-1",
            strategy_id="growth-1",
            revision=1,
            results=(result, result),
        )
