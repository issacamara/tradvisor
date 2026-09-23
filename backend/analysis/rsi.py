"""Wilder RSI14 calculation over immutable analytical input snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from backend.analysis.inputs import AnalyticalInputSnapshot, CloseState, SessionInput
from backend.contracts.scalars import OpaqueIdentifier

RSI_PERIOD = 14
WARM_UP_SESSIONS = 250
RsiStatus = Literal["warming_up", "assessable", "missing_inputs"]


class RsiCalculationError(ValueError):
    """Raised for invalid RSI replay anchors."""


@dataclass(frozen=True)
class RsiPoint:
    session_id: OpaqueIdentifier
    session_index: int
    value: float | None
    status: RsiStatus
    close_segment: int | None
    input_close_state: CloseState
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RsiCheckpoint:
    input_snapshot_id: OpaqueIdentifier
    rule_version: OpaqueIdentifier
    session_index: int
    close_segment: int
    close_count: int
    previous_close: float
    average_gain: float
    average_loss: float
    prefix_fingerprint: str


@dataclass(frozen=True)
class RsiSeries:
    input_snapshot_id: OpaqueIdentifier
    rule_version: OpaqueIdentifier
    points: tuple[RsiPoint, ...]
    checkpoints: tuple[RsiCheckpoint, ...]


def _fingerprint(sessions: tuple[SessionInput, ...], through: int) -> str:
    values = [
        f"{item.session_index}|{item.close_micros}|{item.close_state}|{item.close_segment}|{item.price_basis_ref}"
        for item in sessions if item.session_index <= through
    ]
    return sha256("\n".join(values).encode()).hexdigest()


def _rsi(gain: float, loss: float) -> float:
    if loss == 0.0:
        return 100.0 if gain > 0.0 else 50.0
    if gain == 0.0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def calculate_rsi14(
    snapshot: AnalyticalInputSnapshot, *, rule_version: OpaqueIdentifier, checkpoint: RsiCheckpoint | None = None
) -> RsiSeries:
    """Calculate unrounded Wilder RSI14, optionally from a verified suffix anchor."""

    if checkpoint is not None and checkpoint.rule_version != rule_version:
        raise RsiCalculationError("checkpoint rule version must match the requested series")
    if checkpoint is not None and checkpoint.prefix_fingerprint != _fingerprint(snapshot.sessions, checkpoint.session_index):
        raise RsiCalculationError("checkpoint prefix differs from the requested input snapshot")

    points: list[RsiPoint] = []
    checkpoints: list[RsiCheckpoint] = []
    segment = checkpoint.close_segment if checkpoint else None
    count = checkpoint.close_count if checkpoint else 0
    previous = checkpoint.previous_close if checkpoint else None
    average_gain = checkpoint.average_gain if checkpoint else None
    average_loss = checkpoint.average_loss if checkpoint else None
    gains: list[float] = []
    losses: list[float] = []

    for item in snapshot.sessions:
        if checkpoint is not None and item.session_index <= checkpoint.session_index:
            continue
        if item.close_state == "unknown" or item.close_micros is None or item.close_segment is None:
            points.append(RsiPoint(item.session_id, item.session_index, None, "missing_inputs", None, item.close_state, ("unknown_close",)))
            segment = previous = average_gain = average_loss = None
            count = 0
            gains, losses = [], []
            continue
        if item.close_segment != segment:
            segment, previous, average_gain, average_loss, count = item.close_segment, None, None, None, 0
            gains, losses = [], []
        close = item.close_micros / 1_000_000
        count += 1
        value: float | None = None
        if previous is not None:
            delta = close - previous
            gain, loss = max(delta, 0.0), max(-delta, 0.0)
            if average_gain is None:
                gains.append(gain)
                losses.append(loss)
                if len(gains) == RSI_PERIOD:
                    average_gain, average_loss = sum(gains) / RSI_PERIOD, sum(losses) / RSI_PERIOD
                    value = _rsi(average_gain, average_loss)
            else:
                assert average_loss is not None
                average_gain = ((RSI_PERIOD - 1) * average_gain + gain) / RSI_PERIOD
                average_loss = ((RSI_PERIOD - 1) * average_loss + loss) / RSI_PERIOD
                value = _rsi(average_gain, average_loss)
        previous = close
        status: RsiStatus = "assessable" if count >= WARM_UP_SESSIONS else "warming_up"
        points.append(RsiPoint(item.session_id, item.session_index, value, status, segment, item.close_state))
        if value is not None and average_gain is not None and average_loss is not None:
            checkpoints.append(RsiCheckpoint(snapshot.snapshot_id, rule_version, item.session_index, segment, count, close, average_gain, average_loss, _fingerprint(snapshot.sessions, item.session_index)))

    return RsiSeries(snapshot.snapshot_id, rule_version, tuple(points), tuple(checkpoints))
