"""Transactional execution and expiry of recommendation-linked paper orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

from backend.contracts.analysis import NormalizedSession
from backend.contracts.paper import (
    CalendarCorrectionEvidence,
    CashMovement,
    ExecutionPrice,
    PaperExecution,
    PaperOrder,
    PaperPosition,
    PortfolioControl,
    PortfolioSummary,
)
from backend.contracts.scalars import NonNegativeMoney, OpaqueIdentifier, SignedMoney
from backend.paper.accounting import (
    PositionAccounting,
    apply_buy,
    apply_sell,
    calculate_execution_fee_micros,
)
from backend.paper.holding_advice import V1_EXIT_POLICY_REF
from backend.store.repositories import (
    MAX_PAGE_SIZE,
    GenerationConflict,
    PaperRepositories,
    VersionedDocument,
    WriteRequest,
)
from backend.store.transactions import Transaction

UTC = timezone.utc
ORDER_SCHEMA_VERSION = 1
EXECUTION_SCHEMA_VERSION = 1
COMPLETION_GRACE = timedelta(seconds=60)
RecordT = TypeVar("RecordT", bound=BaseModel)
ExecutionState = Literal["executed", "rejected", "expired", "pending", "skipped"]


@dataclass(frozen=True, slots=True)
class ExecutionRuntime:
    recovery_id: OpaqueIdentifier
    maintenance: bool


@dataclass(frozen=True, slots=True)
class PriceCandidate:
    price: ExecutionPrice
    sequence: int
    valid: bool


@dataclass(frozen=True, slots=True)
class ExecutionEvidence:
    """Control and immutable price evidence read inside the caller's transaction."""

    runtime: ExecutionRuntime | None
    active_calendar_version: OpaqueIdentifier | None
    intended_session: NormalizedSession | None
    grace_session: NormalizedSession | None
    candidates: tuple[PriceCandidate, ...]
    calendar_correction: CalendarCorrectionEvidence | None = None


class ExecutionEvidenceReader(Protocol):
    """Read current runtime, calendar, revision, and validity controls transactionally."""

    def load(self, transaction: Transaction, order: PaperOrder) -> ExecutionEvidence: ...


@dataclass(frozen=True, slots=True)
class OrderExecutionResult:
    order_id: OpaqueIdentifier
    state: ExecutionState
    reason: str | None = None
    execution: PaperExecution | None = None


def execute_pending_orders(
    repositories: PaperRepositories,
    evidence_reader: ExecutionEvidenceReader,
    *,
    now: datetime,
    expected_recovery_id: OpaqueIdentifier,
    limit: int = MAX_PAGE_SIZE,
) -> tuple[OrderExecutionResult, ...]:
    """Process the oldest bounded page; every candidate is rechecked transactionally."""

    now = _as_utc(now)
    if not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    control = repositories.get_control()
    if control is None or control.record.active_generation is None:
        return ()
    generation = control.record.active_generation
    page = repositories._page(
        "orders",
        generation,
        PaperOrder,
        limit=limit,
        cursor=None,
        order_by=(("accepted_at", "asc"), ("order_id", "asc")),
        filters=(("status", "==", "pending"),),
    )
    return tuple(
        _execute_one(
            repositories,
            order,
            evidence_reader,
            now=now,
            expected_recovery_id=expected_recovery_id,
        )
        for order in page.items
    )


def _execute_one(
    repositories: PaperRepositories,
    candidate: PaperOrder,
    evidence_reader: ExecutionEvidenceReader,
    *,
    now: datetime,
    expected_recovery_id: OpaqueIdentifier,
) -> OrderExecutionResult:
    store = repositories._store
    result_execution: PaperExecution | None = None
    result_state: ExecutionState = "skipped"
    result_reason: str | None = None

    def transact(transaction: Transaction) -> None:
        nonlocal result_execution, result_state, result_reason
        result_execution = None
        result_state = "skipped"
        result_reason = None
        control_doc = store.get_in_transaction(transaction, repositories.control_key())
        summary_doc = store.get_in_transaction(
            transaction, repositories.generation_key(candidate.generation)
        )
        order_doc = store.get_in_transaction(
            transaction, repositories.order_key(candidate.generation, candidate.order_id)
        )
        if control_doc is None or summary_doc is None or order_doc is None:
            result_state = "skipped"
            result_reason = "state_missing"
            return
        control = _record(control_doc.record, PortfolioControl)
        summary = _record(summary_doc.record, PortfolioSummary)
        order = _record(order_doc.record, PaperOrder)
        if order.status != "pending":
            result_state = "skipped"
            result_reason = "already_terminal"
            return
        if control.active_generation != order.generation:
            result_state = "skipped"
            result_reason = "generation_superseded"
            return
        if control.recovery_id != expected_recovery_id:
            result_state = "skipped"
            result_reason = "recovery_superseded"
            return
        if summary.pending_order_count < 1:
            result_state = "skipped"
            result_reason = "resources_inconsistent"
            return

        evidence = evidence_reader.load(transaction, order)
        if (
            evidence.runtime is None
            or evidence.runtime.maintenance
            or evidence.runtime.recovery_id != control.recovery_id
        ):
            result_state = "skipped"
            result_reason = "runtime_unavailable"
            return

        position_doc = store.get_in_transaction(
            transaction, repositories.position_key(order.generation, order.symbol)
        )
        position = (
            None
            if position_doc is None
            else _record(position_doc.record, PaperPosition)
        )
        correction_reason = _calendar_rejection(order, evidence)
        if correction_reason == "calendar_unavailable":
            result_state = "pending"
            result_reason = correction_reason
            return
        if correction_reason is not None:
            _write_terminal(
                repositories,
                transaction,
                order_doc,
                summary_doc,
                position_doc,
                order,
                summary,
                position,
                status="rejected",
                reason=correction_reason,
                now=now,
                correction=evidence.calendar_correction,
            )
            result_state = "rejected"
            result_reason = correction_reason
            return

        selected = _select_price(order, evidence, now)
        if selected is None:
            if now <= order.grace_deadline_at:
                result_state = "pending"
                result_reason = "price_not_yet_eligible"
                return
            _write_terminal(
                repositories,
                transaction,
                order_doc,
                summary_doc,
                position_doc,
                order,
                summary,
                position,
                status="expired",
                reason="price_deadline_passed",
                now=now,
            )
            result_state = "expired"
            result_reason = "price_deadline_passed"
            return

        if summary.reserved_cash.micros < _reserved_cash(order):
            result_state = "skipped"
            result_reason = "cash_reservation_inconsistent"
            return
        if order.side == "sell" and (
            position is None or position.reserved_sell_quantity < order.quantity
        ):
            result_state = "skipped"
            result_reason = "share_reservation_inconsistent"
            return

        fee = calculate_execution_fee_micros(
            quantity=order.quantity,
            closing_price_micros=selected.close.micros,
            fee_rate_pct=order.fee_rate_pct,
        )
        gross = order.quantity * selected.close.micros
        allocated_cost: NonNegativeMoney | None = None
        allocated_purchase_fees: NonNegativeMoney | None = None
        if order.side == "buy":
            own_reservation = _reserved_cash(order)
            available_after_other_reservations = summary.cash.micros - summary.reserved_cash.micros
            if gross + fee > own_reservation + available_after_other_reservations:
                _write_terminal(
                    repositories,
                    transaction,
                    order_doc,
                    summary_doc,
                    position_doc,
                    order,
                    summary,
                    position,
                    status="rejected",
                    reason="insufficient_cash_at_execution",
                    now=now,
                )
                result_state = "rejected"
                result_reason = "insufficient_cash_at_execution"
                return
            buy_accounting = apply_buy(
                PositionAccounting(
                    quantity=0 if position is None else position.quantity,
                    gross_cost_micros=0 if position is None else position.remaining_gross_cost.micros,
                    purchase_fee_micros=0 if position is None else position.purchase_fees.micros,
                ),
                quantity=order.quantity,
                closing_price_micros=selected.close.micros,
                purchase_fee_micros=fee,
            )
            next_position = PaperPosition(
                generation=order.generation,
                symbol=order.symbol,
                quantity=buy_accounting.position.quantity,
                reserved_sell_quantity=0 if position is None else position.reserved_sell_quantity,
                remaining_gross_cost=_money(buy_accounting.position.gross_cost_micros),
                purchase_fees=_money(buy_accounting.position.purchase_fee_micros),
                opening_session=(
                    order.intended_session if position is None else position.opening_session
                ),
                high_water_close=(
                    selected.close if position is None or position.high_water_close is None
                    else max(position.high_water_close, selected.close, key=lambda value: value.micros)
                ),
                evaluated_through_session=order.intended_session,
                trail_activated=False if position is None else position.trail_activated,
                exit_policy_ref=V1_EXIT_POLICY_REF if position is None else position.exit_policy_ref,
            )
            cash_effect = -(gross + fee)
        else:
            assert position is not None and position_doc is not None
            sell_accounting = apply_sell(
                PositionAccounting(
                    quantity=position.quantity,
                    gross_cost_micros=position.remaining_gross_cost.micros,
                    purchase_fee_micros=position.purchase_fees.micros,
                ),
                quantity=order.quantity,
                closing_price_micros=selected.close.micros,
                sell_fee_micros=fee,
            )
            if fee > gross:
                _write_terminal(
                    repositories,
                    transaction,
                    order_doc,
                    summary_doc,
                    position_doc,
                    order,
                    summary,
                    position,
                    status="rejected",
                    reason="insufficient_proceeds_at_execution",
                    now=now,
                )
                result_state = "rejected"
                result_reason = "insufficient_proceeds_at_execution"
                return
            next_position = position.model_copy(
                update={
                    "quantity": sell_accounting.position.quantity,
                    "reserved_sell_quantity": position.reserved_sell_quantity - order.quantity,
                    "remaining_gross_cost": _money(sell_accounting.position.gross_cost_micros),
                    "purchase_fees": _money(sell_accounting.position.purchase_fee_micros),
                    "high_water_close": (
                        None if sell_accounting.position.quantity == 0 else position.high_water_close
                    ),
                    "trail_activated": (
                        False if sell_accounting.position.quantity == 0 else position.trail_activated
                    ),
                    "evaluated_through_session": order.intended_session,
                }
            )
            allocated_cost = _money(sell_accounting.allocated_gross_cost_micros)
            allocated_purchase_fees = _money(sell_accounting.allocated_purchase_fee_micros)
            cash_effect = gross - fee

        next_summary = summary.model_copy(
            update={
                "cash": _money(summary.cash.micros + cash_effect),
                "reserved_cash": _money(summary.reserved_cash.micros - _reserved_cash(order)),
                "pending_order_count": summary.pending_order_count - 1,
                "state_version": summary.state_version + 1,
            }
        )
        execution = PaperExecution(
            execution_id=order.order_id,
            order_id=order.order_id,
            owner_uid=order.owner_uid,
            generation=order.generation,
            quantity=order.quantity,
            execution_price=selected,
            gross_amount=_money(gross),
            fee_amount=_money(fee),
            allocated_cost=allocated_cost,
            allocated_purchase_fees=allocated_purchase_fees,
            signed_cash_effect=SignedMoney(amount=_amount(cash_effect), currency="XOF"),
            processed_at=now,
        )
        movement = CashMovement(
            movement_id=f"execution-{order.order_id}",
            owner_uid=order.owner_uid,
            generation=order.generation,
            movement_type="buy_execution" if order.side == "buy" else "sell_execution",
            signed_amount=SignedMoney(amount=_amount(cash_effect), currency="XOF"),
            execution_id=execution.execution_id,
            occurred_at=selected.validated_available_at,
            processed_at=now,
        )
        requests = [
            WriteRequest(
                repositories.order_key(order.generation, order.order_id),
                order.model_copy(update={"status": "executed"}),
                ORDER_SCHEMA_VERSION,
                order_doc.state_version,
            ),
            WriteRequest(
                repositories.generation_key(order.generation),
                next_summary,
                summary_doc.schema_version,
                summary_doc.state_version,
            ),
            WriteRequest(
                repositories.execution_key(order.generation, order.order_id),
                execution,
                EXECUTION_SCHEMA_VERSION,
                None,
            ),
            WriteRequest(
                repositories.cash_movement_key(order.generation, movement.movement_id),
                movement,
                1,
                None,
            ),
        ]
        requests.append(
            WriteRequest(
                repositories.position_key(order.generation, order.symbol),
                next_position,
                1 if position_doc is None else position_doc.schema_version,
                None if position_doc is None else position_doc.state_version,
            )
        )
        repositories.write_many_in_transaction(transaction, requests=tuple(requests))
        result_state = "executed"
        result_execution = execution

    repositories.transact(transact)
    return OrderExecutionResult(candidate.order_id, result_state, result_reason, result_execution)


def _write_terminal(
    repositories: PaperRepositories,
    transaction: Transaction,
    order_doc: VersionedDocument[BaseModel],
    summary_doc: VersionedDocument[BaseModel],
    position_doc: VersionedDocument[BaseModel] | None,
    order: PaperOrder,
    summary: PortfolioSummary,
    position: PaperPosition | None,
    *,
    status: Literal["rejected", "expired"],
    reason: str,
    now: datetime,
    correction: CalendarCorrectionEvidence | None = None,
) -> None:
    if summary.pending_order_count < 1 or summary.reserved_cash.micros < _reserved_cash(order):
        raise GenerationConflict("pending order reservation is inconsistent")
    next_summary = summary.model_copy(
        update={
            "reserved_cash": _money(summary.reserved_cash.micros - _reserved_cash(order)),
            "pending_order_count": summary.pending_order_count - 1,
            "state_version": summary.state_version + 1,
        }
    )
    requests = [
        WriteRequest(
            repositories.order_key(order.generation, order.order_id),
            order.model_copy(
                update={
                    "status": status,
                    "terminal_reason": reason,
                    "terminal_at": now,
                    "calendar_correction": correction,
                }
            ),
            ORDER_SCHEMA_VERSION,
            order_doc.state_version,
        ),
        WriteRequest(
            repositories.generation_key(order.generation),
            next_summary,
            summary_doc.schema_version,
            summary_doc.state_version,
        ),
    ]
    if order.side == "sell" and position is not None and position_doc is not None:
        next_position = position.model_copy(
            update={
                "reserved_sell_quantity": max(
                    0, position.reserved_sell_quantity - order.quantity
                )
            }
        )
        requests.append(
            WriteRequest(
                repositories.position_key(order.generation, order.symbol),
                next_position,
                position_doc.schema_version,
                position_doc.state_version,
            )
        )
    repositories.write_many_in_transaction(transaction, requests=tuple(requests))


def _calendar_rejection(order: PaperOrder, evidence: ExecutionEvidence) -> str | None:
    intended = evidence.intended_session
    grace = evidence.grace_session
    if (
        evidence.active_calendar_version is None
        or intended is None
        or grace is None
        or intended.status != "trading"
        or grace.status != "trading"
        or intended.session_index is None
        or grace.session_index is None
        or intended.official_close_at is None
        or grace.official_close_at is None
    ):
        return "calendar_unavailable"
    if evidence.calendar_correction is not None:
        return "calendar_corrected"
    deadline = grace.official_close_at.astimezone(UTC) + COMPLETION_GRACE
    if (
        intended.session_date != order.intended_session
        or intended.session_id != order.accepted_session_id
        or deadline != order.grace_deadline_at
        or intended.calendar_version != evidence.active_calendar_version
        or grace.calendar_version != evidence.active_calendar_version
    ):
        return "calendar_corrected"
    return None


def _select_price(
    order: PaperOrder, evidence: ExecutionEvidence, now: datetime
) -> ExecutionPrice | None:
    eligible = [
        candidate
        for candidate in evidence.candidates
        if candidate.valid
        and candidate.sequence > 0
        and candidate.price.symbol == order.symbol
        and candidate.price.session_date == order.intended_session
        and candidate.price.close.micros > 0
        and candidate.price.validated_available_at <= now
        and candidate.price.validated_available_at <= order.grace_deadline_at
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda candidate: candidate.sequence).price


def _reserved_cash(order: PaperOrder) -> int:
    return 0 if order.reserved_cash is None else order.reserved_cash.micros


def _money(micros: int) -> NonNegativeMoney:
    return NonNegativeMoney(amount=_amount(micros), currency="XOF")


def _amount(micros: int) -> str:
    return format(Decimal(micros) / Decimal(1_000_000), ".6f")


def _record(value: BaseModel, model: type[RecordT]) -> RecordT:
    if isinstance(value, model):
        return value
    return model.model_validate(value.model_dump(mode="python"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("now must be an explicit UTC instant")
    return value.astimezone(UTC)
