from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from backend.analysis.ema import EmaPoint, EmaSeries
from backend.analysis.inputs import AnalyticalInputSnapshot, SessionInput
from backend.analysis.rsi import RsiPoint, RsiSeries
from backend.contracts.paper import PaperPosition
from backend.contracts.scalars import NonNegativeMoney
from backend.paper.holding_advice import FrozenExitPolicy, evaluate_holding_advice

POLICY = FrozenExitPolicy("exit-policy-v1")
BASE = date(2026, 1, 1)
ENTRY = 100_000_000


def money(micros: int) -> NonNegativeMoney:
    return NonNegativeMoney(amount=f"{micros // 1_000_000}.{micros % 1_000_000:06d}", currency="XOF")


def position(
    *,
    quantity: int = 1,
    cost: int = ENTRY,
    opening_index: int = 0,
    high: int | None = None,
    activated: bool = False,
    evaluated: date | None = None,
    generation: str = "generation-1",
    policy_ref: str = POLICY.policy_ref,
) -> PaperPosition:
    return PaperPosition(
        generation=generation,
        symbol="TEST",
        quantity=quantity,
        reserved_sell_quantity=0,
        remaining_gross_cost=money(cost),
        purchase_fees=money(0),
        opening_session=BASE.fromordinal(BASE.toordinal() + opening_index),
        high_water_close=money(high) if high is not None else None,
        evaluated_through_session=evaluated,
        trail_activated=activated,
        exit_policy_ref=policy_ref,
    )


def evaluate(
    pos: PaperPosition,
    *,
    prices: dict[int, tuple[int | None, str]] | None = None,
    duration: int = 1,
    current_index: int | None = None,
    ema20_values: dict[int, float | None] | None = None,
    ema50_values: dict[int, float | None] | None = None,
    rsi_values: dict[int, float | None] | None = None,
    missing_session_index: int | None = None,
    active_generation: str = "generation-1",
    current_state_version: int = 4,
    expected_state_version: int = 4,
    policy: FrozenExitPolicy = POLICY,
):
    current_index = duration if current_index is None else current_index
    prices = prices or {}
    ema20_values = ema20_values or {}
    ema50_values = ema50_values or {}
    rsi_values = rsi_values or {}
    sessions = tuple(
        SessionInput(
            session_id=f"session-{index}",
            session_date=BASE.fromordinal(BASE.toordinal() + index),
            session_index=index,
            price_basis_ref="basis-1",
            close_micros=(prices.get(index, (ENTRY, "traded"))[0]),
            close_state=prices.get(index, (ENTRY, "traded"))[1],
            close_segment=1 if prices.get(index, (ENTRY, "traded"))[0] is not None else None,
            true_range_state="unknown",
            true_range_micros=None,
            source_price_revision=index,
        )
        for index in range(current_index + 1) if index != missing_session_index
    )
    sessions_by_index = {session.session_index: session for session in sessions}
    inputs = AnalyticalInputSnapshot(
        snapshot_id="snapshot-1",
        contract_version="analysis-input-v1",
        symbol="TEST",
        as_of=datetime(2026, 2, 1, tzinfo=timezone.utc),
        calendar_version="calendar-1",
        sessions=sessions,
    )

    def ema(period: int, values: dict[int, float | None]) -> EmaSeries:
        return EmaSeries(
            input_snapshot_id="snapshot-1",
            rule_version="ema-v1",
            period=period,
            points=tuple(
                EmaPoint(
                    session_id=f"session-{index}", session_index=index, period=period,
                    value=values.get(index, 90.0 if period == 20 else 80.0),
                    status="assessable" if values.get(index, 1) is not None else "missing_inputs",
                    close_segment=1, input_close_state=sessions_by_index[index].close_state,
                )
                for index in range(current_index + 1) if index != missing_session_index
            ),
            checkpoints=(),
        )

    rsi = RsiSeries(
        input_snapshot_id="snapshot-1",
        rule_version="rsi-v1",
        points=tuple(
            RsiPoint(
                session_id=f"session-{index}", session_index=index,
                value=rsi_values.get(index, 50.0),
                status="assessable" if rsi_values.get(index, 1) is not None else "missing_inputs",
                close_segment=1, input_close_state=sessions_by_index[index].close_state,
            )
            for index in range(current_index + 1) if index != missing_session_index
        ),
        checkpoints=(),
    )
    return evaluate_holding_advice(
        pos,
        policy=policy,
        active_generation=active_generation,
        current_state_version=current_state_version,
        expected_state_version=expected_state_version,
        inputs=inputs,
        ema20=ema(20, ema20_values),
        ema50=ema(50, ema50_values),
        rsi14=rsi,
        evaluation_session=sessions_by_index[current_index].session_date,
    )


@pytest.mark.parametrize("price,expected", [(95_000_000, "sell"), (95_000_001, "keep")])
def test_fixed_loss_threshold_is_inclusive(price: int, expected: str) -> None:
    result = evaluate(position(), prices={1: (price, "traded")})
    assert result.action == expected
    assert ("fixed_loss" in result.sell_reasons) == (expected == "sell")


def test_trailing_activation_at_108_percent_latches() -> None:
    result = evaluate(position(), prices={1: (108_000_000, "traded")})
    assert result.trail_activated is True
    assert result.high_water_close_micros == 108_000_000


@pytest.mark.parametrize("price,expected", [(96_000_000, "sell"), (96_000_001, "keep")])
def test_activated_trailing_threshold_is_inclusive(price: int, expected: str) -> None:
    result = evaluate(
        position(high=100_000_000, activated=True), prices={1: (price, "traded")}
    )
    assert result.action == expected
    assert ("trailing_stop" in result.sell_reasons) == (expected == "sell")


def test_ema20_equality_with_ema50_sells() -> None:
    result = evaluate(position(), ema20_values={1: 80.0}, ema50_values={1: 80.0})
    assert result.action == "sell"
    assert "ema20_at_or_below_ema50" in result.sell_reasons


def test_rsi_45_does_not_trigger_two_close_technical_exit() -> None:
    result = evaluate(
        position(),
        prices={0: (80_000_000, "traded"), 1: (80_000_000, "traded")},
        ema20_values={0: 90.0, 1: 90.0},
        rsi_values={1: 45.0},
    )
    assert "two_closes_below_ema20_with_weak_rsi" not in result.sell_reasons


def test_rsi_below_45_with_two_closes_below_ema20_triggers() -> None:
    result = evaluate(
        position(),
        prices={0: (80_000_000, "traded"), 1: (80_000_000, "traded")},
        ema20_values={0: 90.0, 1: 90.0},
        rsi_values={1: 44.999},
    )
    assert "two_closes_below_ema20_with_weak_rsi" in result.sell_reasons


def test_missing_exchange_session_does_not_compress_technical_lookback() -> None:
    result = evaluate(
        position(), duration=2, current_index=2, missing_session_index=1,
        prices={0: (80_000_000, "traded"), 2: (80_000_000, "traded")},
        ema20_values={0: 90.0, 2: 90.0}, rsi_values={2: 44.0},
    )
    assert "two_closes_below_ema20_with_weak_rsi" not in result.sell_reasons
    assert "technical_pullback" in result.unavailable_checks


@pytest.mark.parametrize(("elapsed", "expected"), [(0, "keep"), (29, "keep"), (30, "sell"), (31, "sell")])
def test_duration_uses_authoritative_session_index(elapsed: int, expected: str) -> None:
    if elapsed == 0:
        result = evaluate(position(opening_index=1), duration=0, current_index=1)
    else:
        result = evaluate(position(), duration=elapsed)
    assert result.action == expected
    assert ("duration" in result.sell_reasons) == (elapsed >= 30)


def test_missing_price_keeps_independent_duration_sell_and_reports_unknown_checks() -> None:
    result = evaluate(
        position(), duration=30, prices={30: (None, "unknown")},
        ema20_values={30: None}, ema50_values={30: None}, rsi_values={30: None},
    )
    assert result.action == "sell"
    assert result.sell_reasons == ("duration",)
    assert {"fixed_loss", "trailing", "technical_pullback", "technical_trend"} <= set(result.unavailable_checks)


def test_simultaneous_exit_reasons_are_all_returned() -> None:
    result = evaluate(
        position(high=100_000_000, activated=True),
        prices={30: (90_000_000, "traded")}, duration=30,
        ema20_values={30: 100.0}, ema50_values={30: 100.0},
    )
    assert set(result.sell_reasons) == {"fixed_loss", "trailing_stop", "ema20_at_or_below_ema50", "duration"}


def test_additional_buy_uses_updated_weighted_gross_entry_and_preserves_exit_state() -> None:
    before = position(high=110_000_000, activated=True)
    after_buy = before.model_copy(update={"quantity": 2, "remaining_gross_cost": money(220_000_000)})
    result = evaluate(after_buy, prices={1: (115_000_000, "traded")})
    assert result.trail_activated is True
    assert result.high_water_close_micros == 115_000_000
    assert result.exit_policy_ref == before.exit_policy_ref
    assert result.evaluated_through_session == BASE.fromordinal(BASE.toordinal() + 1)


def test_additional_buy_does_not_retroactively_activate_from_old_high() -> None:
    after_buy = position(high=120_000_000).model_copy(
        update={"quantity": 2, "remaining_gross_cost": money(220_000_000)}
    )
    result = evaluate(after_buy, prices={1: (110_000_000, "traded")})
    assert result.trail_activated is False
    assert result.high_water_close_micros == 120_000_000


def test_partial_sell_preserves_timer_high_activation_and_policy() -> None:
    prior = position(quantity=4, cost=400_000_000, opening_index=0,
                     high=120_000_000, activated=True)
    after_partial = prior.model_copy(
        update={"quantity": 2, "remaining_gross_cost": money(200_000_000)}
    )
    result = evaluate(after_partial, duration=29, prices={29: (120_000_000, "traded")})
    assert result.sell_reasons == ()
    assert result.high_water_close_micros == 120_000_000
    assert result.trail_activated is True
    assert result.exit_policy_ref == prior.exit_policy_ref


def test_full_close_and_reopen_resets_position_lifetime_state() -> None:
    closed = position(quantity=0, cost=0, high=None, activated=False)
    assert evaluate(closed).action == "not_applicable"
    reopened = position(quantity=1, cost=130_000_000, opening_index=2)
    result = evaluate(reopened, current_index=2, prices={2: (130_000_000, "traded")})
    assert result.trail_activated is False
    assert result.high_water_close_micros == 130_000_000
    assert result.evaluated_through_session == reopened.opening_session


def test_position_keeps_its_old_frozen_policy_reference() -> None:
    newer = FrozenExitPolicy("exit-policy-v2")
    old_position = position(policy_ref="exit-policy-v1")
    result = evaluate(old_position, policy=newer)
    assert result.action == "not_applicable"
    assert result.unavailable_checks == ("exit_policy_mismatch",)
    assert result.exit_policy_ref == "exit-policy-v1"


def test_unknown_matching_policy_reference_is_insufficient_and_not_evaluated() -> None:
    unknown_policy = FrozenExitPolicy("exit-policy-unknown")
    unknown_position = position(policy_ref="exit-policy-unknown")
    result = evaluate(
        unknown_position,
        policy=unknown_policy,
        prices={1: (95_000_000, "traded")},
    )
    assert result.action == "insufficient_data"
    assert result.sell_reasons == ()
    assert result.unavailable_checks == ("unsupported_basis",)


def test_carried_close_cannot_create_a_new_high_or_trigger_price_exits() -> None:
    result = evaluate(
        position(high=100_000_000), prices={0: (100_000_000, "traded"),
                                           1: (120_000_000, "carried")}
    )
    assert result.high_water_close_micros == 100_000_000
    assert result.action == "insufficient_data"


def test_reset_generation_fences_late_retry_without_resurrecting_state() -> None:
    old = position(high=110_000_000, activated=True, generation="generation-old")
    result = evaluate(old, active_generation="generation-new", prices={1: (130_000_000, "traded")})
    assert result.action == "not_applicable"
    assert result.unavailable_checks == ("generation_superseded",)
    assert result.high_water_close_micros == 110_000_000
    assert result.trail_activated is True


def test_state_version_mismatch_cannot_publish_advice_for_stale_position() -> None:
    result = evaluate(position(), current_state_version=5, expected_state_version=4)
    assert result.action == "not_applicable"
    assert result.state_version == 5
    assert result.unavailable_checks == ("state_version_mismatch",)


def test_old_session_retry_is_fenced() -> None:
    through = BASE.fromordinal(BASE.toordinal() + 2)
    result = evaluate(position(evaluated=through), current_index=1, prices={1: (130_000_000, "traded")})
    assert result.action == "not_applicable"
    assert result.unavailable_checks == ("late_retry",)
