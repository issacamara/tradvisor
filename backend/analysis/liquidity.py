"""Complete-window traded-value liquidity calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from backend.analysis.inputs import AnalyticalInputSnapshot
from backend.contracts.analysis import NormalizedPrice
from backend.contracts.scalars import OpaqueIdentifier

LIQUIDITY_WINDOW = 20
MINIMUM_MEDIAN_XOF = Decimal("5000000")
MINIMUM_TRADED_SESSIONS = 18
LiquidityBasis = Literal["actual", "estimated"]
LiquidityStatus = Literal["assessable", "unavailable"]


class LiquidityCalculationError(ValueError):
    """Raised when price evidence is ambiguous or inconsistent."""


@dataclass(frozen=True)
class LiquidityResult:
    input_snapshot_id: OpaqueIdentifier
    status: LiquidityStatus
    median_xof: Decimal | None
    traded_session_count: int | None
    basis: LiquidityBasis | None
    eligible: bool | None
    window_session_ids: tuple[OpaqueIdentifier, ...]
    evidence_refs: tuple[OpaqueIdentifier, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CurrentTradeGate:
    status: Literal["pass", "fail", "unknown"]
    evidence_refs: tuple[OpaqueIdentifier, ...]
    reason_codes: tuple[str, ...]


def _median_xof(values_micros: list[int]) -> Decimal:
    ordered = sorted(values_micros)
    middle = LIQUIDITY_WINDOW // 2
    return Decimal(ordered[middle - 1] + ordered[middle]) / Decimal(2_000_000)


def _selected_prices(
    snapshot: AnalyticalInputSnapshot, prices: tuple[NormalizedPrice, ...]
) -> dict[str, NormalizedPrice]:
    by_key: dict[tuple[str, date], list[NormalizedPrice]] = {}
    for price in prices:
        if price.symbol != snapshot.symbol:
            continue
        key = (price.symbol, price.session_date)
        by_key.setdefault(key, []).append(price)

    selected: dict[str, NormalizedPrice] = {}
    for session in snapshot.sessions:
        candidates = by_key.get((snapshot.symbol, session.session_date), [])
        matching = [
            price
            for price in candidates
            if price.revision.revision == session.source_price_revision
        ]
        if len(matching) > 1:
            raise LiquidityCalculationError("duplicate selected price revision for a snapshot session")
        if matching:
            selected[session.session_id] = matching[0]
    return selected


def calculate_liquidity(
    snapshot: AnalyticalInputSnapshot,
    prices: tuple[NormalizedPrice, ...],
) -> LiquidityResult:
    """Calculate the last 20-session median and confirmed trading frequency.

    Price records must be the normalized revisions available to the snapshot.
    Actual turnover is used only when complete.  An explicit no-trade row with
    positive actual turnover invalidates the whole result and blocks fallback.
    """

    sessions = snapshot.sessions[-LIQUIDITY_WINDOW:]
    session_ids = tuple(item.session_id for item in sessions)
    if len(sessions) < LIQUIDITY_WINDOW:
        return LiquidityResult(
            snapshot.snapshot_id, "unavailable", None, None, None, None,
            session_ids, (), ("history_incomplete",),
        )

    selected = _selected_prices(snapshot, prices)
    rows = [selected.get(item.session_id) for item in sessions]
    evidence = tuple(
        dict.fromkeys(
            row.revision.provenance.source_id for row in rows if row is not None
        )
    )

    for row in rows:
        if (
            row is not None
            and row.trade_status == "confirmed_no_trade"
            and row.actual_xof_turnover is not None
            and row.actual_xof_turnover.micros > 0
        ):
            return LiquidityResult(
                snapshot.snapshot_id, "unavailable", None, None, None, None,
                session_ids, evidence, ("actual_turnover_conflicts_with_no_trade",),
            )

    reasons: list[str] = []
    actual_complete = all(
        row is not None
        and (
            row.actual_xof_turnover is not None
            or row.trade_status == "confirmed_no_trade"
        )
        for row in rows
    )

    if actual_complete:
        values_micros = []
        for row in rows:
            assert row is not None
            if row.trade_status == "confirmed_no_trade":
                values_micros.append(0)
            else:
                assert row.actual_xof_turnover is not None
                values_micros.append(row.actual_xof_turnover.micros)
        basis: LiquidityBasis = "actual"
    else:
        if any(row is None for row in rows):
            reasons.append("missing_price_observation")
        if any(row is not None and row.trade_status == "unknown" for row in rows):
            reasons.append("trade_status_unknown")
        traded_rows = [row for row in rows if row is not None and row.trade_status == "traded"]
        price_bases = {row.price_basis_ref for row in traded_rows}
        estimated_complete = all(
            row is not None
            and (
                row.trade_status == "confirmed_no_trade"
                or (
                    row.trade_status == "traded"
                    and row.close is not None
                    and row.volume is not None
                    and row.basis == "actual"
                    and row.original_source_date == row.session_date
                )
            )
            for row in rows
        )
        if not estimated_complete:
            reasons.append("estimated_inputs_incomplete")
        if len(price_bases) != 1:
            reasons.append("incompatible_price_basis")
        if not estimated_complete or len(price_bases) != 1:
            return LiquidityResult(
                snapshot.snapshot_id, "unavailable", None, None, None, None,
                session_ids, evidence, tuple(dict.fromkeys(reasons)),
            )
        values_micros = []
        for row in rows:
            assert row is not None
            if row.trade_status == "confirmed_no_trade":
                values_micros.append(0)
            else:
                assert row.close is not None and row.volume is not None
                values_micros.append(row.close.micros * row.volume)
        basis = "estimated"

    statuses_known = all(row is not None and row.trade_status != "unknown" for row in rows)
    trade_count = (
        sum(row is not None and row.trade_status == "traded" for row in rows)
        if statuses_known
        else None
    )
    median = _median_xof(values_micros)
    if not statuses_known:
        reasons.append("trade_status_unknown")
    if median < MINIMUM_MEDIAN_XOF:
        reasons.append("median_below_threshold")
    if trade_count is not None and trade_count < MINIMUM_TRADED_SESSIONS:
        reasons.append("traded_sessions_below_threshold")
    eligible = (
        None
        if trade_count is None
        else median >= MINIMUM_MEDIAN_XOF and trade_count >= MINIMUM_TRADED_SESSIONS
    )
    return LiquidityResult(
        snapshot.snapshot_id, "assessable", median, trade_count, basis, eligible,
        session_ids, evidence, tuple(reasons),
    )


def evaluate_current_trade_gate(price: NormalizedPrice | None) -> CurrentTradeGate:
    """Evaluate genuine current-session trade and suspension independently."""

    if price is None:
        return CurrentTradeGate("unknown", (), ("current_price_missing",))
    evidence = tuple(
        dict.fromkeys(
            (
                price.revision.provenance.source_id,
                *(item.source_id for item in price.suspension_evidence),
            )
        )
    )
    reasons: list[str] = []
    if price.trade_status == "unknown":
        reasons.append("current_trade_status_unknown")
    elif price.trade_status == "confirmed_no_trade":
        reasons.append("no_current_trade")
    elif price.close is None or price.close.micros <= 0:
        reasons.append("genuine_current_close_missing")
    if price.suspension_status == "unknown":
        reasons.append("current_suspension_status_unknown")
    elif price.suspension_status == "suspended":
        reasons.append("current_session_suspended")
    if reasons:
        unknown = any(reason.endswith("unknown") or reason.endswith("missing") for reason in reasons)
        return CurrentTradeGate("unknown" if unknown else "fail", evidence, tuple(reasons))
    return CurrentTradeGate("pass", evidence, ())
