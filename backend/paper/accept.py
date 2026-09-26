"""Fresh, recommendation-linked order acceptance with atomic reservations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Protocol, TypeVar, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from backend.commands.receipts import (
    ReceiptError,
    ReceiptOutcome,
    execute_with_receipt,
    fingerprint_request,
)
from backend.contracts.analysis import NormalizedSession
from backend.contracts.envelopes import CommandReceipt
from backend.contracts.paper import (
    PaperOrder,
    PaperPosition,
    PaperPreferences,
    PortfolioControl,
    PortfolioSummary,
)
from backend.contracts.routes import CreatePaperOrderRequest
from backend.contracts.scalars import NonNegativeMoney, OpaqueIdentifier
from backend.paper.holding_advice import HoldingAdvice
from backend.store.repositories import (
    GenerationConflict,
    PaperRepositories,
    VersionConflict,
    WriteRequest,
)
from backend.store.transactions import Transaction

UTC = timezone.utc
RecordT = TypeVar("RecordT", bound=BaseModel)
EXCHANGE_TZ = ZoneInfo("Africa/Abidjan")
SESSION_CUTOFF_GRACE = timedelta(seconds=60)
ORDER_SCHEMA_VERSION = 1


class OrderAcceptanceError(ValueError):
    """A manual order does not satisfy the current advice or account state."""

    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class RecommendationEvidence:
    reference: OpaqueIdentifier
    batch_id: OpaqueIdentifier
    symbol: OpaqueIdentifier
    session_date: date
    published_at: datetime
    entry_action: Literal["buy", "not_buy", "unavailable"]
    reference_close: NonNegativeMoney


@dataclass(frozen=True, slots=True)
class AcceptanceEvidence:
    active_recommendation: RecommendationEvidence
    calendar_sessions: tuple[NormalizedSession, ...]
    holding_advice: HoldingAdvice | None


class AcceptanceEvidenceReader(Protocol):
    """Read the active publication, verified calendar and current holding advice."""

    def load(
        self,
        transaction: Transaction,
        *,
        symbol: OpaqueIdentifier,
        generation: OpaqueIdentifier,
        now: datetime,
    ) -> AcceptanceEvidence: ...


@dataclass(frozen=True, slots=True)
class OrderAcceptanceResult:
    order: PaperOrder
    receipt: CommandReceipt


def accept_order(
    repositories: PaperRepositories,
    request: CreatePaperOrderRequest,
    evidence_reader: AcceptanceEvidenceReader,
    *,
    now: datetime,
    order_id: OpaqueIdentifier | None = None,
) -> OrderAcceptanceResult:
    """Validate fresh evidence and atomically create a pending order and receipt."""

    now = _as_utc(now)
    stable_order_id = order_id or f"order-{uuid4().hex}"
    fingerprint = fingerprint_request("POST", "/v1/paper/orders", request)
    store = repositories._store

    def apply(transaction: Transaction) -> ReceiptOutcome:
        control_doc = store.get_in_transaction(transaction, repositories.control_key())
        summary_doc = store.get_in_transaction(
            transaction, repositories.generation_key(request.expected_generation)
        )
        if control_doc is None or summary_doc is None:
            raise OrderAcceptanceError("not_found", "Configured paper portfolio was not found.", status_code=404)
        control = _record(control_doc.record, PortfolioControl)
        summary = _record(summary_doc.record, PortfolioSummary)
        if control.active_generation != request.expected_generation:
            raise GenerationConflict("expected portfolio generation is no longer active")
        if summary.state_version != request.expected_state_version:
            raise VersionConflict(
                f"expected state version {request.expected_state_version}, found {summary.state_version}"
            )
        preference_doc = store.get_in_transaction(transaction, repositories.preferences_key())
        if preference_doc is None:
            raise OrderAcceptanceError("not_found", "Paper fee preferences were not found.", status_code=404)
        preferences = _record(preference_doc.record, PaperPreferences)
        if preferences.preference_version != control.preference_version:
            raise VersionConflict("paper preferences changed during order acceptance")

        evidence = evidence_reader.load(
            transaction,
            symbol=request.symbol,
            generation=request.expected_generation,
            now=now,
        )
        latest_session = _latest_completed_session(evidence.calendar_sessions, now)
        recommendation = evidence.active_recommendation
        if (
            recommendation.reference != request.recommendation_ref
            or recommendation.batch_id != request.batch_id
            or recommendation.symbol != request.symbol
            or recommendation.session_date != latest_session.session_date
            or recommendation.published_at < _session_cutoff(latest_session)
            or recommendation.published_at > now
        ):
            raise OrderAcceptanceError(
                "recommendation_stale",
                "Refresh the latest completed-session recommendation and confirm the order again.",
            )

        intended, deadline = _intended_session(evidence.calendar_sessions, now)
        if intended.session_index is None:
            raise OrderAcceptanceError(
                "calendar_unavailable", "Intended session has no verified index.", status_code=503
            )
        reserved_cash: NonNegativeMoney | None = None
        reserved_shares: int | None = None
        advice_action: Literal["keep", "sell"] | None = None
        advice_session: date | None = None
        exit_policy: OpaqueIdentifier | None = None
        is_override = False
        acknowledged = False

        if request.side == "buy":
            if recommendation.entry_action != "buy":
                raise OrderAcceptanceError("recommendation_stale", "Current entry advice does not authorize a Buy.")
            reserved_cash = _buy_reservation(
                recommendation.reference_close, request.quantity, preferences.fee_rate_pct
            )
            available = summary.cash.micros - summary.reserved_cash.micros
            if reserved_cash.micros > available:
                raise OrderAcceptanceError("insufficient_cash", "Available cash cannot cover this order.")
            next_summary = summary.model_copy(
                update={
                    "reserved_cash": _money(summary.reserved_cash.micros + reserved_cash.micros),
                    "pending_order_count": summary.pending_order_count + 1,
                    "state_version": summary.state_version + 1,
                }
            )
            reservation_request = WriteRequest(
                key=repositories.generation_key(request.expected_generation),
                record=next_summary,
                schema_version=summary_doc.schema_version,
                expected_state_version=summary_doc.state_version,
            )
        else:
            advice = evidence.holding_advice
            if (
                advice is None
                or advice.generation != request.expected_generation
                or advice.state_version != summary.state_version
                or advice.evaluation_session != latest_session.session_date
                or advice.action not in {"keep", "sell"}
            ):
                raise OrderAcceptanceError(
                    "recommendation_stale",
                    "Refresh current holding advice and confirm the order again.",
                )
            position_doc = store.get_in_transaction(
                transaction,
                repositories.position_key(request.expected_generation, request.symbol),
            )
            if position_doc is None:
                raise OrderAcceptanceError("not_found", "The paper position was not found.", status_code=404)
            position = _record(position_doc.record, PaperPosition)
            available_shares = position.quantity - position.reserved_sell_quantity
            if request.quantity > available_shares:
                raise OrderAcceptanceError("insufficient_shares", "Available shares cannot cover this order.")
            if advice.action == "keep" and not request.acknowledge_keep_override:
                raise OrderAcceptanceError(
                    "override_acknowledgment_required",
                    "A Sell against Keep advice requires explicit acknowledgment.",
                    status_code=422,
                )
            advice_action = cast(Literal["keep", "sell"], advice.action)
            advice_session = advice.evaluation_session
            exit_policy = advice.exit_policy_ref
            is_override = advice.action == "keep"
            acknowledged = is_override and request.acknowledge_keep_override
            reserved_shares = request.quantity
            next_position = position.model_copy(
                update={"reserved_sell_quantity": position.reserved_sell_quantity + request.quantity}
            )
            next_summary = summary.model_copy(
                update={
                    "pending_order_count": summary.pending_order_count + 1,
                    "state_version": summary.state_version + 1,
                }
            )
            reservation_request = WriteRequest(
                key=repositories.generation_key(request.expected_generation),
                record=next_summary,
                schema_version=summary_doc.schema_version,
                expected_state_version=summary_doc.state_version,
            )
            position_request = WriteRequest(
                key=repositories.position_key(request.expected_generation, request.symbol),
                record=next_position,
                schema_version=position_doc.schema_version,
                expected_state_version=position_doc.state_version,
            )

        order = PaperOrder(
            order_id=stable_order_id,
            owner_uid=repositories.owner_uid,
            generation=request.expected_generation,
            recommendation_ref=recommendation.reference,
            batch_id=recommendation.batch_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            accepted_at=now,
            intended_session=intended.session_date,
            accepted_calendar_version=intended.calendar_version,
            accepted_session_id=intended.session_id,
            accepted_session_index=intended.session_index,
            grace_deadline_at=deadline,
            fee_rate_pct=preferences.fee_rate_pct,
            reserved_cash=reserved_cash,
            reserved_sell_quantity=reserved_shares,
            status="pending",
            state_version_at_acceptance=summary.state_version,
            advice_action_at_acceptance=advice_action,
            advice_evaluation_session=advice_session,
            exit_policy_ref=exit_policy,
            is_advice_override=is_override,
            acknowledged_keep_override=acknowledged,
        )
        requests = [reservation_request]
        if request.side == "sell":
            requests.append(position_request)
        requests.append(
            WriteRequest(
                key=repositories.order_key(request.expected_generation, stable_order_id),
                record=order,
                schema_version=ORDER_SCHEMA_VERSION,
                expected_state_version=None,
            )
        )
        repositories.write_many_in_transaction(transaction, requests=tuple(requests))
        return ReceiptOutcome(
            operation="create_paper_order",
            http_status=201,
            outcome_id=stable_order_id,
            generation=request.expected_generation,
            state_version=next_summary.state_version,
        )

    receipt_result = execute_with_receipt(
        store,
        repositories,
        request.command,
        fingerprint,
        now=now,
        apply_mutation=apply,
    )
    receipt = receipt_result.receipt
    if receipt.outcome_id is None or receipt.generation is None:
        raise ReceiptError("idempotency_conflict", "Order receipt does not identify its result.")
    accepted = repositories.get_order(receipt.generation, receipt.outcome_id)
    if accepted is None:
        raise ReceiptError("idempotency_conflict", "Accepted order is missing from its active generation.")
    return OrderAcceptanceResult(accepted.record, receipt)


def _latest_completed_session(
    sessions: tuple[NormalizedSession, ...], now: datetime
) -> NormalizedSession:
    completed = [
        session
        for session in sessions
        if session.status == "trading"
        and session.official_close_at is not None
        and _session_cutoff(session) <= now
    ]
    if not completed:
        raise OrderAcceptanceError("recommendation_stale", "No completed trading session is available.")
    return max(completed, key=lambda session: (session.session_date, session.session_index or -1))


def _intended_session(
    sessions: tuple[NormalizedSession, ...], now: datetime
) -> tuple[NormalizedSession, datetime]:
    if len({session.calendar_version for session in sessions}) != 1:
        raise OrderAcceptanceError(
            "calendar_unavailable", "Calendar evidence mixes versions.", status_code=503
        )
    acceptance_date = now.astimezone(EXCHANGE_TZ).date()
    trading = sorted(
        (session for session in sessions if session.status == "trading" and session.official_close_at),
        key=lambda session: (session.session_date, session.session_index or -1),
    )
    following = [session for session in trading if session.session_date > acceptance_date]
    if len(following) < 2:
        raise OrderAcceptanceError(
            "calendar_unavailable", "Verified calendar does not cover the intended and grace sessions.", status_code=503
        )
    intended, grace_session = following[:2]
    if intended.session_index is None or grace_session.official_close_at is None:
        raise OrderAcceptanceError(
            "calendar_unavailable", "Verified calendar session indexes or close times are missing.", status_code=503
        )
    return intended, _session_cutoff(grace_session)


def _session_cutoff(session: NormalizedSession) -> datetime:
    if session.status != "trading" or session.official_close_at is None or not session.source_evidence:
        raise OrderAcceptanceError("calendar_unavailable", "Trading session lacks verified close evidence.", status_code=503)
    return session.official_close_at + SESSION_CUTOFF_GRACE


def _buy_reservation(
    reference_close: NonNegativeMoney, quantity: int, fee_rate_pct: str
) -> NonNegativeMoney:
    if reference_close.micros <= 0:
        raise OrderAcceptanceError("recommendation_stale", "Current recommendation lacks a genuine closing price.")
    gross_micros = reference_close.micros * quantity
    fee_xof = (
        Decimal(gross_micros)
        / Decimal(1_000_000)
        * Decimal(fee_rate_pct)
        / Decimal(100)
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return _money(gross_micros + int(fee_xof) * 1_000_000)


def _money(micros: int) -> NonNegativeMoney:
    if micros < 0:
        raise OrderAcceptanceError("insufficient_cash", "Order reservation cannot be negative.")
    return NonNegativeMoney(
        amount=f"{micros // 1_000_000}.{micros % 1_000_000:06d}", currency="XOF"
    )


def _record(value: BaseModel, record_type: type[RecordT]) -> RecordT:
    if isinstance(value, record_type):
        return value
    return record_type.model_validate(value.model_dump(mode="python"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("now must be an explicit UTC instant")
    return value.astimezone(UTC)
