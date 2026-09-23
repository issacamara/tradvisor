from datetime import date, datetime, timezone
from typing import Sequence, cast

import pytest

from backend.analysis.atr import AtrCalculationError, calculate_atr14
from backend.analysis.inputs import (
    AnalyticalInputSnapshot,
    CloseState,
    SessionInput,
    TrueRangeState,
    build_analytical_input_snapshot,
)
from backend.contracts.analysis import NormalizedPrice, NormalizedSession, Provenance, Revision
from backend.contracts.scalars import NonNegativeMoney

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _money(value: str) -> NonNegativeMoney:
    return NonNegativeMoney(amount=value, currency="XOF")


def _revision(number: int) -> Revision:
    return Revision(
        revision=number,
        known_at=NOW,
        provenance=Provenance(source_id=f"source-{number}", collected_at=NOW, basis="actual"),
    )


def _market_session(index: int) -> NormalizedSession:
    return NormalizedSession(
        calendar_version="calendar-v1",
        session_id=f"session-{index}",
        session_date=date(2026, 1, index),
        session_index=index,
        exchange_timezone="Africa/Abidjan",
        status="trading",
        official_close_at=NOW,
        source_evidence=(Provenance(source_id="calendar", collected_at=NOW, basis="actual"),),
        reason_codes=(),
        revision=_revision(index),
    )


def _market_price(index: int, *, close: str, high: str, low: str) -> NormalizedPrice:
    return NormalizedPrice(
        symbol="NSI",
        session_date=date(2026, 1, index),
        close=_money(close),
        high=_money(high),
        low=_money(low),
        volume=10,
        trade_status="traded",
        basis="actual",
        original_source_date=date(2026, 1, index),
        price_basis_ref="basis-v1",
        validated_available_at=NOW,
        suspension_status="not_suspended",
        reason_codes=(),
        revision=_revision(index),
    )


def snapshot(
    ranges: list[int | None],
    *,
    states: Sequence[TrueRangeState] | None = None,
    bases: Sequence[str | None] | None = None,
    close_states: Sequence[CloseState] | None = None,
    close_segments: Sequence[int | None] | None = None,
    snapshot_id: str = "snapshot-1",
) -> AnalyticalInputSnapshot:
    size = len(ranges)
    states = states or ["observed" if value is not None else "unknown" for value in ranges]
    bases = bases or ["basis-v1"] * size
    close_states = close_states or ["traded"] * size
    close_segments = close_segments or [1] * size
    sessions = tuple(
        SessionInput(
            f"s-{index}", date(2026, 1, 1), index, bases[index - 1],
            10_000_000, close_states[index - 1], close_segments[index - 1],
            states[index - 1], None if value is None else value * 1_000_000, 1,
        )
        for index, value in enumerate(ranges, 1)
    )
    return AnalyticalInputSnapshot(
        snapshot_id, "analysis-input-v1", "NSI",
        datetime(2026, 1, 1, tzinfo=timezone.utc), "calendar-v1", sessions,
    )


def test_seed_and_wilder_recurrence() -> None:
    series = calculate_atr14(snapshot([None] + [2] * 15), rule_version="atr-v1")
    assert series.points[13].value is None
    assert series.points[14].value == 2.0
    assert series.points[15].value == pytest.approx((13 * 2 + 2) / 14)


def test_true_range_uses_intraday_range_and_both_gap_legs() -> None:
    inputs = build_analytical_input_snapshot(
        symbol="NSI",
        as_of=NOW,
        sessions=(_market_session(1), _market_session(2)),
        prices=(
            _market_price(1, close="100", high="105", low="95"),
            _market_price(2, close="110", high="112", low="108"),
        ),
    )
    series = calculate_atr14(inputs, rule_version="atr-v1")
    assert series.points[1].true_range == 12.0
    assert series.points[1].true_range_state == "observed"


def test_missing_traded_session_ohlc_interrupts_even_when_close_continues() -> None:
    ranges = [None] + [2] * 14 + [None, 4]
    series = calculate_atr14(snapshot(ranges), rule_version="atr-v1")
    assert series.points[15].status == "missing_inputs"
    assert series.points[15].reason_codes == ("unknown_true_range",)
    assert series.points[16].value is None
    assert series.points[16].valid_true_range_count == 1


def test_modeled_no_trade_is_labeled_zero_while_unknown_breaks_chain() -> None:
    ranges = [None] + [3] * 13 + [0, None]
    states = cast(
        list[TrueRangeState],
        ["unknown"] + ["observed"] * 13 + ["modeled_zero_range", "unknown"],
    )
    close_states = cast(list[CloseState], ["traded"] * 14 + ["carried", "traded"])
    series = calculate_atr14(
        snapshot(ranges, states=states, close_states=close_states), rule_version="atr-v1"
    )
    assert series.points[14].value == pytest.approx(39 / 14)
    assert series.points[14].true_range_state == "modeled_zero_range"
    assert series.points[14].reason_codes == ("modeled_zero_range",)
    assert series.points[15].status == "missing_inputs"


def test_basis_change_restarts_instead_of_smoothing() -> None:
    ranges = [None] + [3] * 13 + [None] + [9] * 14
    bases: Sequence[str | None] = ["basis-v1"] * 15 + ["basis-v2"] * 14
    segments: Sequence[int | None] = [1] * 15 + [2] * 14
    series = calculate_atr14(
        snapshot(ranges, bases=bases, close_segments=segments), rule_version="atr-v1"
    )
    assert series.points[15].value is None
    assert series.points[-1].value == 9.0
    assert series.points[-1].valid_true_range_count == 14


def test_maturity_requires_250_sessions_and_zero_atr_is_valid_but_not_denominator() -> None:
    flat = calculate_atr14(snapshot([None] + [0] * 249), rule_version="atr-v1")
    assert flat.points[248].status == "warming_up"
    assert flat.points[249].status == "assessable"
    assert flat.points[249].value is not None
    assert flat.points[249].value == 0.0


def test_checkpoint_replay_matches_full_recomputation_after_suffix_correction() -> None:
    initial = snapshot([None] + list(range(1, 270)))
    original = calculate_atr14(initial, rule_version="atr-v1")
    anchor = original.checkpoints[20]
    corrected_ranges = [None] + list(range(1, 270))
    corrected_ranges[-1] = 999
    corrected = snapshot(corrected_ranges, snapshot_id="corrected")
    replay = calculate_atr14(corrected, rule_version="atr-v1", checkpoint=anchor)
    full = calculate_atr14(corrected, rule_version="atr-v1")
    assert [point.value for point in replay.points] == pytest.approx(
        [point.value for point in full.points if point.session_index > anchor.session_index],
        rel=1e-8, abs=1e-8,
    )


def test_checkpoint_fingerprint_covers_true_range_and_basis() -> None:
    full = calculate_atr14(snapshot([None] + [4] * 20), rule_version="atr-v1")
    anchor = full.checkpoints[0]
    changed = [None] + [4] * 20
    changed[1] = 5
    with pytest.raises(AtrCalculationError, match="prefix differs"):
        calculate_atr14(snapshot(changed), rule_version="atr-v1", checkpoint=anchor)
    with pytest.raises(AtrCalculationError, match="rule version"):
        calculate_atr14(snapshot([None] + [4] * 20), rule_version="other", checkpoint=anchor)
