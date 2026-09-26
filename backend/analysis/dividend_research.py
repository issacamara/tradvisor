"""Point-in-time dividend facts and verified trailing ordinary yield."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable, Hashable, Iterable, Literal, Protocol, TypeVar

from backend.contracts.analysis import (
    AnalyticalMetric,
    LongTermObjectiveState,
    NormalizedDividend,
    NormalizedDividendCoverage,
    NormalizedPrice,
    Revision,
)

DIVIDEND_SCORE_REASON = "dividend_scoring_deferred_v1"
BALANCED_SCORE_REASON = "balanced_scoring_deferred_v1"


class DividendResearchError(ValueError):
    """Raised when source revisions cannot form an unambiguous research view."""


class Revisioned(Protocol):
    revision: Revision


R = TypeVar("R", bound=Revisioned)
Objective = Literal["dividend", "balanced"]
MetricStatus = Literal["assessable", "missing_inputs", "unsupported_basis"]


@dataclass(frozen=True)
class ShareBasisAdjustment:
    """Verified multiplier converting one payment's DPS to a price share basis."""

    installment_id: str
    source_share_basis_ref: str
    target_share_basis_ref: str
    dps_multiplier: Decimal
    known_at: datetime
    revision: int
    evidence_ref: str
    verified: bool


@dataclass(frozen=True)
class DividendResearchInput:
    """Fixture-backed inputs for one issuer at a point-in-time valuation date."""

    company_id: str
    symbol: str
    valuation_date: date
    as_of: datetime
    payments: tuple[NormalizedDividend, ...]
    coverage: tuple[NormalizedDividendCoverage, ...]
    adjustments: tuple[ShareBasisAdjustment, ...]
    price: NormalizedPrice | None


@dataclass(frozen=True)
class DividendPaymentFact:
    """A retained source payment with optional basis-adjusted gross DPS."""

    payment: NormalizedDividend
    adjusted_gross_dps: Decimal | None
    adjustment: ShareBasisAdjustment | None


@dataclass(frozen=True)
class DividendResearchFact:
    """Symbol-ordered facts only; deferred scores carry no recommendation state."""

    company_id: str
    symbol: str
    valuation_date: date
    coverage: NormalizedDividendCoverage | None
    payments: tuple[DividendPaymentFact, ...]
    trailing_ordinary_yield: AnalyticalMetric[float]
    dividend: LongTermObjectiveState
    balanced: LongTermObjectiveState


def _require_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise DividendResearchError(f"{field} must be an explicit UTC timestamp")
    return value.astimezone(timezone.utc)


def _subtract_calendar_year(value: date) -> date:
    year = value.year - 1
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return date(year, value.month, day)


def _latest_revisions(
    records: Iterable[R], *, as_of: datetime, key: Callable[[R], Hashable]
) -> dict[Hashable, R]:
    selected: dict[Hashable, R] = {}
    for item in records:
        record_key = key(item)
        known_at = _require_utc(item.revision.known_at, "revision.known_at")
        if known_at > as_of:
            continue
        previous = selected.get(record_key)
        if previous is None or (known_at, item.revision.revision) > (
            previous.revision.known_at,
            previous.revision.revision,
        ):
            selected[record_key] = item
        elif (known_at, item.revision.revision) == (
            previous.revision.known_at,
            previous.revision.revision,
        ) and item != previous:
            raise DividendResearchError(f"ambiguous revision for {record_key!r}")
    return selected


def _latest_adjustments(
    records: Iterable[ShareBasisAdjustment], *, as_of: datetime
) -> dict[str, ShareBasisAdjustment]:
    selected: dict[str, ShareBasisAdjustment] = {}
    for item in records:
        known_at = _require_utc(item.known_at, "adjustment.known_at")
        if known_at > as_of:
            continue
        if (
            not item.dps_multiplier.is_finite()
            or item.dps_multiplier <= 0
            or item.revision < 0
            or not item.source_share_basis_ref
            or not item.target_share_basis_ref
            or not item.evidence_ref
        ):
            raise DividendResearchError("share adjustment must have a positive factor and revision")
        previous = selected.get(item.installment_id)
        if previous is None or (known_at, item.revision) > (previous.known_at, previous.revision):
            selected[item.installment_id] = item
        elif (known_at, item.revision) == (previous.known_at, previous.revision) and item != previous:
            raise DividendResearchError(f"ambiguous share adjustment for {item.installment_id!r}")
    return selected


def _deferred_state(objective: Objective, reason: str) -> LongTermObjectiveState:
    return LongTermObjectiveState(
        objective=objective,
        overall_score=AnalyticalMetric[float](
            status="deferred_scope", value=None, unit="points", reason_codes=(reason,)
        ),
    )


def _yield_metric(
    *,
    status: MetricStatus,
    reason: str,
    evidence_refs: tuple[str, ...] = (),
    value: float | None = None,
    valuation_date: date,
) -> AnalyticalMetric[float]:
    return AnalyticalMetric[float](
        status=status,
        value=value,
        unit="ratio",
        reason_codes=() if status == "assessable" else (reason,),
        evidence_refs=evidence_refs,
        effective_date=valuation_date if status == "assessable" else None,
        basis="actual" if status == "assessable" else None,
    )


def calculate_dividend_research(
    inputs: Iterable[DividendResearchInput],
) -> tuple[DividendResearchFact, ...]:
    """Publish symbol-ordered payment facts and only fully supported TTM yield."""

    facts: list[DividendResearchFact] = []
    seen_symbols: set[str] = set()
    for source in inputs:
        as_of = _require_utc(source.as_of, "as_of")
        if source.symbol in seen_symbols:
            raise DividendResearchError(f"duplicate issuer symbol {source.symbol!r}")
        seen_symbols.add(source.symbol)

        payments = _latest_revisions(
            (item for item in source.payments if item.company_id == source.company_id),
            as_of=as_of,
            key=lambda item: (item.company_id, item.installment_id),
        )
        coverage_records = _latest_revisions(
            (item for item in source.coverage if item.company_id == source.company_id),
            as_of=as_of,
            key=lambda item: (item.company_id, item.covered_interval_start, item.covered_interval_end, item.coverage_basis),
        )
        coverages = sorted(
            coverage_records.values(),
            key=lambda item: (item.covered_interval_start, item.covered_interval_end),
        )
        visible_coverage = next(
            (item for item in reversed(coverages) if item.covered_interval_end <= source.valuation_date),
            None,
        )
        adjustments = _latest_adjustments(source.adjustments, as_of=as_of)
        lower_bound = _subtract_calendar_year(source.valuation_date)

        payment_facts: list[DividendPaymentFact] = []
        ttm_payments: list[tuple[NormalizedDividend, Decimal, ShareBasisAdjustment]] = []
        for payment in sorted(
            payments.values(),
            key=lambda item: (item.payment_date or date.min, item.dividend_id, item.installment_id),
        ):
            adjustment = adjustments.get(payment.installment_id)
            adjusted_dps: Decimal | None = None
            if (
                payment.payment_status == "paid"
                and payment.per_share_semantics == "gross"
                and payment.revision.provenance.basis == "actual"
                and payment.gross_amount_per_share is not None
                and adjustment is not None
                and adjustment.verified
                and adjustment.source_share_basis_ref
                and adjustment.target_share_basis_ref
            ):
                adjusted_dps = (
                    Decimal(payment.gross_amount_per_share.amount) * adjustment.dps_multiplier
                )
            payment_facts.append(DividendPaymentFact(payment, adjusted_dps, adjustment))

            if (
                payment.dividend_type == "ordinary"
                and payment.payment_status == "paid"
                and payment.payment_date is not None
                and lower_bound < payment.payment_date <= source.valuation_date
                and adjusted_dps is not None
            ):
                assert adjustment is not None
                ttm_payments.append((payment, adjusted_dps, adjustment))

        metric = _yield_metric(
            status="missing_inputs",
            reason="ttm_coverage_incomplete",
            valuation_date=source.valuation_date,
        )
        expected_coverage = next(
            (
                item
                for item in coverages
                if item.coverage_basis == "trailing_12_months"
                and item.covered_interval_start == lower_bound
                and item.covered_interval_end == source.valuation_date
                and item.coverage_status == "complete"
                and item.revision.provenance.basis == "actual"
            ),
            None,
        )
        price = source.price
        if expected_coverage is not None:
            if price is None:
                metric = _yield_metric(
                    status="missing_inputs",
                    reason="no_current_trade",
                    valuation_date=source.valuation_date,
                )
            else:
                price_known_at = price.revision.known_at
                price_available_at = price.validated_available_at
                price_provenance_actual = price.revision.provenance.basis == "actual"
                price_ok = (
                    price.symbol == source.symbol
                    and price.session_date == source.valuation_date
                    and price.trade_status == "traded"
                    and price.basis == "actual"
                    and price.close is not None
                    and price.close.micros > 0
                    and price_available_at is not None
                    and _require_utc(price_known_at, "price.revision.known_at") <= as_of
                    and _require_utc(price_available_at, "price.validated_available_at") <= as_of
                )
                window_payments = [
                    item
                    for item in payments.values()
                    if item.payment_date is not None
                    and lower_bound < item.payment_date <= source.valuation_date
                ]
                undated_unresolved_payments = [
                    item
                    for item in payments.values()
                    if item.payment_date is None
                    and (
                        item.payment_status == "unknown"
                        or item.payment_status == "paid"
                    )
                ]
                window_paid = [item for item in window_payments if item.payment_status == "paid"]
                ordinary_paid = [
                    item for item in window_paid if item.dividend_type == "ordinary"
                ]
                unresolved_payment_semantics = bool(undated_unresolved_payments) or any(
                    item.payment_status == "unknown"
                    or item.payment_status == "paid" and item.dividend_type == "unclassified"
                    for item in window_payments
                )
                coverage_consistent = (
                    expected_coverage.payment_outcome == "confirmed_no_payment"
                    and not window_payments
                    or expected_coverage.payment_outcome == "payments_recorded"
                    and bool(window_paid)
                )
                basis_compatible = (
                    len(ttm_payments) == len(ordinary_paid)
                    and all(
                        adjustment.target_share_basis_ref == price.price_basis_ref
                        for _, _, adjustment in ttm_payments
                    )
                )
                if not price_provenance_actual:
                    metric = _yield_metric(
                        status="unsupported_basis",
                        reason="price_basis_unverified",
                        valuation_date=source.valuation_date,
                    )
                elif not price_ok:
                    metric = _yield_metric(
                        status="missing_inputs",
                        reason="no_current_trade",
                        valuation_date=source.valuation_date,
                    )
                elif unresolved_payment_semantics:
                    metric = _yield_metric(
                        status="missing_inputs",
                        reason="payment_semantics_unknown",
                        valuation_date=source.valuation_date,
                    )
                elif not coverage_consistent:
                    metric = _yield_metric(
                        status="missing_inputs",
                        reason="ttm_coverage_incomplete",
                        valuation_date=source.valuation_date,
                    )
                elif not basis_compatible:
                    metric = _yield_metric(
                        status="unsupported_basis",
                        reason="share_basis_unverified",
                        valuation_date=source.valuation_date,
                    )
                else:
                    assert price.close is not None
                    adjustment_refs = tuple(
                        sorted({item[2].evidence_ref for item in ttm_payments})
                    )
                    evidence_refs = tuple(
                        sorted(
                            {
                                *(item.dividend_id for item in window_paid),
                                *(item.revision.provenance.source_id for item in window_paid),
                                expected_coverage.revision.provenance.source_id,
                                price.revision.provenance.source_id,
                                *adjustment_refs,
                            }
                        )
                    )
                    total_dps = sum((amount for _, amount, _ in ttm_payments), Decimal(0))
                    metric = _yield_metric(
                        status="assessable",
                        reason="",
                        value=float(total_dps / Decimal(price.close.amount)),
                        evidence_refs=evidence_refs,
                        valuation_date=source.valuation_date,
                    )

        facts.append(
            DividendResearchFact(
                company_id=source.company_id,
                symbol=source.symbol,
                valuation_date=source.valuation_date,
                coverage=visible_coverage,
                payments=tuple(payment_facts),
                trailing_ordinary_yield=metric,
                dividend=_deferred_state("dividend", DIVIDEND_SCORE_REASON),
                balanced=_deferred_state("balanced", BALANCED_SCORE_REASON),
            )
        )

    return tuple(sorted(facts, key=lambda item: item.symbol))
