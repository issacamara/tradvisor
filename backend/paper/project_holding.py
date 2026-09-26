"""Monotone, generation-bound paper holding projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.analysis.ema import EmaSeries
from backend.analysis.inputs import AnalyticalInputSnapshot
from backend.analysis.rsi import RsiSeries
from backend.contracts.paper import PaperPosition
from backend.contracts.scalars import NonNegativeMoney
from backend.paper.holding_advice import FrozenExitPolicy, HoldingAdvice, evaluate_holding_advice


@dataclass(frozen=True, slots=True)
class HoldingProjection:
    position: PaperPosition
    advice: HoldingAdvice


def advance_holding(
    position: PaperPosition,
    *,
    active_generation: str | None,
    current_state_version: int,
    inputs: AnalyticalInputSnapshot,
    ema20: EmaSeries,
    ema50: EmaSeries,
    rsi14: RsiSeries,
    evaluation_session: date,
    policy: FrozenExitPolicy,
) -> HoldingProjection:
    """Advance a position once, never regressing its high-water or session."""

    advice = evaluate_holding_advice(
        position,
        policy=policy,
        active_generation=active_generation,
        current_state_version=current_state_version,
        expected_state_version=current_state_version,
        inputs=inputs,
        ema20=ema20,
        ema50=ema50,
        rsi14=rsi14,
        evaluation_session=evaluation_session,
    )
    if advice.generation != position.generation:
        return HoldingProjection(position, advice)
    previous_session = position.evaluated_through_session
    if previous_session is not None and evaluation_session <= previous_session:
        return HoldingProjection(position, advice)
    next_high = advice.high_water_close_micros
    if position.high_water_close is not None and next_high is not None:
        next_high = max(position.high_water_close.micros, next_high)
    next_high_money = (
        None
        if next_high is None
        else NonNegativeMoney(
            amount=f"{next_high // 1_000_000}.{next_high % 1_000_000:06d}", currency="XOF"
        )
    )
    next_position = position.model_copy(
        update={
            "high_water_close": next_high_money,
            "trail_activated": position.trail_activated or advice.trail_activated,
            "evaluated_through_session": evaluation_session,
        }
    )
    return HoldingProjection(next_position, advice)
