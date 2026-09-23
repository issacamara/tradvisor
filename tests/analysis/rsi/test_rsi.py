from datetime import date, datetime, timezone

import pytest

from backend.analysis.inputs import AnalyticalInputSnapshot, SessionInput
from backend.analysis.rsi import RsiCalculationError, calculate_rsi14


def snapshot(closes, *, segments=None, states=None, snapshot_id="snapshot-1"):
    segments = segments or [1 if close is not None else None for close in closes]
    states = states or ["traded" if close is not None else "unknown" for close in closes]
    return AnalyticalInputSnapshot(snapshot_id, "analysis-input-v1", "NSI", datetime(2026, 1, 1, tzinfo=timezone.utc), "calendar-v1", tuple(
        SessionInput(f"s-{i}", date(2026, 1, 1), i, "basis-v1" if c is not None else None, None if c is None else c * 1_000_000, states[i-1], segments[i-1], "unknown", None, 1 if c is not None else None)
        for i, c in enumerate(closes, 1)
    ))


def test_seed_boundaries_and_first_wilder_recurrence() -> None:
    gain = calculate_rsi14(snapshot(list(range(1, 17))), rule_version="rsi-v1")
    loss = calculate_rsi14(snapshot(list(range(16, 0, -1))), rule_version="rsi-v1")
    flat = calculate_rsi14(snapshot([10] * 15), rule_version="rsi-v1")
    assert gain.points[13].value is None
    assert gain.points[14].value == 100.0
    assert gain.points[15].value == 100.0
    assert loss.points[14].value == 0.0
    assert flat.points[14].value == 50.0


def test_mixed_gain_loss_seed_and_wilder_recurrence_match_the_formula() -> None:
    closes = [0]
    for _ in range(7):
        closes.extend((closes[-1] + 2, closes[-1] + 1))
    closes.append(closes[-1] - 1)
    series = calculate_rsi14(snapshot(closes), rule_version="rsi-v1")
    seeded = 100.0 - 100.0 / (1.0 + 1.0 / 0.5)
    next_gain = 13.0 / 14.0
    next_loss = (13.0 * 0.5 + 1.0) / 14.0
    recurred = 100.0 - 100.0 / (1.0 + next_gain / next_loss)
    assert series.points[14].value == pytest.approx(seeded, rel=1e-8, abs=1e-8)
    assert series.points[15].value == pytest.approx(recurred, rel=1e-8, abs=1e-8)


def test_carried_close_counts_and_unknown_interrupts_segment() -> None:
    values = list(range(1, 15)) + [14, None] + list(range(30, 45))
    segments = [1] * 15 + [None] + [2] * 15
    states = ["traded"] * 14 + ["carried", "unknown"] + ["traded"] * 15
    series = calculate_rsi14(snapshot(values, segments=segments, states=states), rule_version="rsi-v1")
    assert series.points[14].value == 100.0
    assert series.points[14].input_close_state == "carried"
    assert series.points[15].status == "missing_inputs"
    assert series.points[-1].value == 100.0


def test_maturity_and_checkpoint_correction_fence() -> None:
    original = snapshot(list(range(1, 251)))
    full = calculate_rsi14(original, rule_version="rsi-v1")
    assert full.points[248].status == "warming_up"
    assert full.points[249].status == "assessable"
    anchor = full.checkpoints[5]
    corrected = list(range(1, 251)); corrected[-1] = 999
    suffix = calculate_rsi14(snapshot(corrected, snapshot_id="corrected"), rule_version="rsi-v1", checkpoint=anchor)
    corrected_full = calculate_rsi14(snapshot(corrected, snapshot_id="corrected"), rule_version="rsi-v1")
    assert [point.value for point in suffix.points] == pytest.approx(
        [point.value for point in corrected_full.points if point.session_index > anchor.session_index],
        rel=1e-8,
        abs=1e-8,
    )
    stale = list(range(1, 251)); stale[0] = 999
    with pytest.raises(RsiCalculationError, match="prefix differs"):
        calculate_rsi14(snapshot(stale, snapshot_id="stale"), rule_version="rsi-v1", checkpoint=anchor)
