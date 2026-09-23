"""Tests for deterministic point-in-time technical-analysis inputs."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

import pytest

from backend.analysis.inputs import InputSnapshotError, build_analytical_input_snapshot
from backend.contracts.analysis import NormalizedPrice, NormalizedSession, Provenance, Revision
from backend.contracts.scalars import NonNegativeMoney

NOW = datetime(2026, 9, 23, 16, tzinfo=timezone.utc)


def money(amount: str) -> NonNegativeMoney:
    return NonNegativeMoney(amount=amount, currency="XOF")


def revision(number: int, known_at: datetime = NOW) -> Revision:
    return Revision(
        revision=number,
        known_at=known_at,
        provenance=Provenance(source_id=f"source-{number}", collected_at=known_at, basis="actual"),
    )


def session(
    day: int,
    index: int | None,
    *,
    status: Literal["trading", "holiday", "suspended", "unknown"] = "trading",
    known_at: datetime = NOW,
) -> NormalizedSession:
    return NormalizedSession(
        calendar_version="calendar-v1",
        session_id=f"session-{day}",
        session_date=date(2026, 9, day),
        session_index=index,
        exchange_timezone="Africa/Abidjan",
        status=status,
        official_close_at=NOW if status == "trading" else None,
        source_evidence=(Provenance(source_id="calendar-source", collected_at=known_at, basis="actual"),),
        reason_codes=() if status == "trading" else ("calendar_status",),
        revision=revision(day if index is None else index, known_at),
    )


def price(
    day: int,
    *,
    close: str | None = "100",
    high: str | None = "110",
    low: str | None = "90",
    status: Literal["traded", "confirmed_no_trade", "unknown"] = "traded",
    basis: str = "basis-v1",
    symbol: str = "NSI",
    number: int = 1,
    known_at: datetime = NOW,
) -> NormalizedPrice:
    return NormalizedPrice(
        symbol=symbol,
        session_date=date(2026, 9, day),
        close=None if close is None else money(close),
        high=None if high is None else money(high),
        low=None if low is None else money(low),
        volume=10 if status == "traded" else None,
        trade_status=status,
        basis="actual",
        original_source_date=date(2026, 9, day),
        price_basis_ref=basis,
        validated_available_at=known_at if status == "traded" else None,
        suspension_status="not_suspended",
        reason_codes=() if status == "traded" else ("no_trade_confirmed",),
        revision=revision(number, known_at),
    )


def test_snapshot_uses_authoritative_sessions_and_explicit_no_trade_model() -> None:
    snapshot = build_analytical_input_snapshot(
        symbol="NSI",
        as_of=NOW,
        sessions=(session(21, 1), session(22, 2, status="holiday"), session(23, 3)),
        prices=(
            price(21, close="100", high="105", low="95"),
            price(23, close=None, high=None, low=None, status="confirmed_no_trade"),
        ),
    )

    assert [item.session_date.day for item in snapshot.sessions] == [21, 23]
    first, second = snapshot.sessions
    assert first.close_state == "traded"
    assert first.true_range_state == "unknown"
    assert second.close_state == "carried"
    assert second.close_micros == first.close_micros
    assert second.true_range_state == "modeled_zero_range"
    assert second.true_range_micros == 0


def test_suspended_sessions_remain_explicit_for_no_trade_and_unknown_inputs() -> None:
    snapshot = build_analytical_input_snapshot(
        symbol="NSI",
        as_of=NOW,
        sessions=(
            session(21, 1),
            session(22, 2, status="suspended"),
            session(23, 3, status="suspended"),
        ),
        prices=(
            price(21),
            price(22, close=None, high=None, low=None, status="confirmed_no_trade"),
        ),
    )

    first, confirmed_no_trade, unavailable = snapshot.sessions
    assert [item.session_date.day for item in snapshot.sessions] == [21, 22, 23]
    assert confirmed_no_trade.close_state == "carried"
    assert confirmed_no_trade.true_range_state == "modeled_zero_range"
    assert unavailable.close_state == "unknown"
    assert unavailable.true_range_state == "unknown"


def test_missing_observation_and_price_basis_change_break_only_dependent_chains() -> None:
    snapshot = build_analytical_input_snapshot(
        symbol="NSI",
        as_of=NOW,
        sessions=(session(21, 1), session(22, 2), session(23, 3), session(24, 4)),
        prices=(
            price(21),
            price(23, basis="basis-v2"),
            price(24, close="110", high=None, low=None),
        ),
    )

    first, missing, changed_basis, missing_range = snapshot.sessions
    assert first.close_segment == 1
    assert missing.close_state == "unknown"
    assert missing.true_range_state == "unknown"
    assert changed_basis.close_state == "traded"
    assert changed_basis.close_segment == 2
    assert changed_basis.true_range_state == "unknown"
    assert missing_range.close_state == "traded"
    assert missing_range.close_segment == 3
    assert missing_range.true_range_state == "unknown"


def test_known_at_selects_only_visible_revision_and_snapshot_is_stable() -> None:
    early = NOW - timedelta(hours=1)
    later = NOW + timedelta(hours=1)
    sessions = (session(21, 1, known_at=early),)
    old = price(21, close="100", number=1, known_at=early)
    correction = price(21, close="120", number=2, known_at=later)

    first = build_analytical_input_snapshot(symbol="NSI", as_of=NOW, sessions=sessions, prices=(old, correction))
    repeated = build_analytical_input_snapshot(symbol="NSI", as_of=NOW, sessions=sessions, prices=(correction, old))
    corrected = build_analytical_input_snapshot(symbol="NSI", as_of=later, sessions=sessions, prices=(old, correction))

    assert first.sessions[0].close_micros == money("100").micros
    assert first.snapshot_id == repeated.snapshot_id
    assert corrected.sessions[0].close_micros == money("120").micros
    assert corrected.snapshot_id != first.snapshot_id


def test_other_symbols_cannot_multiply_or_fill_the_requested_symbol_grid() -> None:
    snapshot = build_analytical_input_snapshot(
        symbol="NSI",
        as_of=NOW,
        sessions=(session(21, 1), session(22, 2)),
        prices=(price(21), price(21, symbol="SIB"), price(22, symbol="SIB")),
    )

    assert len(snapshot.sessions) == 2
    assert snapshot.sessions[0].close_state == "traded"
    assert snapshot.sessions[1].close_state == "unknown"


def test_unknown_calendar_and_ambiguous_revisions_never_silently_choose_or_skip() -> None:
    with pytest.raises(InputSnapshotError, match="unknown session"):
        build_analytical_input_snapshot(
            symbol="NSI", as_of=NOW, sessions=(session(21, None, status="unknown"),), prices=()
        )

    with pytest.raises(InputSnapshotError, match="ambiguous revision"):
        build_analytical_input_snapshot(
            symbol="NSI",
            as_of=NOW,
            sessions=(session(21, 1),),
            prices=(price(21, number=1), price(21, close="110", number=1)),
        )
