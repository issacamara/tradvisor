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
    calendar_version: OpaqueIdentifier
    session_id: OpaqueIdentifier
    session_date: date
    session_index: NonNegativeVersion | None
    exchange_timezone: Literal["Africa/Abidjan"]
    status: Literal["trading", "holiday", "suspended", "unknown"]
    official_close_at: datetime | None
    source_evidence: tuple[Provenance, ...]
    revision: Revision
    reason_codes: tuple[ReasonCode, ...] = ()

    @field_validator("official_close_at")
    @classmethod
    def validate_official_close_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_utc(value)

    @field_serializer("official_close_at")
    def serialize_official_close_at(self, value: datetime | None) -> str | None:
        return None if value is None else value.isoformat().replace("+00:00", "Z")

    @model_validator(mode="after")
    def require_reason_for_non_trading_session(self) -> "NormalizedSession":
        if not self.source_evidence:
            raise ValueError("session requires source evidence")
        if (self.status == "unknown") != (self.session_index is None):
            raise ValueError("unknown session status requires no index; known status requires an index")
        if self.status == "trading" and self.official_close_at is None:
            raise ValueError("trading session requires an official close instant")
        if self.status != "trading" and not self.reason_codes:
            raise ValueError("non-trading session status requires a reason code")
        return self


class NormalizedPrice(ImmutableContractModel):
    symbol: OpaqueIdentifier
    session_date: date
    close: NonNegativeMoney | None
    close_basis: Literal["raw", "adjusted", "unknown"] = Field(
        default="unknown", exclude=True
    )
    high: NonNegativeMoney | None = None
    low: NonNegativeMoney | None = None
    volume: NonNegativeShares | None = None
    trade_status: Literal["traded", "confirmed_no_trade", "unknown"]
    basis: Basis
    original_source_date: date
    price_basis_ref: OpaqueIdentifier
    validated_available_at: datetime | None
    actual_xof_turnover: NonNegativeMoney | None = None
    liquidity_basis: Basis | None = None
    suspension_status: Literal["not_suspended", "suspended", "unknown"]
    suspension_evidence: tuple[Provenance, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    revision: Revision

    @field_validator("validated_available_at")
    @classmethod
    def validate_available_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_utc(value)

    @field_serializer("validated_available_at")
    def serialize_available_at(self, value: datetime | None) -> str | None:
        return None if value is None else value.isoformat().replace("+00:00", "Z")

    @model_validator(mode="after")
    def validate_price_availability(self) -> "NormalizedPrice":
        if self.trade_status == "traded" and self.close is None:
            raise ValueError("traded price requires a close")
        if self.trade_status == "traded" and self.basis == "actual" and self.validated_available_at is None:
            raise ValueError("actual traded price requires validated availability")
        if self.trade_status != "traded" and not self.reason_codes:
            raise ValueError("non-traded price requires a reason code")
        if (self.high is None) != (self.low is None):
            raise ValueError("high and low must be supplied together")
        if self.actual_xof_turnover is not None and self.liquidity_basis != "actual":
            raise ValueError("actual turnover requires an actual liquidity basis")
        if self.suspension_status != "not_suspended" and not self.suspension_evidence:
            raise ValueError("suspension or unknown status requires evidence")
        return self


class NormalizedFinancial(ImmutableContractModel):
    company_id: OpaqueIdentifier
    fiscal_period_start: date
    fiscal_period_end: date
    report_scope: Literal["standalone", "consolidated", "unknown"]
    currency: Literal["XOF"]
    original_scale: ShortText | None
    revenue: NonNegativeMoney | None = None
    ordinary_owner_earnings: SignedMoney | None = None
    equity: SignedMoney | None = None
    opening_equity: SignedMoney | None = None
    publication_status: Literal["published", "unknown"]
    reason_codes: tuple[ReasonCode, ...] = ()
    revision: Revision

    @model_validator(mode="after")
    def require_reason_for_unknown_publication(self) -> "NormalizedFinancial":
        if self.fiscal_period_end < self.fiscal_period_start:
            raise ValueError("financial period cannot end before it starts")
        if self.publication_status == "unknown" and not self.reason_codes:
            raise ValueError("unknown publication status requires a reason code")
        return self


class NormalizedCapital(ImmutableContractModel):
    company_id: OpaqueIdentifier
    effective_date: date
    ordinary_shares: WholeShares | None
    share_basis: Literal["ordinary_outstanding", "free_float", "weighted_average", "unknown"] | None
    aggregate_ordinary_market_cap: NonNegativeMoney | None = None
    capitalization_basis: Literal[
        "matched_ordinary_claim",
        "verified_aggregate_ordinary_claim",
        "unmatched",
        "unknown",
    ]
    reason_codes: tuple[ReasonCode, ...] = ()
    revision: Revision

    @model_validator(mode="after")
    def validate_share_basis(self) -> "NormalizedCapital":
        if self.capitalization_basis == "matched_ordinary_claim":
            if self.share_basis != "ordinary_outstanding" or self.ordinary_shares is None:
                raise ValueError("matched ordinary claim requires outstanding ordinary shares")
            if self.aggregate_ordinary_market_cap is not None:
                raise ValueError("capitalization must use either shares or verified aggregate value")
        elif self.capitalization_basis == "verified_aggregate_ordinary_claim":
            if self.ordinary_shares is not None or self.share_basis is not None:
                raise ValueError("verified aggregate claim cannot use a share count")
            if (
                self.aggregate_ordinary_market_cap is None
                or self.aggregate_ordinary_market_cap.micros <= 0
                or self.revision.provenance.basis != "actual"
            ):
                raise ValueError("verified aggregate claim requires positive actual market capitalization")
        else:
            if self.aggregate_ordinary_market_cap is not None:
                raise ValueError("unverified capitalization cannot supply aggregate value")
            if (self.ordinary_shares is None) != (self.share_basis is None):
                raise ValueError("share count and its basis must be supplied together")
            if self.share_basis == "ordinary_outstanding":
                raise ValueError("ordinary outstanding shares require matched capitalization basis")
            if not self.reason_codes:
                raise ValueError("unmatched or unknown capitalization requires a reason code")
        return self


class NormalizedDividend(ImmutableContractModel):
    dividend_id: OpaqueIdentifier
    company_id: OpaqueIdentifier
    installment_id: OpaqueIdentifier
    payment_date: date | None
    fiscal_period_end: date | None = None
    gross_amount_per_share: NonNegativeMoney | None = None
    net_amount_per_share: NonNegativeMoney | None = None
    gross_total_amount: NonNegativeMoney | None = None
    net_total_amount: NonNegativeMoney | None = None
    per_share_semantics: Literal["gross", "net", "unknown"]
    total_semantics: Literal["gross", "net", "unknown"]
    payment_status: Literal["paid", "declared", "unknown"]
    dividend_type: Literal["ordinary", "exceptional", "unclassified"]
    reason_codes: tuple[ReasonCode, ...] = ()
    revision: Revision

    @model_validator(mode="after")
    def validate_dividend_evidence(self) -> "NormalizedDividend":
        amounts = (
            self.gross_amount_per_share,
            self.net_amount_per_share,
            self.gross_total_amount,
            self.net_total_amount,
        )
        if self.payment_status == "paid" and (self.payment_date is None or not any(amounts)):
            raise ValueError("paid dividend requires payment date and amount evidence")
        if self.payment_status == "unknown" and not self.reason_codes:
            raise ValueError("unknown dividend status requires a reason code")
        return self


class NormalizedDividendCoverage(ImmutableContractModel):
    """Source-backed coverage for an interval, independent of payment events."""

    company_id: OpaqueIdentifier
    covered_interval_start: date
    covered_interval_end: date
    coverage_basis: Literal["fiscal_year", "trailing_12_months", "source_observed", "unknown"]
    coverage_status: Literal["complete", "partial", "unknown"]
    payment_outcome: Literal["confirmed_no_payment", "payments_recorded", "unresolved"]
    reason_codes: tuple[ReasonCode, ...] = ()
    revision: Revision

    @model_validator(mode="after")
    def validate_coverage(self) -> "NormalizedDividendCoverage":
        if self.covered_interval_end < self.covered_interval_start:
            raise ValueError("covered interval cannot end before it starts")
        if self.coverage_basis == "unknown" and not self.reason_codes:
            raise ValueError("unknown coverage basis requires a reason code")
        if self.coverage_status != "complete" and not self.reason_codes:
            raise ValueError("incomplete or unknown coverage requires a reason code")
        if self.coverage_status == "complete" and (
            self.coverage_basis == "unknown" or self.revision.provenance.basis != "actual"
        ):
            raise ValueError("complete coverage requires a known basis and actual source evidence")
        if self.payment_outcome == "confirmed_no_payment":
            if self.coverage_status != "complete" or self.revision.provenance.basis != "actual":
                raise ValueError("confirmed no-payment requires complete actual coverage evidence")
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


class LongTermObjectiveState(ImmutableContractModel):
    """An objective-specific overall score without conflating deferred and missing states."""

    objective: Literal["growth", "dividend", "balanced"]
    overall_score: AnalyticalMetric[Score]

    @model_validator(mode="after")
    def validate_objective_scope(self) -> "LongTermObjectiveState":
        deferred_reason = {
            "dividend": "dividend_scoring_deferred_v1",
            "balanced": "balanced_scoring_deferred_v1",
        }.get(self.objective)
        if deferred_reason is None:
            if self.overall_score.status == "deferred_scope":
                raise ValueError("Growth must use missing or unsupported evidence, not deferred scope")
            return self
        if (
            self.overall_score.status != "deferred_scope"
            or self.overall_score.value is not None
            or deferred_reason not in self.overall_score.reason_codes
        ):
            raise ValueError(f"{deferred_reason} must be an explicit deferred V1 state")
        return self


class LongTermResult(ImmutableContractModel):
    """Published Long-Term results with isolated objective-specific score states."""

    company_id: OpaqueIdentifier
    growth: LongTermObjectiveState
    dividend: LongTermObjectiveState
    balanced: LongTermObjectiveState
    revision: Revision

    @model_validator(mode="after")
    def validate_objectives(self) -> "LongTermResult":
        if (self.growth.objective, self.dividend.objective, self.balanced.objective) != (
            "growth",
            "dividend",
            "balanced",
        ):
            raise ValueError("Long-Term result must contain each objective exactly once")
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
