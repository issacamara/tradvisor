"""Point-in-time, session-grid inputs for the technical analysis calculators.

The module deliberately stops before indicator arithmetic.  It turns normalized
calendar and price revisions into a deterministic snapshot, leaving later EMA,
RSI and ATR modules to consume the explicit chain and true-range states.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Callable, Hashable, Iterable, Literal, TypeVar, cast

from backend.contracts.analysis import NormalizedPrice, NormalizedSession
from backend.contracts.scalars import OpaqueIdentifier

INPUT_CONTRACT_VERSION = "analysis-input-v1"

CloseState = Literal["traded", "carried", "unknown"]
TrueRangeState = Literal["observed", "modeled_zero_range", "unknown"]
T = TypeVar("T", NormalizedPrice, NormalizedSession)


class InputSnapshotError(ValueError):
    """Raised when source revisions cannot produce a deterministic input view."""


@dataclass(frozen=True)
class SessionInput:
    """One authoritative trading session with explicit calculation-input states."""

    session_id: OpaqueIdentifier
    session_date: date
    session_index: int
    price_basis_ref: OpaqueIdentifier | None
    close_micros: int | None
    close_state: CloseState
    close_segment: int | None
    true_range_state: TrueRangeState
    true_range_micros: int | None
    source_price_revision: int | None


@dataclass(frozen=True)
class AnalyticalInputSnapshot:
    """Versioned, immutable input view selected only from facts known at ``as_of``."""

    snapshot_id: OpaqueIdentifier
    contract_version: str
    symbol: OpaqueIdentifier
    as_of: datetime
    calendar_version: OpaqueIdentifier
    sessions: tuple[SessionInput, ...]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise InputSnapshotError("as_of must be an explicit UTC timestamp")
    return value.astimezone(timezone.utc)


def _select_known_revisions(
    records: Iterable[T], *, as_of: datetime, key: Callable[[T], Hashable]
) -> dict[Hashable, T]:
    """Choose the latest known revision per logical key without source-order ties."""

    candidates: dict[Hashable, list[T]] = defaultdict(list)
    for record in records:
        if record.revision.known_at <= as_of:
            candidates[key(record)].append(record)

    selected: dict[Hashable, T] = {}
    for logical_key, versions in candidates.items():
        versions.sort(key=lambda value: (value.revision.known_at, value.revision.revision))
        latest = versions[-1]
        latest_key = (latest.revision.known_at, latest.revision.revision)
        if sum(
            (value.revision.known_at, value.revision.revision) == latest_key
            for value in versions
        ) != 1:
            raise InputSnapshotError(
                f"ambiguous revision for logical key {logical_key!r} at the requested as_of"
            )
        selected[logical_key] = latest
    return selected


def _price_key(price: NormalizedPrice) -> tuple[str, date]:
    return (price.symbol, price.session_date)


def _session_key(session: NormalizedSession) -> str:
    return session.session_id


def _input_snapshot_id(
    *, symbol: str, as_of: datetime, sessions: Iterable[NormalizedSession], prices: dict[tuple[str, date], NormalizedPrice]
) -> str:
    parts = [INPUT_CONTRACT_VERSION, symbol, as_of.isoformat()]
    for session in sessions:
        price = prices.get((symbol, session.session_date))
        parts.append(
            "|".join(
                (
                    session.session_id,
                    str(session.revision.revision),
                    session.revision.known_at.isoformat(),
                    "" if price is None else str(price.revision.revision),
                    "" if price is None else price.revision.known_at.isoformat(),
                )
            )
        )
    digest = sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"{INPUT_CONTRACT_VERSION}:{digest}"


def build_analytical_input_snapshot(
    *,
    symbol: OpaqueIdentifier,
    as_of: datetime,
    sessions: Iterable[NormalizedSession],
    prices: Iterable[NormalizedPrice],
) -> AnalyticalInputSnapshot:
    """Build a symbol's session-grid inputs from revisions known at ``as_of``.

    Holidays are absent from the grid.  An unresolved calendar session is a
    hard error rather than a silently skipped day; a missing price is retained
    as an explicit unknown observation.  No-trade carries and zero true ranges
    are modelled inputs, never synthetic OHLC observations.
    """

    as_of = _require_utc(as_of)
    selected_sessions = cast(
        dict[str, NormalizedSession],
        _select_known_revisions(sessions, as_of=as_of, key=_session_key),
    )
    by_date: dict[date, NormalizedSession] = {}
    for session in selected_sessions.values():
        existing = by_date.setdefault(session.session_date, session)
        if existing.session_id != session.session_id:
            raise InputSnapshotError(f"ambiguous calendar session for {session.session_date.isoformat()}")

    ordered_sessions = tuple(
        sorted(
            (session for session in by_date.values() if session.status == "trading"),
            key=lambda session: (session.session_index, session.session_date, session.session_id),
        )
    )
    if any(session.status == "unknown" for session in by_date.values()):
        raise InputSnapshotError("calendar contains an unknown session; do not skip it")
    if len({session.session_index for session in ordered_sessions}) != len(ordered_sessions):
        raise InputSnapshotError("calendar has duplicate trading session indices")
    if any(
        earlier.session_index >= later.session_index
        for earlier, later in zip(ordered_sessions, ordered_sessions[1:])
    ):
        raise InputSnapshotError("calendar trading session indices are not strictly increasing")

    selected_prices = cast(
        dict[tuple[str, date], NormalizedPrice],
        _select_known_revisions(prices, as_of=as_of, key=_price_key),
    )

    inputs: list[SessionInput] = []
    prior_close: int | None = None
    prior_basis: str | None = None
    close_segment = 0
    for session in ordered_sessions:
        price = selected_prices.get((symbol, session.session_date))
        close_state: CloseState = "unknown"
        close_micros: int | None = None
        price_basis_ref: str | None = None
        source_price_revision: int | None = None
        true_range_state: TrueRangeState = "unknown"
        true_range_micros: int | None = None

        if price is not None:
            price_basis_ref = price.price_basis_ref
            source_price_revision = price.revision.revision
            comparable = prior_close is not None and prior_basis == price.price_basis_ref
            if price.trade_status == "traded" and price.close is not None and price.close.micros > 0:
                close_micros = price.close.micros
                close_state = "traded"
                if prior_close is None or not comparable:
                    close_segment += 1
                if (
                    comparable
                    and price.high is not None
                    and price.low is not None
                    and price.low.micros <= price.close.micros <= price.high.micros
                    and price.low.micros > 0
                ):
                    assert prior_close is not None
                    true_range_state = "observed"
                    true_range_micros = max(
                        price.high.micros - price.low.micros,
                        abs(price.high.micros - prior_close),
                        abs(price.low.micros - prior_close),
                    )
            elif price.trade_status == "confirmed_no_trade" and comparable:
                close_micros = prior_close
                close_state = "carried"
                true_range_state = "modeled_zero_range"
                true_range_micros = 0

        if close_state == "unknown":
            prior_close = None
            prior_basis = None
            segment: int | None = None
        else:
            prior_close = close_micros
            prior_basis = price_basis_ref
            segment = close_segment

        inputs.append(
            SessionInput(
                session_id=session.session_id,
                session_date=session.session_date,
                session_index=session.session_index,
                price_basis_ref=price_basis_ref,
                close_micros=close_micros,
                close_state=close_state,
                close_segment=segment,
                true_range_state=true_range_state,
                true_range_micros=true_range_micros,
                source_price_revision=source_price_revision,
            )
        )

    calendar_versions = {session.calendar_version for session in by_date.values()}
    if len(calendar_versions) != 1:
        raise InputSnapshotError("snapshot requires one selected calendar version")
    calendar_version = next(iter(calendar_versions), "empty-calendar")
    return AnalyticalInputSnapshot(
        snapshot_id=_input_snapshot_id(
            symbol=symbol,
            as_of=as_of,
            sessions=ordered_sessions,
            prices=selected_prices,
        ),
        contract_version=INPUT_CONTRACT_VERSION,
        symbol=symbol,
        as_of=as_of,
        calendar_version=calendar_version,
        sessions=tuple(inputs),
    )
