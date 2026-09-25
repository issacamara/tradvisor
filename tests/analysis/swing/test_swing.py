"""Scoring, threshold, and independent eligibility-guard tests."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

import pytest

from backend.analysis.atr import AtrPoint, AtrSeries
from backend.analysis.ema import EmaPoint, EmaSeries
from backend.analysis.inputs import AnalyticalInputSnapshot, SessionInput
from backend.analysis.liquidity import CurrentTradeGate, LiquidityResult
from backend.analysis.rsi import RsiPoint, RsiSeries
from backend.analysis.swing import (
    SwingStrategyInput,
    _extension_contribution,
    _rsi_contribution,
    evaluate_swing,
    load_swing_rules,
)

NOW = datetime(2026, 9, 25, 16, tzinfo=timezone.utc)
RULES = load_swing_rules()


def strategy_input(
    *,
    fast: float = 100,
    slow: float = 99,
    previous_fast: float = 99.5,
    rsi: float = 50,
    atr: float = 1,
    close: str = "102",
    liquidity: bool | None = True,
    current_trade: Literal["pass", "fail", "unknown"] = "pass",
) -> SwingStrategyInput:
    sessions = tuple(
        SessionInput(
            session_id=f"s-{index}", session_date=date(2026, 9, 20 + index),
            session_index=index, price_basis_ref="basis-v1",
            close_micros=int(Decimal(close) * 1_000_000) if index == 5 else 99_500_000,
            close_state="traded", close_segment=0, true_range_state="observed",
            true_range_micros=1_000_000, source_price_revision=1,
        )
        for index in range(6)
    )
    snapshot = AnalyticalInputSnapshot(
        "snapshot-v1", "analysis-input-v1", "TEST", NOW, "calendar-v1", sessions
    )
    ema20 = EmaSeries("snapshot-v1", "ema-v1", 20, (
        EmaPoint("s-0", 0, 20, previous_fast, "assessable", 0, "traded"),
        EmaPoint("s-5", 5, 20, fast, "assessable", 0, "traded"),
    ), ())
    ema50 = EmaSeries("snapshot-v1", "ema-v1", 50, (
        EmaPoint("s-5", 5, 50, slow, "assessable", 0, "traded"),
    ), ())
    rsi_series = RsiSeries("snapshot-v1", "rsi-v1", (
        RsiPoint("s-5", 5, rsi, "assessable", 0, "traded"),
    ), ())
    atr_series = AtrSeries("snapshot-v1", "atr-v1", (
        AtrPoint("s-5", 5, atr, "assessable", atr, "observed", "basis-v1", 250, 250),
    ), ())
    liquidity_result = LiquidityResult(
        "snapshot-v1", "assessable",
        Decimal("5000000") if liquidity is not False else Decimal("4000000"),
        20, "actual",
        liquidity, tuple(f"liq-s-{i}" for i in range(20)), ("turnover-source",),
        () if liquidity else ("median_below_threshold",),
    )
    trade_gate = CurrentTradeGate(current_trade, ("current-price-source",),
                                  () if current_trade == "pass" else ("current_trade_unknown",))
    return SwingStrategyInput(
        snapshot, ema20, ema50, rsi_series, atr_series, liquidity_result, trade_gate
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [(40, 0), (45, 7.5), (50, 15), (52.5, 22.5), (55, 30),
     (60, 30), (65, 30), (67.5, 22.5), (70, 15), (75, 7.5), (80, 0)],
)
def test_rsi_curve_endpoints_and_interiors(value: float, expected: float) -> None:
    assert _rsi_contribution(Decimal(str(value)), RULES) == Decimal(str(expected))


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-1, 0), (0, 30), (0.5, 30), (1, 30), (2, 15), (2.5, 7.5), (3, 0), (4, 0)],
)
def test_extension_curve_endpoints_and_interiors(value: float, expected: float) -> None:
    assert _extension_contribution(Decimal(str(value)), RULES) == Decimal(str(expected))


def test_unrounded_score_at_exactly_seventy_is_buy_eligible() -> None:
    result = evaluate_swing(strategy_input(
        fast=100, slow=99, previous_fast=99.5, rsi=50, atr=1, close="102"
    ))

    assert result.score is not None
    assert result.score.total == Decimal("70")
    assert result.decision == "buy"


def test_display_rounding_cannot_promote_score_to_buy() -> None:
    result = evaluate_swing(strategy_input(
        fast=100, slow=99, previous_fast=99.501, rsi=50, atr=1, close="102"
    ))

    assert result.score is not None
    assert result.score.total == Decimal("69.96")
    assert result.score.display_total == Decimal("70.0")
    assert result.decision == "not_buy"
    assert "score_below_buy_threshold" in result.reason_codes


@pytest.mark.parametrize(("fast", "slow", "previous_fast"), [(100, 100, 99), (101, 100, 101), (101, 100, 102)])
def test_flat_or_falling_ema_blocks_buy_even_with_score_eighty(
    fast: float, slow: float, previous_fast: float
) -> None:
    result = evaluate_swing(strategy_input(
        fast=fast, slow=slow, previous_fast=previous_fast, rsi=65, atr=1,
        close=str(fast),
    ))

    assert result.score is not None and result.score.total == Decimal("80")
    assert result.decision == "not_buy"
    assert any(guard.status == "fail" for guard in result.guards)


def test_extension_at_three_atr_blocks_buy_despite_score_seventy() -> None:
    result = evaluate_swing(strategy_input(
        fast=100, slow=99, previous_fast=99, rsi=65, atr=1, close="103"
    ))

    assert result.score is not None and result.score.total == Decimal("70")
    assert result.decision == "not_buy"
    guard = next(guard for guard in result.guards if guard.code == "extension_below_three_atr")
    assert guard.status == "fail"
    assert guard.reason_codes == ("extension_at_or_above_three_atr",)


@pytest.mark.parametrize(
    ("liquidity", "current_trade", "expected_reason"),
    [(False, "pass", "median_below_threshold"), (True, "unknown", "current_trade_unknown")],
)
def test_independent_guards_keep_non_buy_distinct_from_sell(
    liquidity: bool | None,
    current_trade: Literal["pass", "fail", "unknown"],
    expected_reason: str,
) -> None:
    result = evaluate_swing(strategy_input(
        fast=100, slow=99, previous_fast=99.5, rsi=50, atr=1, close="102",
        liquidity=liquidity, current_trade=current_trade,
    ))

    assert result.decision in {"not_buy", "unavailable"}
    assert expected_reason in result.reason_codes


def test_result_retains_immutable_rule_and_evidence_references() -> None:
    result = evaluate_swing(strategy_input())

    assert result.rule_reference == "swing-v1"
    assert result.rule_version == "swing-v1"
    assert "snapshot-v1" in result.evidence_refs
    assert "turnover-source" in result.evidence_refs
    assert result.indicator_rule_refs == ("ema-v1", "rsi-v1", "atr-v1")
    with pytest.raises((AttributeError, TypeError)):
        result.rule_version = "changed"  # type: ignore[misc]
