"""Composition, guard precedence, and ranking tests for Growth advice."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.analysis.growth_advice import (
    GuardEvidence,
    GrowthAdviceInput,
    compose_growth_advice,
    load_growth_rules,
    rank_growth_catalog,
)
from backend.analysis.growth_core import GrowthCoreResult, TermResult
from backend.analysis.growth_risk import (
    GrowthRiskResult,
    GrowthRiskSnapshot,
    NonFinancialBalanceSheet,
)
from backend.contracts.analysis import NormalizedPrice, NormalizedSession, Provenance, Revision
from backend.contracts.scalars import NonNegativeMoney

AS_OF = datetime(2026, 9, 25, 16, tzinfo=timezone.utc)


def _term(points: str | None, *, reason: str = "missing") -> TermResult:
    return TermResult(
        "unavailable" if points is None else "assessable",
        None if points is None else Decimal(points),
        ("financial-source",),
        (reason,) if points is None else (),
    )


def _sessions(current_index: int = 25, oldest_age: int = 6) -> tuple[NormalizedSession, ...]:
    items = []
    for age in range(oldest_age + 1):
        session_date = date.fromordinal(AS_OF.date().toordinal() - age)
        provenance = Provenance(
            source_id=f"session-{age}", collected_at=AS_OF,
            original_unit="session", basis="actual",
        )
        items.append(NormalizedSession(
            calendar_version="calendar-v1", session_id=f"session-{age}",
            session_date=session_date, session_index=current_index - age,
            exchange_timezone="Africa/Abidjan", status="trading",
            official_close_at=AS_OF, source_evidence=(provenance,),
            revision=Revision(revision=0, known_at=AS_OF, provenance=provenance),
        ))
    return tuple(items)


def _price(
    *, symbol: str = "TEST", age: int = 0,
    trade_status: str = "traded", close_basis: str = "raw",
) -> NormalizedPrice:
    session_date = date.fromordinal(AS_OF.date().toordinal() - age)
    provenance = Provenance(
        source_id="price-source", collected_at=AS_OF,
        original_unit="XOF/share", basis="actual",
    )
    return NormalizedPrice(
        symbol=symbol, session_date=session_date,
        close=NonNegativeMoney(amount="100", currency="XOF"),
        close_basis=close_basis, trade_status=trade_status, basis="actual",
        original_source_date=session_date, price_basis_ref="ordinary-price-basis",
        validated_available_at=AS_OF, suspension_status="not_suspended",
        revision=Revision(revision=0, known_at=AS_OF, provenance=provenance),
    )


def _input(
    symbol: str = "TEST",
    points: tuple[str | None, str | None, str | None, str | None, str | None] = (
        "12", "18", "25", "20", "25",
    ),
    *,
    report_end: date = date(2025, 12, 31),
    report_known: datetime | None = AS_OF,
    earnings: Decimal | None = Decimal("10"),
    equity: Decimal | None = Decimal("100"),
    price_age: int | None = 0,
    risk_event: GuardEvidence | None = None,
) -> GrowthAdviceInput:
    company_id = f"company-{symbol}"
    core = GrowthCoreResult(
        _term(points[0]), _term(points[1]), _term(None), _term(points[2])
    )
    balance = NonFinancialBalanceSheet(
        company_id, report_end, "consolidated", "basis-v1",
        Decimal(0), Decimal(0), Decimal(100), Decimal(50), ("balance-source",),
    )
    snapshot = GrowthRiskSnapshot(
        company_id=company_id, category="non_financial", jurisdiction="BRVM",
        period_end=report_end, report_scope="consolidated", basis_id="basis-v1",
        ordinary_owner_earnings=earnings, equity=equity, market_capitalization=Decimal(100),
        capitalization_basis_id="basis-v1", evidence_refs=("financial-source",),
        regulatory_constraints_complete=False, balance_sheet=balance,
    )
    risk = GrowthRiskResult(_term(points[3]), _term(points[4]))
    return GrowthAdviceInput(
        company_id, symbol, core, risk, snapshot, AS_OF, report_known, True,
        () if price_age is None else (_price(symbol=symbol, age=price_age),),
        _sessions(oldest_age=max(6, price_age or 0)),
        risk_event or GuardEvidence("known_risk_flags", "pass"),
    )


def _guard(result, code: str):
    return next(guard for guard in result.guards if guard.code == code)


def test_growth_dimensions_sum_to_100_and_69_96_displays_70_but_stays_watchlist() -> None:
    assert sum(maximum for _, maximum in load_growth_rules().dimension_points) == Decimal(100)
    result = compose_growth_advice(_input(points=("0", "0", "25", "20", "24.96")))
    assert result.overall_score == Decimal("69.96")
    assert result.display_score == Decimal("70.0")
    assert result.advisory_state == "watchlist"


@pytest.mark.parametrize(("score", "expected"), [("70", "candidate"), ("50", "watchlist")])
def test_exact_advice_score_boundaries(score: str, expected: str) -> None:
    result = compose_growth_advice(_input(points=("0", "0", "25", "20", str(Decimal(score) - 45))))
    assert result.overall_score == Decimal(score)
    assert result.advisory_state == expected


def test_report_freshness_includes_exact_18_month_boundary() -> None:
    passing = compose_growth_advice(_input(report_end=date(2025, 3, 25)))
    stale = compose_growth_advice(_input(report_end=date(2025, 3, 24)))
    assert _guard(passing, "financial_report_freshness").status == "pass"
    assert _guard(stale, "financial_report_freshness").status == "fail"


@pytest.mark.parametrize(("age", "expected"), [(5, "pass"), (6, "fail")])
def test_actual_price_freshness_includes_five_session_boundary(age: int, expected: str) -> None:
    result = compose_growth_advice(_input(price_age=age))
    assert _guard(result, "actual_traded_price_freshness").status == expected


def test_adjusted_close_is_not_accepted_as_an_actual_traded_close() -> None:
    item = _input()
    result = compose_growth_advice(GrowthAdviceInput(
        item.company_id, item.symbol, item.core, item.risk, item.risk_snapshot,
        item.analysis_time, item.latest_report_known_at, item.latest_report_published,
        (_price(symbol=item.symbol, close_basis="adjusted"),), item.sessions, item.event_monitoring,
    ))
    assert _guard(result, "actual_traded_price_freshness").status == "fail"


def test_confirmed_suspension_requires_review() -> None:
    item = _input()
    sessions = list(item.sessions)
    sessions[0] = sessions[0].model_copy(update={"status": "suspended"})
    result = compose_growth_advice(GrowthAdviceInput(
        item.company_id, item.symbol, item.core, item.risk, item.risk_snapshot,
        item.analysis_time, item.latest_report_known_at, item.latest_report_published,
        item.prices, tuple(sessions), item.event_monitoring,
    ))
    assert _guard(result, "suspension_status").status == "fail"
    assert result.advisory_state == "review_required"


def test_known_failed_guard_wins_over_unknown_required_guards() -> None:
    result = compose_growth_advice(_input(
        earnings=Decimal("-1"), report_known=None, price_age=None,
        risk_event=GuardEvidence("known_risk_flags", "unknown"),
    ))
    assert result.advisory_state == "review_required"
    assert "positive_latest_ordinary_owner_earnings" in result.reasons


def test_unknown_required_guard_blocks_advice_without_a_known_failure() -> None:
    result = compose_growth_advice(_input(report_known=None))
    assert result.advisory_state == "insufficient_evidence"


def test_partial_metrics_are_retained_but_never_ranked_as_full_scores() -> None:
    partial = compose_growth_advice(_input(points=(None, "18", "25", "20", "25")))
    assert partial.overall_score is None
    assert partial.partial_points == Decimal("88")
    assert partial.display_score is None
    rankings = rank_growth_catalog((
        _input(symbol="B"), _input(symbol="A"),
        _input(symbol="C", points=(None, "18", "25", "20", "25")),
    ))
    assert [item.symbol for item in rankings.ranked] == ["A", "B"]
    assert [item.symbol for item in rankings.insufficient_evidence] == ["C"]
    assert [item.symbol for item in rankings.items] == ["A", "B", "C"]
