"""Resource-oriented REST request, response, pagination, and route declarations."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, StringConstraints, field_serializer, field_validator, model_validator

from backend.contracts.envelopes import CommandMetadata, ContractModel
from backend.contracts.paper import (
    CashMovement,
    PAPER_ORDER_STATUS,
    PaperExecution,
    PaperOrder,
    PaperPosition,
    PaperPreferences,
    PortfolioSummary,
)
from backend.contracts.scalars import FeeRatePct, NonNegativeVersion, OpaqueIdentifier, StartingCash, WholeShares

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 100
CURSOR_MAX_AGE = timedelta(hours=24)
Cursor = Annotated[str, StringConstraints(min_length=1, max_length=2048, strict=True)]
HttpMethod: TypeAlias = Literal["GET", "PATCH", "POST"]
HttpStatus: TypeAlias = Literal[200, 201, 401, 403, 404, 409, 410, 413, 422, 503]
PortfolioSetupState: TypeAlias = Literal["setup_required", "configured"]
RouteErrorCode: TypeAlias = Literal[
    "recovery_mismatch",
    "stale_cursor",
    "expired_snapshot",
    "validation_failed",
    "admission_rejected",
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


class PatchPreferencesRequest(ContractModel):
    command: CommandMetadata
    expected_preference_version: NonNegativeVersion
    objective: Literal["growth", "dividend"] | None = None
    fee_rate_pct: FeeRatePct | None = None

    @model_validator(mode="after")
    def require_a_change(self) -> "PatchPreferencesRequest":
        if self.objective is None and self.fee_rate_pct is None:
            raise ValueError("preferences request requires objective or fee_rate_pct")
        return self


class SetupPortfolioRequest(ContractModel):
    command: CommandMetadata
    starting_cash: StartingCash
    fee_rate_pct: FeeRatePct


class CreatePaperOrderRequest(ContractModel):
    command: CommandMetadata
    expected_generation: OpaqueIdentifier
    expected_state_version: NonNegativeVersion
    recommendation_ref: OpaqueIdentifier
    batch_id: OpaqueIdentifier
    symbol: OpaqueIdentifier
    side: Literal["buy", "sell"]
    quantity: WholeShares
    acknowledge_keep_override: bool = False

    @model_validator(mode="after")
    def bind_command_fence(self) -> "CreatePaperOrderRequest":
        if (
            self.command.expected_generation != self.expected_generation
            or self.command.expected_state_version != self.expected_state_version
        ):
            raise ValueError("order command metadata must match the expected portfolio state")
        return self


class ResetPortfolioRequest(ContractModel):
    command: CommandMetadata
    expected_generation: OpaqueIdentifier
    expected_state_version: NonNegativeVersion
    starting_cash: StartingCash

    @model_validator(mode="after")
    def bind_command_fence(self) -> "ResetPortfolioRequest":
        if (
            self.command.expected_generation != self.expected_generation
            or self.command.expected_state_version != self.expected_state_version
        ):
            raise ValueError("reset command metadata must match the expected portfolio state")
        return self


class MeResource(ContractModel):
    uid: OpaqueIdentifier
    email: Annotated[str, StringConstraints(min_length=3, max_length=320, strict=True)]
    preferences: PaperPreferences
    portfolio_setup_state: PortfolioSetupState
    starting_cash_min_xof: int
    starting_cash_default_xof: int
    starting_cash_max_xof: int


class PortfolioResource(ContractModel):
    setup_state: PortfolioSetupState
    summary: PortfolioSummary | None
    positions: tuple[PaperPosition, ...]
    valuation_batch_id: OpaqueIdentifier | None
    valuation_session: date | None
    valuation_status: Literal["complete", "incomplete", "not_available"]

    @model_validator(mode="after")
    def validate_setup_state(self) -> "PortfolioResource":
        if self.setup_state == "setup_required":
            if self.summary is not None or self.positions:
                raise ValueError("unconfigured portfolio must have null summary and no positions")
        elif self.summary is None:
            raise ValueError("configured portfolio requires a summary")
        return self


class OrderListRequest(PageRequest):
    status: PAPER_ORDER_STATUS | None = None


class ExecutionListRequest(PageRequest):
    pass


class CashMovementListRequest(PageRequest):
    pass


class OrderListResource(Page):
    items: tuple[PaperOrder, ...]


class ExecutionListResource(Page):
    items: tuple[PaperExecution, ...]


class CashMovementListResource(Page):
    items: tuple[CashMovement, ...]


class CommandAcknowledgement(ContractModel):
    operation: OpaqueIdentifier
    generation: OpaqueIdentifier
    state_version: NonNegativeVersion
    preference_version: NonNegativeVersion
    replayed: bool


class SetupPortfolioResource(CommandAcknowledgement):
    summary: PortfolioSummary
    opening_cash_movement: CashMovement


class CreatePaperOrderResource(CommandAcknowledgement):
    order: PaperOrder


class ResetPortfolioResource(CommandAcknowledgement):
    summary: PortfolioSummary


class RouteContract(ContractModel):
    method: HttpMethod
    path: str
    success_status: Literal[200, 201]
    mutation: bool
    error_outcomes: tuple["RouteErrorOutcome", ...]


class RouteErrorOutcome(ContractModel):
    status: HttpStatus
    code: RouteErrorCode


COMMON_READ_ERRORS = (
    RouteErrorOutcome(status=401, code="admission_rejected"),
    RouteErrorOutcome(status=422, code="validation_failed"),
)
COMMON_MUTATION_ERRORS = COMMON_READ_ERRORS + (
    RouteErrorOutcome(status=409, code="recovery_mismatch"),
    RouteErrorOutcome(status=503, code="admission_rejected"),
)
PAGINATION_ERRORS = COMMON_READ_ERRORS + (
    RouteErrorOutcome(status=409, code="stale_cursor"),
    RouteErrorOutcome(status=410, code="expired_snapshot"),
)


PAPER_ROUTES: tuple[RouteContract, ...] = (
    RouteContract(method="GET", path="/v1/me", success_status=200, mutation=False, error_outcomes=COMMON_READ_ERRORS),
    RouteContract(method="PATCH", path="/v1/me/preferences", success_status=200, mutation=True, error_outcomes=COMMON_MUTATION_ERRORS),
    RouteContract(method="GET", path="/v1/paper/portfolio", success_status=200, mutation=False, error_outcomes=COMMON_READ_ERRORS),
    RouteContract(method="POST", path="/v1/paper/portfolio", success_status=201, mutation=True, error_outcomes=COMMON_MUTATION_ERRORS),
    RouteContract(method="POST", path="/v1/paper/orders", success_status=201, mutation=True, error_outcomes=COMMON_MUTATION_ERRORS),
    RouteContract(method="GET", path="/v1/paper/orders", success_status=200, mutation=False, error_outcomes=PAGINATION_ERRORS),
    RouteContract(method="GET", path="/v1/paper/executions", success_status=200, mutation=False, error_outcomes=PAGINATION_ERRORS),
    RouteContract(method="GET", path="/v1/paper/cash-movements", success_status=200, mutation=False, error_outcomes=PAGINATION_ERRORS),
    RouteContract(method="POST", path="/v1/paper/reset", success_status=200, mutation=True, error_outcomes=COMMON_MUTATION_ERRORS),
)
