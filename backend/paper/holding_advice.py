"""Generation-bound paper-position exit advice from immutable history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import Literal

from backend.analysis.ema import EmaSeries
from backend.analysis.inputs import AnalyticalInputSnapshot, SessionInput
from backend.analysis.rsi import RsiSeries
from backend.contracts.paper import PaperPosition

Action = Literal["keep", "sell", "insufficient_data", "not_applicable"]
V1_EXIT_POLICY_REF = "exit-policy-v1"
_FIXED_LOSS_PERCENT = 95
_TRAILING_ACTIVATION_PERCENT = 108
_TRAILING_STOP_PERCENT = 96
_TECHNICAL_RSI_CEILING = 45
_DURATION_SESSIONS = 30


@dataclass(frozen=True, slots=True)
class FrozenExitPolicy:
    """Reference to the immutable V1 exit policy."""

    policy_ref: str

    def __post_init__(self) -> None:
        if not self.policy_ref:
            raise ValueError("policy_ref is required")


@dataclass(frozen=True, slots=True)
class HoldingAdvice:
    action: Action
    generation: str
    state_version: int
    exit_policy_ref: str
    evaluation_session: date
    sell_reasons: tuple[str, ...]
    unavailable_checks: tuple[str, ...]
    high_water_close_micros: int | None
    trail_activated: bool
    evaluated_through_session: date | None


def _points_by_session(series: EmaSeries | RsiSeries) -> dict[str, object]:
    return {point.session_id: point for point in series.points}


def _assessable_value(point: object | None) -> float | None:
    if point is None or getattr(point, "status", None) != "assessable":
        return None
    value = getattr(point, "value", None)
    return float(value) if isinstance(value, (int, float)) and isfinite(value) else None


def _valid_close(session: SessionInput | None) -> int | None:
    if (session is None or session.close_state != "traded"
            or session.close_micros is None or session.close_micros <= 0):
        return None
    return session.close_micros


def _not_applicable(
    position: PaperPosition,
    *,
    state_version: int,
    evaluation_session: date,
    reason: str,
) -> HoldingAdvice:
    return HoldingAdvice(
        action="not_applicable",
        generation=position.generation,
        state_version=state_version,
        exit_policy_ref=position.exit_policy_ref,
        evaluation_session=evaluation_session,
        sell_reasons=(),
        unavailable_checks=(reason,),
        high_water_close_micros=position.high_water_close.micros if position.high_water_close else None,
        trail_activated=position.trail_activated,
        evaluated_through_session=position.evaluated_through_session,
    )


def _unsupported_policy(
    position: PaperPosition,
    *,
    state_version: int,
    evaluation_session: date,
) -> HoldingAdvice:
    return HoldingAdvice(
        action="insufficient_data",
        generation=position.generation,
        state_version=state_version,
        exit_policy_ref=position.exit_policy_ref,
        evaluation_session=evaluation_session,
        sell_reasons=(),
        unavailable_checks=("unsupported_basis",),
        high_water_close_micros=position.high_water_close.micros if position.high_water_close else None,
        trail_activated=position.trail_activated,
        evaluated_through_session=position.evaluated_through_session,
    )


def evaluate_holding_advice(
    position: PaperPosition,
    *,
    policy: FrozenExitPolicy,
    active_generation: str | None,
    current_state_version: int,
    expected_state_version: int,
    inputs: AnalyticalInputSnapshot,
    ema20: EmaSeries,
    ema50: EmaSeries,
    rsi14: RsiSeries,
    evaluation_session: date,
) -> HoldingAdvice:
    """Evaluate independent exit rules and propose monotone position history.

    This function has no order side effects. A caller persists the returned
    high-water, activation latch, and evaluated-through date transactionally.
    """

    if position.quantity <= 0:
        return _not_applicable(position, state_version=current_state_version,
                               evaluation_session=evaluation_session, reason="position_closed")
    if active_generation != position.generation:
        return _not_applicable(position, state_version=current_state_version,
                               evaluation_session=evaluation_session, reason="generation_superseded")
    if expected_state_version != current_state_version:
        return _not_applicable(position, state_version=current_state_version,
                               evaluation_session=evaluation_session, reason="state_version_mismatch")
    if position.exit_policy_ref != policy.policy_ref:
        return _not_applicable(position, state_version=current_state_version,
                               evaluation_session=evaluation_session, reason="exit_policy_mismatch")
    if policy.policy_ref != V1_EXIT_POLICY_REF:
        return _unsupported_policy(position, state_version=current_state_version,
                                   evaluation_session=evaluation_session)
    if position.symbol != inputs.symbol:
        return _not_applicable(position, state_version=current_state_version,
                               evaluation_session=evaluation_session, reason="symbol_mismatch")
    if any(series.input_snapshot_id != inputs.snapshot_id for series in (ema20, ema50, rsi14)):
        return _not_applicable(position, state_version=current_state_version,
                               evaluation_session=evaluation_session, reason="snapshot_mismatch")
    if ema20.period != 20 or ema50.period != 50:
        return _not_applicable(position, state_version=current_state_version,
                               evaluation_session=evaluation_session, reason="indicator_period_mismatch")

    by_index = {session.session_index: session for session in inputs.sessions}
    ordered = sorted(inputs.sessions, key=lambda session: session.session_index)
    current = next((s for s in ordered if s.session_date == evaluation_session), None)
    if current is None:
        return _not_applicable(position, state_version=current_state_version,
                               evaluation_session=evaluation_session, reason="session_missing")
    last_index: int | None = None
    if position.evaluated_through_session is not None:
        last_index = next((s.session_index for s in ordered
                           if s.session_date == position.evaluated_through_session), None)
        if last_index is None or current.session_index <= last_index:
            return _not_applicable(position, state_version=current_state_version,
                                   evaluation_session=evaluation_session, reason="late_retry")

    high = position.high_water_close.micros if position.high_water_close else None
    activated = position.trail_activated
    opening = next((s for s in ordered if s.session_date == position.opening_session), None)
    replay_start_index = opening.session_index if opening is not None else current.session_index
    for session in ordered:
        if not replay_start_index <= session.session_index <= current.session_index:
            continue
        if last_index is not None and session.session_index <= last_index:
            continue
        close = _valid_close(session)
        if close is None:
            continue
        if opening is not None:
            high = close if high is None else max(high, close)
        if not activated and close * position.quantity * 100 >= (
            position.remaining_gross_cost.micros * _TRAILING_ACTIVATION_PERCENT
        ):
            activated = True

    current_price = _valid_close(current)
    reasons: list[str] = []
    unavailable: list[str] = []
    if current_price is None:
        unavailable.extend(("fixed_loss", "trailing", "technical_pullback"))
    else:
        # Compare ratios as integers, avoiding rounded average-entry prices.
        if current_price * position.quantity * 100 <= (
            position.remaining_gross_cost.micros * _FIXED_LOSS_PERCENT
        ):
            reasons.append("fixed_loss")
        if activated:
            if high is None:
                unavailable.append("trailing")
            elif current_price * 100 <= high * _TRAILING_STOP_PERCENT:
                reasons.append("trailing_stop")

    current_ema20 = _points_by_session(ema20).get(current.session_id)
    current_ema50 = _points_by_session(ema50).get(current.session_id)
    ema20_value = _assessable_value(current_ema20)
    ema50_value = _assessable_value(current_ema50)
    if ema20_value is None or ema50_value is None:
        unavailable.append("technical_trend")
    elif ema20_value <= ema50_value:
        reasons.append("ema20_at_or_below_ema50")

    # Never compress a missing exchange session into the prior observation.
    previous = by_index.get(current.session_index - 1)
    prior_price = _valid_close(previous)
    prior_ema20 = _assessable_value(_points_by_session(ema20).get(previous.session_id)) if previous else None
    current_rsi = _assessable_value(_points_by_session(rsi14).get(current.session_id))
    if (current_price is None or prior_price is None or ema20_value is None
            or prior_ema20 is None or current_rsi is None):
        unavailable.append("technical_pullback")
    elif (current_price / 1_000_000 < ema20_value
          and prior_price / 1_000_000 < prior_ema20
          and current_rsi < _TECHNICAL_RSI_CEILING):
        reasons.append("two_closes_below_ema20_with_weak_rsi")

    opening_index = opening.session_index if opening is not None else None
    if opening_index is None:
        unavailable.append("duration")
    elif current.session_index - opening_index >= _DURATION_SESSIONS:
        reasons.append("duration")

    unique_reasons = tuple(dict.fromkeys(reasons))
    unique_unavailable = tuple(dict.fromkeys(unavailable))
    if unique_reasons:
        action: Action = "sell"
    elif unique_unavailable:
        action = "insufficient_data"
    else:
        action = "keep"
    return HoldingAdvice(
        action=action,
        generation=position.generation,
        state_version=current_state_version,
        exit_policy_ref=position.exit_policy_ref,
        evaluation_session=evaluation_session,
        sell_reasons=unique_reasons,
        unavailable_checks=unique_unavailable,
        high_water_close_micros=high,
        trail_activated=activated,
        evaluated_through_session=evaluation_session,
    )
