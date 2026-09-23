"""Wilder ATR14 over versioned analytical true-range inputs."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from backend.analysis.inputs import AnalyticalInputSnapshot, SessionInput, TrueRangeState
from backend.contracts.scalars import OpaqueIdentifier

ATR_PERIOD = 14
WARM_UP_SESSIONS = 250
AtrStatus = Literal["warming_up", "assessable", "missing_inputs"]


class AtrCalculationError(ValueError):
    """Raised for invalid ATR inputs or replay anchors."""


@dataclass(frozen=True)
class AtrPoint:
    session_id: OpaqueIdentifier
    session_index: int
    value: float | None
    status: AtrStatus
    true_range: float | None
    true_range_state: TrueRangeState
    price_basis_ref: OpaqueIdentifier | None
    session_count: int
    valid_true_range_count: int
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AtrCheckpoint:
    input_snapshot_id: OpaqueIdentifier
    rule_version: OpaqueIdentifier
    session_index: int
    price_basis_ref: OpaqueIdentifier
    session_count: int
    valid_true_range_count: int
    average_true_range: float
    prefix_fingerprint: str


@dataclass(frozen=True)
class AtrSeries:
    input_snapshot_id: OpaqueIdentifier
    rule_version: OpaqueIdentifier
    points: tuple[AtrPoint, ...]
    checkpoints: tuple[AtrCheckpoint, ...]


def _fingerprint(sessions: tuple[SessionInput, ...], through: int) -> str:
    values = [
        f"{item.session_index}|{item.true_range_micros}|{item.true_range_state}|{item.price_basis_ref}"
        for item in sessions
        if item.session_index <= through
    ]
    return sha256("\n".join(values).encode()).hexdigest()


def calculate_atr14(
    snapshot: AnalyticalInputSnapshot,
    *,
    rule_version: OpaqueIdentifier,
    checkpoint: AtrCheckpoint | None = None,
) -> AtrSeries:
    """Calculate unrounded Wilder ATR14, optionally from a verified checkpoint."""

    sessions = snapshot.sessions
    if checkpoint is not None:
        if checkpoint.rule_version != rule_version:
            raise AtrCalculationError("checkpoint rule version must match the requested series")
        if checkpoint.prefix_fingerprint != _fingerprint(sessions, checkpoint.session_index):
            raise AtrCalculationError("checkpoint prefix differs from the requested input snapshot")
    points: list[AtrPoint] = []
    checkpoints: list[AtrCheckpoint] = []
    basis = checkpoint.price_basis_ref if checkpoint else None
    session_count = checkpoint.session_count if checkpoint else 0
    valid_count = checkpoint.valid_true_range_count if checkpoint else 0
    average = checkpoint.average_true_range if checkpoint else None
    seed: list[float] = []

    for item in sessions:
        if checkpoint is not None and item.session_index <= checkpoint.session_index:
            continue

        basis_changed = basis is not None and item.price_basis_ref != basis
        starts_segment = basis is None or basis_changed
        if starts_segment:
            basis = item.price_basis_ref
            session_count, valid_count, average, seed = 0, 0, None, []

        state = item.true_range_state
        true_range: float | None = None
        valid = state in {"observed", "modeled_zero_range"} and item.true_range_micros is not None
        if valid:
            if item.true_range_micros is None or item.true_range_micros < 0:
                raise AtrCalculationError("true range must be nonnegative")
            if state == "modeled_zero_range" and item.true_range_micros != 0:
                raise AtrCalculationError("modeled_zero_range must carry a zero true range")
            if state == "modeled_zero_range" and item.close_state != "carried":
                raise AtrCalculationError("modeled_zero_range requires a carried no-trade close")
            if state == "observed" and item.close_state != "traded":
                raise AtrCalculationError("observed true range requires a traded session")
            if item.price_basis_ref is None:
                valid = False
            else:
                true_range = item.true_range_micros / 1_000_000

        # The first close in a segment has no preceding close by definition. It
        # starts the session maturity count; later unknown TRs break the chain.
        initial_close = (
            starts_segment
            and item.close_state in {"traded", "carried"}
            and item.price_basis_ref is not None
        )
        if not valid and not initial_close:
            points.append(
                AtrPoint(
                    item.session_id, item.session_index, None, "missing_inputs", None,
                    state, item.price_basis_ref, 0, 0, ("unknown_true_range",),
                )
            )
            basis, session_count, valid_count, average, seed = None, 0, 0, None, []
            continue

        session_count += 1
        value: float | None = None
        if valid:
            assert true_range is not None
            valid_count += 1
            if average is None:
                seed.append(true_range)
                if len(seed) == ATR_PERIOD:
                    average = sum(seed) / ATR_PERIOD
                    value = average
                    seed = []
            else:
                average = ((ATR_PERIOD - 1) * average + true_range) / ATR_PERIOD
                value = average

        status: AtrStatus = "assessable" if session_count >= WARM_UP_SESSIONS else "warming_up"
        reasons = ("modeled_zero_range",) if state == "modeled_zero_range" else ()
        points.append(
            AtrPoint(
                item.session_id, item.session_index, value, status, true_range,
                state, item.price_basis_ref, session_count, valid_count, reasons,
            )
        )
        if value is not None and average is not None and basis is not None:
            checkpoints.append(
                AtrCheckpoint(
                    snapshot.snapshot_id, rule_version, item.session_index, basis,
                    session_count, valid_count, average,
                    _fingerprint(sessions, item.session_index),
                )
            )

    return AtrSeries(snapshot.snapshot_id, rule_version, tuple(points), tuple(checkpoints))
