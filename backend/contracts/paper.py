"""Immutable paper-trading resources and storage-boundary contracts."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal, Protocol

from pydantic import Field, field_serializer, field_validator, model_validator

from backend.contracts.analysis import ImmutableContractModel, Provenance, ReasonCode
from backend.contracts.envelopes import CommandReceipt, ContractModel, IdempotencyKey
from backend.contracts.scalars import (
    FeeRatePct,
    NonNegativeMoney,
    NonNegativeVersion,
    OpaqueIdentifier,
    SignedMoney,
    StartingCash,
    WholeShares,
)

PREFERENCE_OBJECTIVE = Literal["growth", "dividend"]
PAPER_ORDER_STATUS = Literal["pending", "executed", "rejected", "expired"]
PAPER_SIDE = Literal["buy", "sell"]
UTC = timezone.utc
RECEIPT_RETENTION = timedelta(days=30)


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("instant must be an explicit UTC RFC3339 timestamp")
    return value.astimezone(UTC)


class PaperPreferences(ImmutableContractModel):
    """User-editable research objective and prospective paper fee only."""

    objective: PREFERENCE_OBJECTIVE
    fee_rate_pct: FeeRatePct
    preference_version: NonNegativeVersion
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class PortfolioControl(ImmutableContractModel):
    """Backend-owned active-generation and serialization control record."""

    owner_uid: OpaqueIdentifier
    active_generation: OpaqueIdentifier | None
    configured_fee_rate_pct: FeeRatePct | None
    state_version: NonNegativeVersion
    preference_version: NonNegativeVersion
    recovery_id: OpaqueIdentifier
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class PortfolioSummary(ImmutableContractModel):
    generation: OpaqueIdentifier
    starting_cash: StartingCash
    cash: NonNegativeMoney
    reserved_cash: NonNegativeMoney
    pending_order_count: Annotated[int, Field(strict=True, ge=0)]
    state_version: NonNegativeVersion
    created_at: datetime
    active: bool

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    @model_validator(mode="after")
    def validate_reservation(self) -> "PortfolioSummary":
        if self.reserved_cash.micros > self.cash.micros:
            raise ValueError("reserved cash cannot exceed cash")
        return self


class PaperPosition(ImmutableContractModel):
    generation: OpaqueIdentifier
    symbol: OpaqueIdentifier
    quantity: Annotated[int, Field(strict=True, ge=0)]
    reserved_sell_quantity: Annotated[int, Field(strict=True, ge=0)]
    remaining_gross_cost: NonNegativeMoney
    purchase_fees: NonNegativeMoney
    opening_session: date
    high_water_close: NonNegativeMoney | None
    evaluated_through_session: date | None
    trail_activated: bool
    exit_policy_ref: OpaqueIdentifier

    @model_validator(mode="after")
    def validate_reserved_shares(self) -> "PaperPosition":
        if self.reserved_sell_quantity > self.quantity:
            raise ValueError("reserved sell quantity cannot exceed position quantity")
        return self


class ExecutionPrice(ImmutableContractModel):
    """The immutable, timely price evidence selected for a paper fill."""

    price_revision_id: OpaqueIdentifier
    symbol: OpaqueIdentifier
    session_date: date
    close: NonNegativeMoney
    validated_available_at: datetime
    source_evidence: tuple[Provenance, ...]

    @field_validator("validated_available_at")
    @classmethod
    def validate_available_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("validated_available_at")
    def serialize_available_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    @model_validator(mode="after")
    def require_evidence(self) -> "ExecutionPrice":
        if not self.source_evidence:
            raise ValueError("execution price requires source evidence")
        return self


class PaperOrder(ImmutableContractModel):
    order_id: OpaqueIdentifier
    owner_uid: OpaqueIdentifier
    generation: OpaqueIdentifier
    recommendation_ref: OpaqueIdentifier
    batch_id: OpaqueIdentifier
    symbol: OpaqueIdentifier
    side: PAPER_SIDE
    quantity: WholeShares
    accepted_at: datetime
    intended_session: date
    grace_deadline_at: datetime
    fee_rate_pct: FeeRatePct
    reserved_cash: NonNegativeMoney | None = None
    reserved_sell_quantity: Annotated[int, Field(strict=True, ge=0)] | None = None
    status: PAPER_ORDER_STATUS
    state_version_at_acceptance: NonNegativeVersion
    advice_action_at_acceptance: Literal["keep", "sell"] | None = None
    advice_evaluation_session: date | None = None
    exit_policy_ref: OpaqueIdentifier | None = None
    is_advice_override: bool = False
    acknowledged_keep_override: bool = False
    terminal_reason: ReasonCode | None = None
    terminal_at: datetime | None = None

    @field_validator("accepted_at", "grace_deadline_at", "terminal_at")
    @classmethod
    def validate_instants(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_utc(value)

    @field_serializer("accepted_at", "grace_deadline_at", "terminal_at")
    def serialize_instants(self, value: datetime | None) -> str | None:
        return None if value is None else value.isoformat().replace("+00:00", "Z")

    @model_validator(mode="after")
    def validate_order_evidence(self) -> "PaperOrder":
        if self.grace_deadline_at < self.accepted_at:
            raise ValueError("order grace deadline cannot precede acceptance")
        if self.side == "buy":
            if self.reserved_cash is None or self.reserved_sell_quantity is not None:
                raise ValueError("buy order requires cash reservation only")
            if self.advice_action_at_acceptance is not None or self.is_advice_override or self.acknowledged_keep_override:
                raise ValueError("buy order cannot carry sell-advice evidence")
        elif self.reserved_sell_quantity != self.quantity or self.reserved_cash is not None:
            raise ValueError("sell order requires the full share reservation only")
        if self.side == "sell":
            if self.advice_action_at_acceptance not in {"keep", "sell"}:
                raise ValueError("sell order requires derived keep or sell advice")
            if self.advice_evaluation_session is None or self.exit_policy_ref is None:
                raise ValueError("sell order requires advice session and exit-policy evidence")
            if self.advice_action_at_acceptance == "keep":
                if not (self.is_advice_override and self.acknowledged_keep_override):
                    raise ValueError("keep advice requires acknowledged override evidence")
            elif self.is_advice_override or self.acknowledged_keep_override:
                raise ValueError("sell advice cannot carry a keep override")
        if self.status == "pending" and (self.terminal_reason is not None or self.terminal_at is not None):
            raise ValueError("pending order cannot have terminal evidence")
        if self.status != "pending" and (self.terminal_reason is None or self.terminal_at is None):
            raise ValueError("terminal order requires reason and terminal instant")
        return self


class PaperExecution(ImmutableContractModel):
    execution_id: OpaqueIdentifier
    order_id: OpaqueIdentifier
    owner_uid: OpaqueIdentifier
    generation: OpaqueIdentifier
    quantity: WholeShares
    execution_price: ExecutionPrice
    gross_amount: NonNegativeMoney
    fee_amount: NonNegativeMoney
    allocated_cost: NonNegativeMoney | None
    allocated_purchase_fees: NonNegativeMoney | None
    signed_cash_effect: SignedMoney
    processed_at: datetime

    @field_validator("processed_at")
    @classmethod
    def validate_processed_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("processed_at")
    def serialize_processed_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class CashMovement(ImmutableContractModel):
    movement_id: OpaqueIdentifier
    owner_uid: OpaqueIdentifier
    generation: OpaqueIdentifier
    movement_type: Literal["opening_cash", "buy_execution", "sell_execution"]
    signed_amount: SignedMoney
    execution_id: OpaqueIdentifier | None = None
    occurred_at: datetime
    processed_at: datetime

    @field_validator("occurred_at", "processed_at")
    @classmethod
    def validate_instants(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("occurred_at", "processed_at")
    def serialize_instants(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    @model_validator(mode="after")
    def validate_execution_link(self) -> "CashMovement":
        needs_execution = self.movement_type != "opening_cash"
        if needs_execution != (self.execution_id is not None):
            raise ValueError("only execution movements may reference an execution")
        if self.movement_type == "opening_cash" and self.signed_amount.micros <= 0:
            raise ValueError("opening cash movement must be positive")
        return self


class PaperCommandReceipt(CommandReceipt):
    """Minimal backend-only replay evidence, intentionally outside generations."""

    owner_uid: OpaqueIdentifier
    idempotency_key: IdempotencyKey
    request_fingerprint: OpaqueIdentifier
    recovery_id: OpaqueIdentifier

    @model_validator(mode="after")
    def validate_retention(self) -> "PaperCommandReceipt":
        if self.expires_at != self.accepted_at + RECEIPT_RETENTION:
            raise ValueError("paper command receipt must retain exactly thirty days")
        return self


class PaperStore(Protocol):
    """Storage protocol; implementations, transactions, and handlers are deferred."""

    def get_control(self, owner_uid: OpaqueIdentifier) -> PortfolioControl | None: ...

    def get_preferences(self, owner_uid: OpaqueIdentifier) -> PaperPreferences: ...

    def get_receipt(self, owner_uid: OpaqueIdentifier, idempotency_key: IdempotencyKey) -> PaperCommandReceipt | None: ...

    def get_execution_price(self, price_revision_id: OpaqueIdentifier) -> ExecutionPrice | None: ...
