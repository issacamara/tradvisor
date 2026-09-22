"""Boundary tests for API v0.13 scalar and envelope contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from math import inf, nan
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from backend.contracts.envelopes import ApiError, CommandMetadata, ErrorEnvelope, ResponseEnvelope, ResponseMeta
from backend.contracts.scalars import (
    INT64_MAX,
    INT64_MIN,
    MAX_COMMAND_BYTES,
    FeeRatePct,
    NonNegativeMoney,
    Score,
    SignedMoney,
    StartingCash,
    WholeShares,
)


def test_money_accepts_signed_int64_endpoints_and_rejects_overflow() -> None:
    maximum = SignedMoney(amount="9223372036854.775807", currency="XOF")
    minimum = SignedMoney(amount="-9223372036854.775808", currency="XOF")

    assert maximum.micros == INT64_MAX
    assert minimum.micros == INT64_MIN
    assert maximum.model_dump(mode="json") == {
        "amount": "9223372036854.775807",
        "currency": "XOF",
    }

    with pytest.raises(ValidationError):
        SignedMoney(amount="9223372036854.775808", currency="XOF")
    with pytest.raises(ValidationError):
        SignedMoney(amount="-9223372036854.775809", currency="XOF")


@pytest.mark.parametrize("amount", ["1.0000001", "1e6", "+1", "1,000", "NaN", "Infinity"])
def test_money_rejects_unsupported_precision_and_nonfinite_values(amount: str) -> None:
    with pytest.raises(ValidationError):
        NonNegativeMoney(amount=amount, currency="XOF")


@pytest.mark.parametrize("amount", ["99999", "100000.1", "100000000.1", "100000001"])
def test_starting_cash_requires_whole_xof_within_bounds(amount: str) -> None:
    with pytest.raises(ValidationError):
        StartingCash(amount=amount, currency="XOF")


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("100000", "100000.000000"),
        ("1000000", "1000000.000000"),
        ("100000000", "100000000.000000"),
    ],
)
def test_starting_cash_valid_boundaries_and_default_serialize_canonically(
    amount: str, expected: str
) -> None:
    assert StartingCash(amount=amount, currency="XOF").model_dump(mode="json") == {
        "amount": expected,
        "currency": "XOF",
    }


class FeePreference(BaseModel):
    fee_rate_pct: FeeRatePct


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", "0"),
        ("12.340000", "12.34"),
        ("999999999999.999999", "999999999999.999999"),
    ],
)
def test_fee_rate_pct_serializes_a_canonical_supported_decimal(value: str, expected: str) -> None:
    assert FeePreference(fee_rate_pct=value).model_dump(mode="json") == {
        "fee_rate_pct": expected
    }


@pytest.mark.parametrize(
    "value",
    ["-0.1", "1e3", "1000000000000", "1.0000001", "NaN", "Infinity"],
)
def test_fee_rate_pct_rejects_invalid_or_out_of_range_strings(value: str) -> None:
    with pytest.raises(ValidationError):
        FeePreference(fee_rate_pct=value)


class ShareCommand(BaseModel):
    quantity: WholeShares


@pytest.mark.parametrize("quantity", [0, 1.0, 1_000_000_001])
def test_whole_share_bounds_reject_invalid_quantities(quantity: Any) -> None:
    with pytest.raises(ValidationError):
        ShareCommand(quantity=quantity)


class ScorePayload(BaseModel):
    score: Score


@pytest.mark.parametrize("score", [nan, inf, -inf])
def test_scores_reject_nonfinite_numbers(score: float) -> None:
    with pytest.raises(ValidationError):
        ScorePayload(score=score)


def test_command_rejects_unknown_fields_and_oversized_body() -> None:
    metadata = {
        "idempotency_key": "1726920000000.0123456789abcdef0123456789abcdef",
        "recovery_id": "recovery-20260922",
        "content_length": MAX_COMMAND_BYTES + 1,
        "issued_at": datetime(2026, 9, 22, tzinfo=timezone.utc),
    }
    with pytest.raises(ValidationError):
        CommandMetadata.model_validate(metadata)

    metadata["content_length"] = 1
    metadata["unexpected"] = True
    with pytest.raises(ValidationError):
        CommandMetadata.model_validate(metadata)


def test_envelopes_serialize_utc_and_safe_errors_without_unknown_fields() -> None:
    meta = ResponseMeta(
        request_id="request-123",
        server_time=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        schema_version=1,
        recovery_id="recovery-20260922",
    )
    response = ResponseEnvelope[dict[str, str]](data={"state": "ok"}, meta=meta)
    error = ErrorEnvelope(
        error=ApiError(
            code="generation_mismatch",
            message="The simulation changed. Refresh before submitting.",
            retryable=False,
            request_id="request-123",
        )
    )

    assert response.model_dump(mode="json")["meta"]["server_time"] == "2026-09-22T12:00:00Z"
    assert error.model_dump(mode="json") == {
        "error": {
            "code": "generation_mismatch",
            "message": "The simulation changed. Refresh before submitting.",
            "retryable": False,
            "request_id": "request-123",
        }
    }

    assert ResponseMeta.model_validate_json(
        '{"request_id":"request-123","server_time":"2026-09-22T12:00:00Z","schema_version":1}'
    ).server_time == datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def test_command_metadata_requires_utc_recovery_fence_and_paired_versions() -> None:
    payload = {
        "idempotency_key": "1726920000000.0123456789abcdef0123456789abcdef",
        "recovery_id": "recovery-20260922",
        "request_fingerprint": "fingerprint-20260922",
        "content_length": 100,
        "issued_at": datetime(2026, 9, 22, tzinfo=timezone.utc),
        "expected_generation": "generation-1",
        "expected_state_version": 0,
    }
    assert CommandMetadata.model_validate(payload).model_dump(mode="json")["issued_at"].endswith("Z")

    payload["issued_at"] = datetime(2026, 9, 22)
    with pytest.raises(ValidationError):
        CommandMetadata.model_validate(payload)
