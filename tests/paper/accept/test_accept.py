from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.contracts.analysis import NormalizedSession, Provenance
from backend.contracts.paper import PaperPosition
from backend.contracts.routes import CreatePaperOrderRequest
from backend.contracts.scalars import NonNegativeMoney, StartingCash
from backend.paper.accept import (
    AcceptanceEvidence,
    OrderAcceptanceError,
    RecommendationEvidence,
    accept_order,
)
from backend.paper.holding_advice import HoldingAdvice
from backend.paper.setup import setup_portfolio
from backend.store.repositories import (
    OwnerContext,
    PaperRepositories,
    WriteRequest,
)
from tests.store.test_repositories import FakeStore

UTC = timezone.utc
NOW = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
OWNER = "owner-1"


def money(amount: str) -> NonNegativeMoney:
    return NonNegativeMoney(amount=amount, currency="XOF")


def starting_cash(amount: str) -> StartingCash:
    return StartingCash(amount=amount, currency="XOF")


def session(day: date, index: int, close_hour: int = 15) -> NormalizedSession:
    return NormalizedSession(
        calendar_version="calendar-v1",
        session_id=f"session-{day.isoformat()}",
        session_date=day,
        session_index=index,
        exchange_timezone="Africa/Abidjan",
        status="trading",
        official_close_at=datetime(day.year, day.month, day.day, close_hour, tzinfo=UTC),
        source_evidence=(
            Provenance(source_id="calendar-source", collected_at=NOW, basis="actual"),
        ),
        revision={
            "revision": 1,
            "known_at": NOW,
            "provenance": Provenance(
                source_id="calendar-source", collected_at=NOW, basis="actual"
            ),
        },
    )


def sessions() -> tuple[NormalizedSession, ...]:
    return (
        session(date(2026, 1, 2), 10),
        session(date(2026, 1, 5), 11),
        session(date(2026, 1, 6), 12),
        session(date(2026, 1, 7), 13),
    )


@dataclass
class EvidenceReader:
    recommendation: RecommendationEvidence
    calendar_sessions: tuple[NormalizedSession, ...]
    holding_advice: HoldingAdvice | None = None

    def load(self, transaction, *, symbol, generation, now) -> AcceptanceEvidence:
        return AcceptanceEvidence(
            self.recommendation,
            self.calendar_sessions,
            self.holding_advice,
        )


def configured(cash: str = "100000") -> tuple[FakeStore, PaperRepositories, str, str]:
    store = FakeStore()
    repositories = PaperRepositories(store, OwnerContext(uid=OWNER))
    setup_portfolio(
        repositories,
        starting_cash=starting_cash(cash),
        objective="growth",
        fee_rate_pct="0.5",
        fee_zero_confirmed=False,
        now=NOW,
    )
    control = repositories.get_control()
    assert control is not None
    return store, repositories, str(control.record.active_generation), str(control.record.recovery_id)


def request(
    generation: str,
    recovery_id: str,
    *,
    side: str = "buy",
    recommendation_ref: str = "rec-1",
    batch_id: str = "batch-1",
    acknowledged: bool = False,
    quantity: int = 2,
    now: datetime = NOW,
) -> CreatePaperOrderRequest:
    issued_ms = int(now.timestamp() * 1000)
    return CreatePaperOrderRequest.model_validate(
        {
            "command": {
                "idempotency_key": f"{issued_ms}.{'a' * 32}",
                "recovery_id": recovery_id,
                "content_length": 100,
                "issued_at": now,
                "expected_generation": generation,
                "expected_state_version": 0,
            },
            "expected_generation": generation,
            "expected_state_version": 0,
            "recommendation_ref": recommendation_ref,
            "batch_id": batch_id,
            "symbol": "NSI",
            "side": side,
            "quantity": quantity,
            "acknowledge_keep_override": acknowledged,
        }
    )


def reader(*, entry_action: str = "buy", ref: str = "rec-1", advice=None) -> EvidenceReader:
    latest = sessions()[0]
    recommendation = RecommendationEvidence(
        reference=ref,
        batch_id="batch-1",
        symbol="NSI",
        session_date=latest.session_date,
        published_at=latest.official_close_at + timedelta(seconds=60),
        entry_action=entry_action,
        reference_close=money("100"),
    )
    return EvidenceReader(recommendation, sessions(), advice)


def test_buy_uses_fresh_recommendation_and_reserves_gross_plus_frozen_fee() -> None:
    _, repositories, generation, recovery_id = configured()
    result = accept_order(
        repositories,
        request(generation, recovery_id),
        reader(),
        now=NOW,
        order_id="order-1",
    )

    assert result.order.status == "pending"
    assert result.order.reserved_cash == money("201")
    assert result.order.fee_rate_pct == "0.5"
    assert result.order.intended_session == date(2026, 1, 6)
    assert result.order.grace_deadline_at == datetime(2026, 1, 7, 15, 1, tzinfo=UTC)
    summary = repositories.get_summary(generation)
    assert summary is not None
    assert summary.record.reserved_cash == money("201")
    assert summary.record.pending_order_count == 1


def test_order_retry_replays_one_atomic_reservation_and_receipt() -> None:
    _, repositories, generation, recovery_id = configured()
    command = request(generation, recovery_id)
    first = accept_order(repositories, command, reader(), now=NOW, order_id="order-1")
    replay = accept_order(repositories, command, reader(), now=NOW, order_id="order-2")

    assert replay.order.order_id == first.order.order_id
    assert replay.receipt.replayed is True
    summary = repositories.get_summary(generation)
    assert summary is not None
    assert summary.record.reserved_cash == money("201")
    assert summary.record.pending_order_count == 1


@pytest.mark.parametrize(
    ("requested_ref", "active_ref", "entry", "expected_code"),
    [
        ("rec-old", "rec-1", "buy", "recommendation_stale"),
        ("rec-1", "rec-1", "not_buy", "recommendation_stale"),
    ],
)
def test_stale_or_ineligible_buy_does_not_write(
    requested_ref: str, active_ref: str, entry: str, expected_code: str
) -> None:
    _, repositories, generation, recovery_id = configured()
    with pytest.raises(OrderAcceptanceError) as error:
        accept_order(
            repositories,
            request(generation, recovery_id, recommendation_ref=requested_ref),
            reader(entry_action=entry, ref=active_ref),
            now=NOW,
        )
    assert error.value.code == expected_code
    assert repositories.get_summary(generation).record.pending_order_count == 0  # type: ignore[union-attr]


def test_insufficient_cash_rejects_fully_without_partial_reservation() -> None:
    _, repositories, generation, recovery_id = configured(cash="100000")
    with pytest.raises(OrderAcceptanceError, match="Available cash") as error:
        accept_order(
            repositories,
            request(generation, recovery_id, quantity=2000),
            reader(),
            now=NOW,
        )
    assert error.value.code == "insufficient_cash"
    summary = repositories.get_summary(generation)
    assert summary is not None
    assert summary.record.reserved_cash.micros == 0
    assert summary.record.pending_order_count == 0


def test_sell_keep_requires_acknowledgment_and_records_immutable_advice() -> None:
    from backend.paper.holding_advice import HoldingAdvice

    _, repositories, generation, recovery_id = configured()
    position = PaperPosition(
        generation=generation,
        symbol="NSI",
        quantity=5,
        reserved_sell_quantity=0,
        remaining_gross_cost=money("500"),
        purchase_fees=money("0"),
        opening_session=date(2025, 12, 1),
        high_water_close=None,
        evaluated_through_session=date(2026, 1, 2),
        trail_activated=False,
        exit_policy_ref="exit-policy-v1",
    )
    repositories.transact(
        lambda transaction: repositories.write_in_transaction(
            transaction,
            key=repositories.position_key(generation, "NSI"),
            record=position,
            schema_version=1,
            expected_state_version=None,
        )
    )
    advice = HoldingAdvice(
        action="keep",
        generation=generation,
        state_version=0,
        exit_policy_ref="exit-policy-v1",
        evaluation_session=date(2026, 1, 2),
        sell_reasons=(),
        unavailable_checks=(),
        high_water_close_micros=None,
        trail_activated=False,
        evaluated_through_session=date(2026, 1, 2),
    )
    evidence = reader(entry_action="not_buy", advice=advice)
    with pytest.raises(OrderAcceptanceError) as error:
        accept_order(repositories, request(generation, recovery_id, side="sell"), evidence, now=NOW)
    assert error.value.code == "override_acknowledgment_required"
    assert repositories.get_position(generation, "NSI").record.reserved_sell_quantity == 0  # type: ignore[union-attr]

    accepted = accept_order(
        repositories,
        request(generation, recovery_id, side="sell", acknowledged=True),
        evidence,
        now=NOW,
        order_id="sell-1",
    )
    assert accepted.order.is_advice_override is True
    assert accepted.order.acknowledged_keep_override is True
    assert accepted.order.advice_action_at_acceptance == "keep"
    assert accepted.order.advice_evaluation_session == date(2026, 1, 2)
    assert repositories.get_position(generation, "NSI").record.reserved_sell_quantity == 2  # type: ignore[union-attr]


def test_sell_rejects_stale_advice_even_with_acknowledgment() -> None:
    from backend.paper.holding_advice import HoldingAdvice

    _, repositories, generation, recovery_id = configured()
    advice = HoldingAdvice(
        action="sell",
        generation=generation,
        state_version=0,
        exit_policy_ref="exit-policy-v1",
        evaluation_session=date(2025, 12, 31),
        sell_reasons=("fixed_loss",),
        unavailable_checks=(),
        high_water_close_micros=None,
        trail_activated=False,
        evaluated_through_session=date(2025, 12, 31),
    )
    with pytest.raises(OrderAcceptanceError) as error:
        accept_order(
            repositories,
            request(generation, recovery_id, side="sell", acknowledged=True),
            reader(entry_action="not_buy", advice=advice),
            now=NOW,
        )
    assert error.value.code == "recommendation_stale"
