"""API v0.13 response and mutation metadata envelopes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_serializer, field_validator, model_validator

from backend.contracts.scalars import MAX_COMMAND_BYTES, MAX_SAFE_INTEGER, OpaqueIdentifier

T = TypeVar("T")

IdempotencyKey = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9]{13}\.[0-9a-f]{32}$",
        strict=True,
    ),
]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("instant must be an explicit UTC RFC3339 timestamp")
    return value.astimezone(timezone.utc)


class ContractModel(BaseModel):
    """Forbid accidental request fields throughout the initial contract boundary."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ResponseMeta(ContractModel):
    request_id: OpaqueIdentifier
    server_time: datetime
    schema_version: Annotated[int, Field(strict=True, ge=1, le=MAX_SAFE_INTEGER)]
    recovery_id: OpaqueIdentifier | None = None

    @field_validator("server_time")
    @classmethod
    def validate_server_time(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("server_time")
    def serialize_server_time(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class ResponseEnvelope(ContractModel, Generic[T]):
    data: T
    meta: ResponseMeta


class ApiError(ContractModel):
    code: Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[a-z0-9_]+$", strict=True)]
    message: Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
    retryable: bool
    request_id: OpaqueIdentifier


class ErrorEnvelope(ContractModel):
    error: ApiError


class CommandMetadata(ContractModel):
    """Required mutation metadata, including the restore-safe command fence."""

    idempotency_key: IdempotencyKey
    recovery_id: OpaqueIdentifier
    request_fingerprint: OpaqueIdentifier
    content_length: Annotated[int, Field(strict=True, ge=0, le=MAX_COMMAND_BYTES)]
    issued_at: datetime
    expected_generation: OpaqueIdentifier | None = None
    expected_state_version: Annotated[int, Field(strict=True, ge=0, le=MAX_SAFE_INTEGER)] | None = None

    @field_validator("issued_at")
    @classmethod
    def validate_issued_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("issued_at")
    def serialize_issued_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    @model_validator(mode="after")
    def require_generation_and_version_together(self) -> "CommandMetadata":
        if (self.expected_generation is None) != (self.expected_state_version is None):
            raise ValueError("expected generation and state version must be supplied together")
        return self

    def matches_recovery(self, active_recovery_id: OpaqueIdentifier) -> bool:
        """Lets a handler reject a command fenced by a stale portfolio generation."""

        return self.recovery_id == active_recovery_id


class CommandReceipt(ContractModel):
    """Minimal replay-safe receipt metadata without financial history."""

    operation: OpaqueIdentifier
    outcome_id: OpaqueIdentifier | None = None
    generation: OpaqueIdentifier | None = None
    state_version: Annotated[int, Field(strict=True, ge=0, le=MAX_SAFE_INTEGER)] | None = None
    http_status: Annotated[int, Field(strict=True, ge=100, le=599)]
    replayed: bool = False
    accepted_at: datetime
    expires_at: datetime

    @field_validator("accepted_at", "expires_at")
    @classmethod
    def validate_receipt_instants(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @model_validator(mode="after")
    def require_ordered_expiry(self) -> "CommandReceipt":
        if self.expires_at < self.accepted_at:
            raise ValueError("receipt expiry cannot precede acceptance")
        return self
