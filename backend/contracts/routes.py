"""Resource-oriented REST request, response, pagination, and route declarations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, StringConstraints, field_serializer, field_validator

from backend.contracts.envelopes import ContractModel
from backend.contracts.scalars import NonNegativeVersion, OpaqueIdentifier

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 100
CURSOR_MAX_AGE = timedelta(hours=24)
Cursor = Annotated[str, StringConstraints(min_length=1, max_length=2048, strict=True)]
HttpMethod: TypeAlias = Literal["GET"]
HttpStatus: TypeAlias = Literal[200, 401, 403, 404, 409, 410, 422, 429, 503]
RouteErrorCode: TypeAlias = Literal[
    "unauthenticated",
    "admission_denied",
    "not_found",
    "recovery_mismatch",
    "generation_mismatch",
    "state_version_mismatch",
    "preference_version_mismatch",
    "generation_superseded",
    "already_initialized",
    "recommendation_stale",
    "insufficient_cash",
    "insufficient_shares",
    "idempotency_conflict",
    "command_window_expired",
    "command_clock_ahead",
    "cursor_stale",
    "snapshot_expired",
    "body_too_large",
    "validation_failed",
    "override_acknowledgment_required",
    "rate_limited",
    "service_unavailable",
    "admission_unavailable",
    "calendar_unavailable",
    "analysis_not_ready",
    "setup_required",
]
def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("instant must be an explicit UTC RFC3339 timestamp")
    return value.astimezone(timezone.utc)


class PageRequest(ContractModel):
    limit: Annotated[int, Field(strict=True, ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT
    cursor: Cursor | None = None


class Page(ContractModel):
    """Bounded response page; cursor lifecycle is enforced by the store/handler."""

    items: tuple[object, ...]
    next_cursor: Cursor | None


class CursorBinding(ContractModel):
    """Backend-only cursor evidence preventing cross-owner or mixed-snapshot pages."""

    owner_uid: OpaqueIdentifier | None
    generation: OpaqueIdentifier | None
    state_version: NonNegativeVersion | None
    batch_id: OpaqueIdentifier | None
    filter_fingerprint: OpaqueIdentifier
    last_key: OpaqueIdentifier
    issued_at: datetime

    @field_validator("issued_at")
    @classmethod
    def validate_issued_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("issued_at")
    def serialize_issued_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class MeResource(ContractModel):
    uid: OpaqueIdentifier
    email: Annotated[str, StringConstraints(min_length=3, max_length=320, strict=True)]
