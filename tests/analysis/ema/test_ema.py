"""Approved seed, warm-up and replay behavior for EMA20 and EMA50."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, cast

import pytest

from backend.analysis.ema import EmaCalculationError, calculate_ema, calculate_ema20_50
from backend.analysis.inputs import AnalyticalInputSnapshot, SessionInput


def snapshot(
    closes: list[int | None],
    *,
    segments: list[int | None] | None = None,
    close_states: list[Literal["traded", "carried", "unknown"]] | None = None,
    snapshot_id: str = "snapshot-1",
) -> AnalyticalInputSnapshot:
    if segments is None:
        segments = [1 if close is not None else None for close in closes]
    if close_states is None:
        close_states = ["traded" if close is not None else "unknown" for close in closes]
    assert close_states is not None
    sessions = tuple(
        SessionInput(
            session_id=f"session-{index}",
            session_date=date(2026, 1, 1),
            session_index=index,
            price_basis_ref="basis-v1" if close is not None else None,
            close_micros=None if close is None else close * 1_000_000,
            close_state=close_states[index - 1],
            close_segment=segments[index - 1],
            true_range_state="unknown",
            true_range_micros=None,
            source_price_revision=1 if close is not None else None,
        )
        for index, close in enumerate(closes, start=1)
    )
    return AnalyticalInputSnapshot(
        snapshot_id=snapshot_id,
        contract_version="analysis-input-v1",
        symbol="NSI",
        as_of=datetime(2026, 9, 23, tzinfo=timezone.utc),
        calendar_version="calendar-v1",
        sessions=sessions,
    )


def test_approved_sma_seeds_and_first_recurrence_are_unrounded() -> None:
    inputs = snapshot(list(range(1, 52)))
    ema20, ema50 = calculate_ema20_50(inputs, rule_version="ema-v1")

    assert ema20.points[18].value is None
    assert ema20.points[19].value == 10.5
    assert ema20.points[20].value == pytest.approx((2 / 21) * 21 + (19 / 21) * 10.5)
    assert ema50.points[48].value is None
    assert ema50.points[49].value == 25.5
    assert ema50.points[50].value == pytest.approx((2 / 51) * 51 + (49 / 51) * 25.5)
    assert ema20.points[19].status == "warming_up"


def test_carried_close_counts_and_unknown_close_starts_a_fresh_segment() -> None:
    closes = [100] * 19 + [100, 100, None] + [200] * 20
    segments = [1] * 21 + [None] + [2] * 20
    states = cast(
        list[Literal["traded", "carried", "unknown"]],
        ["traded"] * 20 + ["carried", "unknown"] + ["traded"] * 20,
    )
    series = calculate_ema(
        snapshot(closes, segments=segments, close_states=states), period=20, rule_version="ema-v1"
    )

    assert series.points[19].value == 100.0
    assert series.points[20].value == 100.0
    assert series.points[20].input_close_state == "carried"
    assert series.points[21].status == "missing_inputs"
    assert series.points[41].value == 200.0
    assert series.points[41].close_segment == 2


def test_maturity_is_session_based_at_250_not_249() -> None:
    series = calculate_ema(snapshot([100] * 250), period=20, rule_version="ema-v1")

    assert series.points[248].status == "warming_up"
    assert series.points[249].status == "assessable"
    assert series.points[249].value == 100.0


def test_checkpoint_suffix_replay_agrees_with_full_replay_and_keeps_new_snapshot_evidence() -> None:
    original = snapshot([100 + index for index in range(30)])
    full = calculate_ema(original, period=20, rule_version="ema-v1")
    anchor = full.checkpoints[4]
    corrected = snapshot([100 + index for index in range(30)], snapshot_id="snapshot-corrected")
    suffix = calculate_ema(corrected, period=20, rule_version="ema-v1", checkpoint=anchor)

    assert [point.value for point in suffix.points] == pytest.approx(
        [point.value for point in full.points if point.session_index > anchor.session_index]
    )
    assert suffix.checkpoints[0].input_snapshot_id == "snapshot-corrected"
    assert suffix.checkpoints[0].value == pytest.approx(full.checkpoints[5].value, rel=1e-8)


def test_invalid_period_and_incompatible_checkpoint_are_rejected() -> None:
    inputs = snapshot([100] * 25)
    with pytest.raises(EmaCalculationError, match="approved EMA20"):
        calculate_ema(inputs, period=14, rule_version="ema-v1")

    checkpoint = calculate_ema(inputs, period=20, rule_version="ema-v1").checkpoints[0]
    with pytest.raises(EmaCalculationError, match="checkpoint period"):
        calculate_ema(inputs, period=50, rule_version="ema-v1", checkpoint=checkpoint)
