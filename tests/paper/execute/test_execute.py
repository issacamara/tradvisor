from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from threading import RLock
from typing import Any, Literal

from backend.contracts.analysis import NormalizedSession, Provenance, Revision
from backend.contracts.paper import (
    CalendarCorrectionEvidence,
    ExecutionPrice,
    PaperExecution,
    PaperPosition,
    PaperOrder,
)
from backend.contracts.routes import CreatePaperOrderRequest
from backend.contracts.scalars import NonNegativeMoney, StartingCash
from backend.paper.accept import (
    AcceptanceEvidence,
    OrderAcceptanceError,
    RecommendationEvidence,
    accept_order,
)
from backend.paper.execute import (
    ExecutionEvidence,
    ExecutionRuntime,
    OrderExecutionResult,
    PriceCandidate,
    execute_pending_orders,
)
from backend.paper.holding_advice import HoldingAdvice
from backend.paper.setup import setup_portfolio
from backend.store.repositories import OwnerContext, PaperRepositories, VersionedDocument
from backend.store.transactions import Transaction
from tests.store.test_repositories import FakeStore

UTC = timezone.utc
NOW = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)


@dataclass
class EvidenceReader:
    evidence: ExecutionEvidence

    def load(self, transaction: Transaction, order: PaperOrder) -> ExecutionEvidence:
        del transaction, order
        return self.evidence


@dataclass
class AcceptanceReader:
    recommendation: RecommendationEvidence
    calendar_sessions: tuple[NormalizedSession, ...]
    advice: HoldingAdvice | None = None

    def load(
        self,
        transaction: Transaction,
        *,
        symbol: str,
        generation: str,
        now: datetime,
    ) -> AcceptanceEvidence:
        del transaction, symbol, generation, now
        return AcceptanceEvidence(self.recommendation, self.calendar_sessions, self.advice)


def _money(amount: str) -> NonNegativeMoney:
    return NonNegativeMoney(amount=amount, currency="XOF")


def _sessions() -> tuple[NormalizedSession, ...]:
    provenance = Provenance(source_id="calendar-source", collected_at=NOW, basis="actual")
    result = []
    for day, index in (
        (date(2026, 1, 2), 10),
        (date(2026, 1, 5), 11),
        (date(2026, 1, 6), 12),
        (date(2026, 1, 7), 13),
    ):
        result.append(
            NormalizedSession(
                calendar_version="calendar-v1",
                session_id=f"session-{day.isoformat()}",
                session_date=day,
                session_index=index,
                exchange_timezone="Africa/Abidjan",
                status="trading",
                official_close_at=datetime(day.year, day.month, day.day, 15, tzinfo=UTC),
                source_evidence=(provenance,),
                revision=Revision(revision=1, known_at=NOW, provenance=provenance),
            )
        )
    return tuple(result)


def _configured() -> tuple[FakeStore, PaperRepositories, str, str]:
    store = FakeStore()
    repositories = PaperRepositories(store, OwnerContext(uid="owner-1"))
    setup_portfolio(
        repositories,
        starting_cash=StartingCash(amount="100000", currency="XOF"),
        objective="growth",
        fee_rate_pct="0.5",
        fee_zero_confirmed=False,
        now=NOW,
    )
    control = repositories.get_control()
    assert control is not None
    assert control.record.active_generation is not None
    return store, repositories, str(control.record.active_generation), str(control.record.recovery_id)


def _request(
    generation: str,
    recovery_id: str,
    *,
    side: Literal["buy", "sell"] = "buy",
    quantity: int = 2,
) -> CreatePaperOrderRequest:
    issued_ms = int(NOW.timestamp() * 1000)
    return CreatePaperOrderRequest.model_validate(
        {
            "command": {
                "idempotency_key": f"{issued_ms}.{'a' * 32}",
                "recovery_id": recovery_id,
                "content_length": 100,
                "issued_at": NOW,
                "expected_generation": generation,
                "expected_state_version": 0,
            },
            "expected_generation": generation,
            "expected_state_version": 0,
            "recommendation_ref": "rec-1",
            "batch_id": "batch-1",
            "symbol": "NSI",
            "side": side,
            "quantity": quantity,
            "acknowledge_keep_override": False,
        }
    )


def _acceptance_reader(advice: HoldingAdvice | None = None) -> AcceptanceReader:
    sessions = _sessions()
    latest = sessions[0]
    assert latest.official_close_at is not None
    return AcceptanceReader(
        recommendation=RecommendationEvidence(
            reference="rec-1",
            batch_id="batch-1",
            symbol="NSI",
            session_date=latest.session_date,
            published_at=latest.official_close_at + timedelta(seconds=60),
            entry_action="buy",
            reference_close=_money("100"),
        ),
        calendar_sessions=sessions,
        advice=advice,
    )


def _price(
    *,
    revision: str = "price-1",
    close: str = "100",
    available_at: datetime = datetime(2026, 1, 6, 15, 0, tzinfo=UTC),
) -> ExecutionPrice:
    return ExecutionPrice(
        price_revision_id=revision,
        symbol="NSI",
        session_date=date(2026, 1, 6),
        close=_money(close),
        validated_available_at=available_at,
        source_evidence=(
            Provenance(source_id="price-source", collected_at=NOW, basis="actual"),
        ),
    )


def _calendar_correction() -> CalendarCorrectionEvidence:
    return CalendarCorrectionEvidence(
        original_calendar_version="calendar-v1",
        original_session_id="session-2026-01-06",
        correcting_calendar_version="calendar-v2",
        correcting_session_id="session-2026-01-07",
        corrected_at=NOW + timedelta(days=1),
        source_evidence=(
            Provenance(source_id="calendar-source", collected_at=NOW, basis="actual"),
        ),
    )


def _evidence(
    recovery_id: str,
    *,
    candidates: tuple[PriceCandidate, ...] = (),
    correction: CalendarCorrectionEvidence | None = None,
    missing_calendar: bool = False,
    maintenance: bool = False,
) -> ExecutionEvidence:
    all_sessions = _sessions()
    return ExecutionEvidence(
        runtime=ExecutionRuntime(recovery_id=recovery_id, maintenance=maintenance),
        active_calendar_version="calendar-v1",
        intended_session=None if missing_calendar else all_sessions[2],
        grace_session=None if missing_calendar else all_sessions[3],
        candidates=candidates,
        calendar_correction=correction,
    )


def _pending_order() -> tuple[FakeStore, PaperRepositories, PaperOrder, str]:
    store, repositories, generation, recovery_id = _configured()
    accepted = accept_order(
        repositories,
        _request(generation, recovery_id),
        _acceptance_reader(),
        now=NOW,
        order_id="order-1",
    )
    store.page_items = (accepted.order,)
    store.page_keys = (repositories.order_key(generation, accepted.order.order_id),)
    return store, repositories, accepted.order, recovery_id


def _pending_sell_order() -> tuple[FakeStore, PaperRepositories, PaperOrder, str]:
    store, repositories, generation, recovery_id = _configured()
    position = PaperPosition(
        generation=generation,
        symbol="NSI",
        quantity=2,
        reserved_sell_quantity=0,
        remaining_gross_cost=_money("200"),
        purchase_fees=_money("10"),
        opening_session=date(2026, 1, 2),
        high_water_close=_money("100"),
        evaluated_through_session=date(2026, 1, 2),
        trail_activated=False,
        exit_policy_ref="exit-policy-v1",
    )
    position_key = repositories.position_key(generation, "NSI")
    store.documents[position_key.path] = VersionedDocument(position_key, 1, 0, position)
    advice = HoldingAdvice(
        action="sell",
        generation=generation,
        state_version=0,
        exit_policy_ref="exit-policy-v1",
        evaluation_session=date(2026, 1, 2),
        sell_reasons=("fixed_loss",),
        unavailable_checks=(),
        high_water_close_micros=100_000_000,
        trail_activated=False,
        evaluated_through_session=date(2026, 1, 2),
    )
    accepted = accept_order(
        repositories,
        _request(generation, recovery_id, side="sell", quantity=2),
        _acceptance_reader(advice),
        now=NOW,
        order_id="order-sell-1",
    )
    store.page_items = (accepted.order,)
    store.page_keys = (repositories.order_key(generation, accepted.order.order_id),)
    return store, repositories, accepted.order, recovery_id


def _run(
    store: FakeStore,
    repositories: PaperRepositories,
    order: PaperOrder,
    recovery_id: str,
    evidence: ExecutionEvidence,
    *,
    now: datetime,
) -> tuple[OrderExecutionResult, ...]:
    return execute_pending_orders(
        repositories,
        EvidenceReader(evidence),
        now=now,
        expected_recovery_id=recovery_id,
        limit=10,
    )


def test_timely_price_executes_even_when_worker_runs_late() -> None:
    store, repositories, order, recovery_id = _pending_order()
    price = _price(available_at=order.grace_deadline_at)

    result = _run(
        store,
        repositories,
        order,
        recovery_id,
        _evidence(recovery_id, candidates=(PriceCandidate(price, 1, True),)),
        now=order.grace_deadline_at + timedelta(days=1),
    )[0]

    assert result.state == "executed"
    assert result.execution is not None
    assert result.execution.execution_price == price
    assert repositories.get_order(order.generation, order.order_id).record.status == "executed"  # type: ignore[union-attr]
    assert repositories.get_execution(order.generation, order.order_id) is not None
    assert repositories.get_cash_movement(order.generation, f"execution-{order.order_id}") is not None


def test_price_available_exactly_at_deadline_is_eligible() -> None:
    store, repositories, order, recovery_id = _pending_order()
    price = _price(available_at=order.grace_deadline_at)

    result = _run(
        store,
        repositories,
        order,
        recovery_id,
        _evidence(recovery_id, candidates=(PriceCandidate(price, 1, True),)),
        now=order.grace_deadline_at,
    )[0]

    assert result.state == "executed"


def test_late_invalid_replacement_cannot_fall_back_to_invalid_earlier_price() -> None:
    store, repositories, order, recovery_id = _pending_order()
    late_price = _price(
        revision="price-2",
        available_at=order.grace_deadline_at + timedelta(seconds=1),
    )
    invalidated_price = _price(revision="price-1", available_at=NOW)

    result = _run(
        store,
        repositories,
        order,
        recovery_id,
        _evidence(
            recovery_id,
            candidates=(
                PriceCandidate(invalidated_price, 1, False),
                PriceCandidate(late_price, 2, True),
            ),
        ),
        now=order.grace_deadline_at + timedelta(seconds=2),
    )[0]

    assert result.state == "expired"
    assert result.reason == "price_deadline_passed"
    assert repositories.get_execution(order.generation, order.order_id) is None


def test_unknown_price_waits_at_deadline_then_expires_once() -> None:
    store, repositories, order, recovery_id = _pending_order()
    evidence = _evidence(recovery_id)

    at_deadline = _run(
        store,
        repositories,
        order,
        recovery_id,
        evidence,
        now=order.grace_deadline_at,
    )[0]
    after_deadline = _run(
        store,
        repositories,
        order,
        recovery_id,
        evidence,
        now=order.grace_deadline_at + timedelta(microseconds=1),
    )[0]
    repeated = _run(
        store,
        repositories,
        order,
        recovery_id,
        evidence,
        now=order.grace_deadline_at + timedelta(days=1),
    )[0]

    assert at_deadline.state == "pending"
    assert after_deadline.state == "expired"
    assert repeated.reason == "already_terminal"
    assert repositories.get_summary(order.generation).record.pending_order_count == 0  # type: ignore[union-attr]


def test_calendar_correction_racing_fill_rejects_and_releases_without_fee() -> None:
    store, repositories, order, recovery_id = _pending_order()
    evidence = _evidence(
        recovery_id,
        candidates=(PriceCandidate(_price(), 1, True),),
        correction=_calendar_correction(),
    )
    summary_before = repositories.get_summary(order.generation).record  # type: ignore[union-attr]

    result = _run(
        store,
        repositories,
        order,
        recovery_id,
        evidence,
        now=NOW + timedelta(days=2),
    )[0]

    assert result.state == "rejected"
    assert result.reason == "calendar_corrected"
    assert repositories.get_execution(order.generation, order.order_id) is None
    summary_after = repositories.get_summary(order.generation).record  # type: ignore[union-attr]
    assert summary_after.cash == summary_before.cash
    assert summary_after.reserved_cash.micros == 0


def test_unknown_calendar_fails_closed_and_rejects_without_execution() -> None:
    store, repositories, order, recovery_id = _pending_order()

    result = _run(
        store,
        repositories,
        order,
        recovery_id,
        _evidence(recovery_id, missing_calendar=True),
        now=NOW,
    )[0]

    assert result.state == "rejected"
    assert result.reason == "calendar_unavailable"
    assert repositories.get_execution(order.generation, order.order_id) is None


def test_unaffordable_execution_rejects_fully_without_repricing_or_fees() -> None:
    store, repositories, order, recovery_id = _pending_order()
    expensive = _price(close="60000")
    cash_before = repositories.get_summary(order.generation).record.cash  # type: ignore[union-attr]

    result = _run(
        store,
        repositories,
        order,
        recovery_id,
        _evidence(recovery_id, candidates=(PriceCandidate(expensive, 1, True),)),
        now=order.grace_deadline_at + timedelta(days=1),
    )[0]

    assert result.state == "rejected"
    assert result.reason == "insufficient_cash_at_execution"
    assert repositories.get_summary(order.generation).record.cash == cash_before  # type: ignore[union-attr]
    assert repositories.get_execution(order.generation, order.order_id) is None
    assert repositories.get_cash_movement(order.generation, f"execution-{order.order_id}") is None


def test_stale_runtime_and_generation_never_mutate_the_pending_order() -> None:
    store, repositories, order, recovery_id = _pending_order()

    stale_runtime = _run(
        store,
        repositories,
        order,
        "different-recovery",
        _evidence("different-recovery", maintenance=True),
        now=order.grace_deadline_at + timedelta(days=1),
    )[0]

    assert stale_runtime.state == "skipped"
    assert repositories.get_order(order.generation, order.order_id).record.status == "pending"  # type: ignore[union-attr]


def test_duplicate_worker_delivery_has_one_ledger_effect() -> None:
    store, repositories, order, recovery_id = _pending_order()
    transaction_lock = RLock()
    original_run = store.run

    def serialized_run(
        callback: Callable[[Transaction], Any], *, max_attempts: int
    ) -> Any:
        with transaction_lock:
            return original_run(callback, max_attempts=max_attempts)

    store.run = serialized_run  # type: ignore[method-assign]
    evidence = _evidence(
        recovery_id,
        candidates=(PriceCandidate(_price(), 1, True),),
    )

    worker_time = order.grace_deadline_at + timedelta(days=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: _run(
                    store,
                    repositories,
                    order,
                    recovery_id,
                    evidence,
                    now=worker_time,
                )[0],
                range(2),
            )
        )

    assert [result.state for result in results].count("executed") == 1
    assert [result.reason for result in results].count("already_terminal") == 1
    assert repositories.get_summary(order.generation).record.pending_order_count == 0  # type: ignore[union-attr]
    execution_records = [
        document.record
        for path, document in store.documents.items()
        if path.endswith(f"/executions/{order.order_id}")
    ]
    assert len(execution_records) == 1
    assert isinstance(execution_records[0], PaperExecution)


def test_sell_execution_allocates_position_basis_and_applies_only_executed_fee() -> None:
    store, repositories, order, recovery_id = _pending_sell_order()
    evidence = _evidence(
        recovery_id,
        candidates=(PriceCandidate(_price(), 1, True),),
    )

    result = _run(
        store,
        repositories,
        order,
        recovery_id,
        evidence,
        now=order.grace_deadline_at + timedelta(days=1),
    )[0]

    assert result.state == "executed"
    assert result.execution is not None
    assert result.execution.fee_amount == _money("1")
    assert result.execution.allocated_cost == _money("200")
    assert result.execution.allocated_purchase_fees == _money("10")
    position = repositories.get_position(order.generation, order.symbol)
    assert position is not None
    assert position.record.quantity == 0
    assert position.record.purchase_fees == _money("0")
