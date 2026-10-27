"""Sanitized contracts for completion-driven analytical publication."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_serializer, field_validator, model_validator

from backend.contracts.analysis import ImmutableContractModel


SourceKind = Literal["shares", "financials", "ratings"]
EligibleSourceKind = Literal["shares", "financials"]
ImportStatus = Literal["succeeded", "failed"]
PublicationRequestState = Literal["coalescing", "dispatched", "no_request", "completed"]
PublicationOutcomeCode = Literal[
    "dispatched",
    "unchanged_input_no_op",
    "import_failed_no_request",
    "analytical_failed",
    "published",
]

MAX_READY_INPUTS = 2
MAX_ANALYTICAL_ATTEMPTS = 3
RevisionFingerprint = Annotated[
    str,
    StringConstraints(pattern=r"^[a-f0-9]{64}$", strict=True),
]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("instant must be an explicit UTC RFC3339 timestamp")
    return value.astimezone(timezone.utc)


class ManagedWriteReceipt(ImmutableContractModel):
    """Sanitized proof that a Terraform-managed BigQuery write completed."""

    revision_fingerprint: RevisionFingerprint
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def validate_completed_at(cls, value: datetime | str) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _require_utc(value)

    @field_serializer("completed_at")
    def serialize_completed_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")


class ManagedImportCompletion(ImmutableContractModel):
    """A managed import outcome with no source rows, payloads, or targets."""

    source: SourceKind
    status: ImportStatus
    managed_write: ManagedWriteReceipt | None = None

    @model_validator(mode="after")
    def require_receipt_only_for_success(self) -> "ManagedImportCompletion":
        if self.status == "succeeded" and self.managed_write is None:
            raise ValueError("successful import requires a managed-write receipt")
        if self.status == "failed" and self.managed_write is not None:
            raise ValueError("failed import cannot include a managed-write receipt")
        return self

    @property
    def triggers_publication(self) -> bool:
        return self.status == "succeeded" and self.source in {"shares", "financials"}


class ReadySourceInput(ImmutableContractModel):
    """One eligible, already-written analytical input represented by a digest."""

    source: EligibleSourceKind
    revision_fingerprint: RevisionFingerprint


class SourceInputIdentity(ImmutableContractModel):
    """Order-independent identity of the bounded, sanitized ready input set."""

    inputs: tuple[ReadySourceInput, ...]
    digest: RevisionFingerprint

    @model_validator(mode="after")
    def validate_identity(self) -> "SourceInputIdentity":
        if not 1 <= len(self.inputs) <= MAX_READY_INPUTS:
            raise ValueError("ready input set must contain one or two eligible sources")
        if len({input.source for input in self.inputs}) != len(self.inputs):
            raise ValueError("ready input set cannot repeat a source")
        canonical = tuple(sorted(self.inputs, key=lambda input: input.source))
        if self.inputs != canonical:
            raise ValueError("ready inputs must be sorted by source")
        if self.digest != self._digest(canonical):
            raise ValueError("source-input identity does not match ready inputs")
        return self

    @classmethod
    def from_inputs(cls, inputs: tuple[ReadySourceInput, ...]) -> "SourceInputIdentity":
        canonical = tuple(sorted(inputs, key=lambda input: input.source))
        return cls(inputs=canonical, digest=cls._digest(canonical))

    @staticmethod
    def _digest(inputs: tuple[ReadySourceInput, ...]) -> str:
        payload = [{"source": input.source, "revision": input.revision_fingerprint} for input in inputs]
        return hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()


class PublicationControlOutcome(ImmutableContractModel):
    """A finite, retry-safe control-plane outcome without free-form failure data."""

    state: PublicationRequestState
    outcome: PublicationOutcomeCode
    input_identity: SourceInputIdentity | None = None
    analytical_attempts: Annotated[int, Field(strict=True, ge=0, le=MAX_ANALYTICAL_ATTEMPTS)] = 0

    @model_validator(mode="after")
    def validate_state_and_outcome(self) -> "PublicationControlOutcome":
        expected = {
            "dispatched": ("dispatched", True, 0),
            "unchanged_input_no_op": ("completed", True, 0),
            "import_failed_no_request": ("no_request", False, 0),
            "analytical_failed": ("completed", True, None),
            "published": ("completed", True, None),
        }[self.outcome]
        state, requires_identity, exact_attempts = expected
        if self.state != state:
            raise ValueError("outcome must use its bounded request state")
        if (self.input_identity is not None) != requires_identity:
            raise ValueError("outcome has an invalid source-input identity")
        if exact_attempts is not None and self.analytical_attempts != exact_attempts:
            raise ValueError("outcome has an invalid analytical attempt count")
        if exact_attempts is None and self.analytical_attempts < 1:
            raise ValueError("analytical terminal outcome requires an attempted job")
        return self
