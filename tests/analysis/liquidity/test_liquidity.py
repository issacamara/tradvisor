"""Tests for approved complete-window liquidity rules."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from backend.analysis.inputs import AnalyticalInputSnapshot, SessionInput
from backend.analysis.liquidity import (
    calculate_liquidity,
    evaluate_current_trade_gate,
)
from backend.contracts.analysis import NormalizedPrice, Provenance, Revision
from backend.contracts.scalars import NonNegativeMoney

NOW = datetime(2026, 9, 25, 16, tzinfo=timezone.utc)


def money(amount: str) -> NonNegativeMoney:
    return NonNegativeMoney(amount=amount, currency="XOF")


def price(
    day: int,
    *,
    traded: bool = True,
    turnover: str | None = "5000000",
    close: str | None = "1000",
    volume: int | None = 5000,
    price_basis: str = "raw-v1",
    trade_status: Literal["traded", "confirmed_no_trade", "unknown"] | None = None,
    suspension: Literal["not_suspended", "suspended", "unknown"] = "not_suspended",
) -> NormalizedPrice:
    status = trade_status or ("traded" if traded else "confirmed_no_trade")
    source = Provenance(
        source_id=f"source-{day}", collected_at=NOW, basis="actual"
    )
    return NormalizedPrice(
        symbol="NSI",
        session_date=date(2026, 9, day),
        close=None if close is None else money(close),
        volume=volume,
        trade_status=status,
        basis="actual",
        original_source_date=date(2026, 9, day),
        price_basis_ref=price_basis,
        validated_available_at=NOW if status == "traded" else None,
        actual_xof_turnover=None if turnover is None else money(turnover),
        liquidity_basis="actual" if turnover is not None else None,
        suspension_status=suspension,
        suspension_evidence=(source,) if suspension != "not_suspended" else (),
        reason_codes=() if status == "traded" else ("no_trade_confirmed",),
        revision=Revision(
            revision=1, known_at=NOW, provenance=source
        ),
    )


def snapshot(prices: tuple[NormalizedPrice, ...], *, count: int = 20) -> AnalyticalInputSnapshot:
    sessions = tuple(
        SessionInput(
            session_id=f"session-{day}",
            session_date=date(2026, 9, day),
            session_index=day,
            price_basis_ref="raw-v1",
            close_micros=None,
            close_state="unknown",
            close_segment=None,
            true_range_state="unknown",
            true_range_micros=None,
            source_price_revision=1 if any(p.session_date.day == day for p in prices) else None,
        )
        for day in range(1, count + 1)
    )
    return AnalyticalInputSnapshot(
        snapshot_id="snapshot-v1",
        contract_version="analysis-input-v1",
        symbol="NSI",
        as_of=NOW,
        calendar_version="calendar-v1",
        sessions=sessions,
    )


def rows(
    *,
    traded_count: int = 20,
    turnover: str | None = "5000000",
    close: str = "1000",
    volume: int = 5000,
) -> tuple[NormalizedPrice, ...]:
    return tuple(
        price(
            day,
            traded=day <= traded_count,
            turnover=turnover if day <= traded_count else ("0" if turnover is not None else None),
            close=close if day <= traded_count else None,
            volume=volume if day <= traded_count else None,
        )
        for day in range(1, 21)
    )


def test_median_uses_tenth_and_eleventh_sorted_values() -> None:
    prices = tuple(
        price(day, turnover=str(day * 1_000_000)) for day in range(1, 21)
    )

    result = calculate_liquidity(snapshot(prices), prices)

    assert result.median_xof == 10_500_000
    assert result.traded_session_count == 20
    assert result.basis == "actual"
    assert result.eligible is True


def test_fewer_than_twenty_sessions_is_unavailable() -> None:
    available = rows()[:19]

    result = calculate_liquidity(snapshot(available, count=19), available)

    assert result.status == "unavailable"
    assert result.reason_codes == ("history_incomplete",)


def test_inclusive_five_million_and_eighteen_of_twenty_boundaries() -> None:
    exactly_at_boundary = rows(traded_count=18)
    result = calculate_liquidity(snapshot(exactly_at_boundary), exactly_at_boundary)
    assert result.median_xof == 5_000_000
    assert result.traded_session_count == 18
    assert result.eligible is True

    below_frequency = rows(traded_count=17)
    result = calculate_liquidity(snapshot(below_frequency), below_frequency)
    assert result.traded_session_count == 17
    assert result.eligible is False
    assert "traded_sessions_below_threshold" in result.reason_codes

    below_value = rows(turnover=None, close="999", volume=5000)
    result = calculate_liquidity(snapshot(below_value), below_value)
    assert result.median_xof == 4_995_000
    assert result.eligible is False
    assert "median_below_threshold" in result.reason_codes


def test_estimated_basis_replaces_incomplete_actual_window_without_mixing() -> None:
    actual_and_estimated = tuple(
        price(day, turnover="9000000" if day < 20 else None)
        for day in range(1, 21)
    )

    result = calculate_liquidity(snapshot(actual_and_estimated), actual_and_estimated)

    assert result.basis == "estimated"
    assert result.median_xof == 5_000_000
    assert result.eligible is True


def test_confirmed_no_trade_is_known_zero_but_missing_observation_is_unavailable() -> None:
    known_zero_rows = rows(traded_count=18, turnover=None)
    result = calculate_liquidity(snapshot(known_zero_rows), known_zero_rows)
    assert result.status == "assessable"
    assert result.median_xof == 5_000_000
    assert result.traded_session_count == 18
    assert result.basis == "estimated"

    missing = known_zero_rows[:-1]
    result = calculate_liquidity(snapshot(missing), missing)
    assert result.status == "unavailable"
    assert result.median_xof is None
    assert "missing_price_observation" in result.reason_codes


def test_positive_actual_turnover_with_confirmed_no_trade_forbids_fallback() -> None:
    contradictory = list(rows(traded_count=19, turnover=None))
    contradictory[-1] = price(
        20, traded=False, turnover="1", close=None, volume=None
    )

    result = calculate_liquidity(snapshot(tuple(contradictory)), tuple(contradictory))

    assert result.status == "unavailable"
    assert result.basis is None
    assert result.median_xof is None
    assert result.reason_codes == ("actual_turnover_conflicts_with_no_trade",)


def test_estimation_rejects_incompatible_adjusted_price_and_volume_basis() -> None:
    prices = list(rows(turnover=None))
    prices[-1] = price(20, turnover=None, price_basis="adjusted-v2")

    result = calculate_liquidity(snapshot(tuple(prices)), tuple(prices))

    assert result.status == "unavailable"
    assert "incompatible_price_basis" in result.reason_codes


def test_current_trade_and_suspension_gate_is_separate_from_window() -> None:
    window = rows()
    liquidity = calculate_liquidity(snapshot(window), window)
    assert liquidity.eligible is True

    no_trade_gate = evaluate_current_trade_gate(price(21, traded=False, close=None, volume=None))
    assert no_trade_gate.status == "fail"
    assert no_trade_gate.reason_codes == ("no_current_trade",)

    suspended_gate = evaluate_current_trade_gate(price(21, suspension="suspended"))
    assert suspended_gate.status == "fail"
    assert suspended_gate.reason_codes == ("current_session_suspended",)

    assert evaluate_current_trade_gate(price(21)).status == "pass"
    assert evaluate_current_trade_gate(None).status == "unknown"
