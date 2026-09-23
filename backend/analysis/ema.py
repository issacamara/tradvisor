"""Seeded EMA calculation over immutable analytical input snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.analysis.inputs import AnalyticalInputSnapshot, CloseState
from backend.contracts.scalars import OpaqueIdentifier

EMA_PERIODS = (20, 50)
WARM_UP_SESSIONS = 250
EmaStatus = Literal["warming_up", "assessable", "missing_inputs"]


class EmaCalculationError(ValueError):
    """Raised when a requested EMA period or replay anchor is invalid."""


@dataclass(frozen=True)
class EmaPoint:
    session_id: OpaqueIdentifier
    session_index: int
    period: int
    value: float | None
    status: EmaStatus
    close_segment: int | None
    input_close_state: CloseState
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmaCheckpoint:
    """An immutable recurrence anchor for a compatible later replay."""

    input_snapshot_id: OpaqueIdentifier
    rule_version: OpaqueIdentifier
    period: int
    session_index: int
    close_segment: int
    close_count: int
    value: float


@dataclass(frozen=True)
class EmaSeries:
    input_snapshot_id: OpaqueIdentifier
    rule_version: OpaqueIdentifier
    period: int
    points: tuple[EmaPoint, ...]
    checkpoints: tuple[EmaCheckpoint, ...]


def _xof(close_micros: int) -> float:
    return close_micros / 1_000_000


def calculate_ema(
    snapshot: AnalyticalInputSnapshot,
    *,
    period: int,
    rule_version: OpaqueIdentifier,
    checkpoint: EmaCheckpoint | None = None,
) -> EmaSeries:
    """Calculate one unrounded EMA series, optionally continuing after an anchor.

    A supplied checkpoint lets a corrected snapshot replay only the affected
    suffix. It is valid only for the same EMA period and rule version; a new
    snapshot identity is deliberately retained in the emitted evidence.
    """

    if period not in EMA_PERIODS:
        raise EmaCalculationError("only approved EMA20 and EMA50 periods are supported")
    if checkpoint is not None and (checkpoint.period != period or checkpoint.rule_version != rule_version):
        raise EmaCalculationError("checkpoint period and rule version must match the requested series")

    multiplier = 2.0 / (period + 1)
    points: list[EmaPoint] = []
    checkpoints: list[EmaCheckpoint] = []
    segment: int | None = checkpoint.close_segment if checkpoint is not None else None
    close_count = checkpoint.close_count if checkpoint is not None else 0
    previous_ema = checkpoint.value if checkpoint is not None else None
    seed_closes: list[float] = []

    for session in snapshot.sessions:
        if checkpoint is not None and session.session_index <= checkpoint.session_index:
            continue

        if session.close_state == "unknown" or session.close_micros is None or session.close_segment is None:
            points.append(
                EmaPoint(
                    session_id=session.session_id,
                    session_index=session.session_index,
                    period=period,
                    value=None,
                    status="missing_inputs",
                    close_segment=None,
                    input_close_state=session.close_state,
                    reason_codes=("unknown_close",),
                )
            )
            segment = None
            close_count = 0
            previous_ema = None
            seed_closes = []
            continue

        if session.close_segment != segment:
            segment = session.close_segment
            close_count = 0
            previous_ema = None
            seed_closes = []

        close_count += 1
        close = _xof(session.close_micros)
        if previous_ema is None:
            seed_closes.append(close)
            if close_count == period:
                previous_ema = sum(seed_closes) / period
            elif close_count > period:
                raise EmaCalculationError("EMA recurrence lost its seed state")
        else:
            previous_ema = multiplier * close + (1.0 - multiplier) * previous_ema

        value = previous_ema if close_count >= period else None
        status: EmaStatus = "assessable" if close_count >= WARM_UP_SESSIONS else "warming_up"
        points.append(
            EmaPoint(
                session_id=session.session_id,
                session_index=session.session_index,
                period=period,
                value=value,
                status=status,
                close_segment=segment,
                input_close_state=session.close_state,
            )
        )
        if value is not None:
            checkpoints.append(
                EmaCheckpoint(
                    input_snapshot_id=snapshot.snapshot_id,
                    rule_version=rule_version,
                    period=period,
                    session_index=session.session_index,
                    close_segment=segment,
                    close_count=close_count,
                    value=value,
                )
            )

    return EmaSeries(
        input_snapshot_id=snapshot.snapshot_id,
        rule_version=rule_version,
        period=period,
        points=tuple(points),
        checkpoints=tuple(checkpoints),
    )


def calculate_ema20_50(
    snapshot: AnalyticalInputSnapshot, *, rule_version: OpaqueIdentifier
) -> tuple[EmaSeries, EmaSeries]:
    """Return the approved fast and slow EMA series from the same input snapshot."""

    return (
        calculate_ema(snapshot, period=20, rule_version=rule_version),
        calculate_ema(snapshot, period=50, rule_version=rule_version),
    )
