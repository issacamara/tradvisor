"""Contract tests for normalized analytical inputs and immutable publications."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from backend.contracts.analysis import (
    AnalyticalBatch,
    AnalyticalMetric,
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
    return NormalizedSession(session_date=date(2026, 9, 22), status="trading", revision=revision)


@pytest.fixture
def price(revision: Revision) -> object:
    return NormalizedPrice(
        symbol="NSI", session_date=date(2026, 9, 22), close=_money("1000"),
        high=_money("1050"), low=_money("950"), volume=100,
        trade_status="traded", basis="actual", revision=revision,
    )


@pytest.fixture
def financial(revision: Revision) -> object:
    from backend.contracts.analysis import NormalizedFinancial

    return NormalizedFinancial(
        company_id="company-nsi", fiscal_period_end=date(2025, 12, 31), report_scope="standalone", currency="XOF",
        revenue=_money("1000000"), publication_status="published", revision=revision,
    )


def test_financial_records_preserve_observed_losses_and_nonpositive_equity(revision: Revision) -> None:
    from backend.contracts.analysis import NormalizedFinancial

    financial = NormalizedFinancial(
        company_id="company-nsi", fiscal_period_end=date(2025, 12, 31), report_scope="standalone", currency="XOF",
        ordinary_owner_earnings=SignedMoney(amount="-100", currency="XOF"),
        equity=SignedMoney(amount="-50", currency="XOF"), publication_status="published", revision=revision,
    )
    assert financial.ordinary_owner_earnings is not None
    assert financial.ordinary_owner_earnings.amount == "-100.000000"


@pytest.fixture
def capital(revision: Revision) -> object:
    return NormalizedCapital(
        company_id="company-nsi", effective_date=date(2026, 9, 22), ordinary_shares=1000,
        share_basis="ordinary_outstanding", revision=revision,
    )


@pytest.fixture
def dividend(revision: Revision) -> object:
    return NormalizedDividend(
        dividend_id="dividend-nsi-2025", company_id="company-nsi", payment_date=date(2026, 5, 1),
        fiscal_period_end=date(2025, 12, 31), amount_per_share=_money("50"),
        payment_status="paid", dividend_type="ordinary", coverage_status="partial", revision=revision,
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
        NormalizedSession(session_date=date(2026, 9, 22), status="holiday", revision=revision)
    with pytest.raises(ValidationError):
        NormalizedPrice(
            symbol="NSI",
            session_date=date(2026, 9, 22),
            close=None,
            trade_status="unknown",
            basis="actual",
            revision=revision,
        )
    with pytest.raises(ValidationError):
        NormalizedCapital(
            company_id="company-nsi",
            effective_date=date(2026, 9, 22),
            ordinary_shares=100,
            share_basis="free_float",
            revision=revision,
        )
    with pytest.raises(ValidationError):
        NormalizedDividend(
            dividend_id="dividend-1",
            company_id="company-nsi",
            payment_date=None,
            amount_per_share=None,
            payment_status="paid",
            dividend_type="ordinary",
            coverage_status="unknown",
            revision=revision,
        )


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
        growth_score=assessable_growth,
        dividend_score=deferred_dividend,
        balanced_score=deferred_balanced,
        overall_score=assessable_growth,
        revision=revision,
    )
    assert result.dividend_score.value is None
    assert result.growth_score.status == "assessable"

    missing_growth = assessable_growth.model_copy(
        update={"status": "missing_inputs", "value": None, "reason_codes": ("history_incomplete",)}
    )
    assert LongTermResult(
        company_id="company-nsi",
        growth_score=missing_growth,
        dividend_score=deferred_dividend,
        balanced_score=deferred_balanced,
        overall_score=missing_growth,
        revision=revision,
    ).growth_score.status == "missing_inputs"

    with pytest.raises(ValidationError):
        LongTermResult(
            company_id="company-nsi",
            growth_score=assessable_growth,
            dividend_score=deferred_balanced,
            balanced_score=deferred_balanced,
            overall_score=assessable_growth,
            revision=revision,
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
        growth_score=assessable_growth,
        dividend_score=deferred_dividend,
        balanced_score=deferred_balanced,
        overall_score=assessable_growth,
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
