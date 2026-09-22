"""Normalized analytical inputs and immutable published-result contracts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import Field, StringConstraints, field_serializer, field_validator, model_validator

from backend.contracts.envelopes import ContractModel
from backend.contracts.scalars import (
    NonNegativeMoney,
    NonNegativeVersion,
    OpaqueIdentifier,
    Score,
    SignedMoney,
    WholeShares,
)

T = TypeVar("T")

ReasonCode = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9_]+$",
        strict=True,
    ),
]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=256, strict=True)]
Basis = Literal["actual", "estimated", "modeled"]
MetricStatus = Literal[
    "assessable",
    "warming_up",
    "missing_inputs",
    "unsupported_basis",
    "deferred_scope",
]
NonNegativeShares = Annotated[int, Field(strict=True, ge=0)]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("instant must be an explicit UTC RFC3339 timestamp")
    return value.astimezone(timezone.utc)


class ImmutableContractModel(ContractModel):
    """A public analytical record that cannot be mutated after publication."""

    model_config = ContractModel.model_config | {"frozen": True}


class Provenance(ImmutableContractModel):
    """Sanitized origin evidence retained with each normalized observation."""

    source_id: OpaqueIdentifier
    collected_at: datetime
    published_at: datetime | None = None
    source_url: str | None = None
    original_unit: ShortText | None = None
    basis: Basis

    @field_validator("collected_at", "published_at")
    @classmethod
    def validate_instants(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_utc(value)

    @field_serializer("collected_at", "published_at")
    def serialize_instants(self, value: datetime | None) -> str | None:
        return None if value is None else value.isoformat().replace("+00:00", "Z")


class Revision(ImmutableContractModel):
    """The deterministic identity of a corrected normalized observation."""

    revision: NonNegativeVersion
    known_at: datetime
    provenance: Provenance

    @field_validator("known_at")
    @classmethod
    def validate_known_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("known_at")
    def serialize_known_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class NormalizedCompany(ImmutableContractModel):
    company_id: OpaqueIdentifier
    symbol: OpaqueIdentifier
    name: ShortText
    sector: ShortText | None = None
    financial_category: Literal["bank", "insurer", "non_financial", "unsupported"]
    share_class: ShortText | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    revision: Revision

    @model_validator(mode="after")
    def validate_validity_window(self) -> "NormalizedCompany":
        if self.valid_from is not None and self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("company validity cannot end before it starts")
        return self


class NormalizedSession(ImmutableContractModel):
    session_date: date
    status: Literal["trading", "holiday", "suspended", "unknown"]
    revision: Revision
    reason_codes: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def require_reason_for_non_trading_session(self) -> "NormalizedSession":
        if self.status != "trading" and not self.reason_codes:
            raise ValueError("non-trading session status requires a reason code")
        return self


class NormalizedPrice(ImmutableContractModel):
    symbol: OpaqueIdentifier
    session_date: date
    close: NonNegativeMoney | None
    high: NonNegativeMoney | None = None
    low: NonNegativeMoney | None = None
    volume: NonNegativeShares | None = None
    trade_status: Literal["traded", "confirmed_no_trade", "unknown"]
    basis: Basis
    reason_codes: tuple[ReasonCode, ...] = ()
    revision: Revision

    @model_validator(mode="after")
    def validate_price_availability(self) -> "NormalizedPrice":
        if self.trade_status == "traded" and self.close is None:
            raise ValueError("traded price requires a close")
        if self.trade_status != "traded" and not self.reason_codes:
            raise ValueError("non-traded price requires a reason code")
        if (self.high is None) != (self.low is None):
            raise ValueError("high and low must be supplied together")
        return self


class NormalizedFinancial(ImmutableContractModel):
    company_id: OpaqueIdentifier
    fiscal_period_end: date
    report_scope: Literal["standalone", "consolidated", "unknown"]
    currency: Literal["XOF"]
    revenue: NonNegativeMoney | None = None
    ordinary_owner_earnings: SignedMoney | None = None
    equity: SignedMoney | None = None
    publication_status: Literal["published", "unknown"]
    reason_codes: tuple[ReasonCode, ...] = ()
    revision: Revision

    @model_validator(mode="after")
    def require_reason_for_unknown_publication(self) -> "NormalizedFinancial":
        if self.publication_status == "unknown" and not self.reason_codes:
            raise ValueError("unknown publication status requires a reason code")
        return self


class NormalizedCapital(ImmutableContractModel):
    company_id: OpaqueIdentifier
    effective_date: date
    ordinary_shares: WholeShares | None
    share_basis: Literal["ordinary_outstanding", "free_float", "weighted_average", "unknown"]
    reason_codes: tuple[ReasonCode, ...] = ()
    revision: Revision

    @model_validator(mode="after")
    def validate_share_basis(self) -> "NormalizedCapital":
        if self.share_basis == "ordinary_outstanding" and self.ordinary_shares is None:
            raise ValueError("ordinary outstanding share basis requires a share count")
        if self.share_basis != "ordinary_outstanding" and not self.reason_codes:
            raise ValueError("unsupported or unknown share basis requires a reason code")
        return self


class NormalizedDividend(ImmutableContractModel):
    dividend_id: OpaqueIdentifier
    company_id: OpaqueIdentifier
    payment_date: date | None
    fiscal_period_end: date | None = None
    amount_per_share: NonNegativeMoney | None
    payment_status: Literal["paid", "declared", "unknown"]
    dividend_type: Literal["ordinary", "exceptional", "unclassified"]
    coverage_status: Literal["complete", "partial", "unknown"]
    reason_codes: tuple[ReasonCode, ...] = ()
    revision: Revision

    @model_validator(mode="after")
    def validate_dividend_evidence(self) -> "NormalizedDividend":
        if self.payment_status == "paid" and (self.payment_date is None or self.amount_per_share is None):
            raise ValueError("paid dividend requires payment date and per-share amount")
        if self.payment_status == "unknown" and not self.reason_codes:
            raise ValueError("unknown dividend status requires a reason code")
        return self


class NormalizedRating(ImmutableContractModel):
    rating_id: OpaqueIdentifier
    company_id: OpaqueIdentifier
    agency: ShortText | None
    scale: ShortText | None
    subject: ShortText | None
    label: ShortText
    effective_date: date | None
    collected_at: datetime
    reason_codes: tuple[ReasonCode, ...] = ()
    revision: Revision

    @field_validator("collected_at")
    @classmethod
    def validate_collected_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("collected_at")
    def serialize_collected_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class AnalyticalMetric(ImmutableContractModel, Generic[T]):
    """A calculated value with explicit availability, reason, basis and evidence."""

    status: MetricStatus
    value: T | None
    unit: ShortText
    reason_codes: tuple[ReasonCode, ...] = ()
    evidence_refs: tuple[OpaqueIdentifier, ...] = ()
    effective_date: date | None = None
    basis: Basis | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> "AnalyticalMetric[T]":
        if self.status == "assessable":
            if self.value is None:
                raise ValueError("assessable metric requires a value")
            return self
        if self.value is not None:
            raise ValueError("unavailable metric must have a null value")
        if not self.reason_codes:
            raise ValueError("unavailable metric requires a reason code")
        return self


class LongTermResult(ImmutableContractModel):
    """Published long-term state; Dividend and Balanced scoring stay deferred in V1."""

    company_id: OpaqueIdentifier
    growth_score: AnalyticalMetric[Score]
    dividend_score: AnalyticalMetric[Score]
    balanced_score: AnalyticalMetric[Score]
    overall_score: AnalyticalMetric[Score]
    revision: Revision

    @model_validator(mode="after")
    def validate_v1_score_scope(self) -> "LongTermResult":
        deferred = (
            (self.dividend_score, "dividend_scoring_deferred_v1"),
            (self.balanced_score, "balanced_scoring_deferred_v1"),
        )
        for metric, reason in deferred:
            if metric.status != "deferred_scope" or metric.value is not None or reason not in metric.reason_codes:
                raise ValueError(f"{reason} must be an explicit deferred V1 state")
        if self.growth_score.status == "deferred_scope":
            raise ValueError("Growth must use missing or unsupported evidence, not deferred scope")
        if self.overall_score != self.growth_score:
            raise ValueError("Growth overall score must equal the Growth score")
        return self


class AnalyticalBatch(ImmutableContractModel):
    """An atomic immutable publication boundary shared by analysis readers."""

    batch_id: OpaqueIdentifier
    market_session: date
    published_at: datetime
    input_snapshot_id: OpaqueIdentifier
    rule_version: OpaqueIdentifier
    strategy_id: OpaqueIdentifier
    revision: NonNegativeVersion
    results: tuple[LongTermResult, ...]

    @field_validator("published_at")
    @classmethod
    def validate_published_at(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("published_at")
    def serialize_published_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    @model_validator(mode="after")
    def require_distinct_company_results(self) -> "AnalyticalBatch":
        company_ids = [result.company_id for result in self.results]
        if len(company_ids) != len(set(company_ids)):
            raise ValueError("batch cannot contain more than one result per company")
        return self
