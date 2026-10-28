"""Credential-free contracts for completion-driven publication control."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.contracts.publication_control import (
    ManagedImportCompletion,
    ManagedWriteReceipt,
    PublicationControlOutcome,
    ReadySourceInput,
    SourceInputIdentity,
)


FINGERPRINT_A = "a" * 64
FINGERPRINT_B = "b" * 64
NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def receipt() -> ManagedWriteReceipt:
    return ManagedWriteReceipt(revision_fingerprint=FINGERPRINT_A, completed_at=NOW)


def test_managed_write_receipt_accepts_json_rfc3339_timestamp() -> None:
    receipt = ManagedWriteReceipt(
        revision_fingerprint=FINGERPRINT_A,
        completed_at="2026-10-18T00:00:00.123456Z",
    )

    assert receipt.completed_at == datetime(2026, 10, 18, 0, 0, 0, 123456, tzinfo=timezone.utc)


def identity() -> SourceInputIdentity:
    return SourceInputIdentity.from_inputs(
        (ReadySourceInput(source="shares", revision_fingerprint=FINGERPRINT_A),)
    )


@pytest.mark.parametrize("source", ["shares", "financials"])
def test_successful_eligible_completion_triggers_publication(source: str) -> None:
    completion = ManagedImportCompletion(source=source, status="succeeded", managed_write=receipt())

    assert completion.triggers_publication is True


def test_ratings_completion_is_explicitly_non_triggering() -> None:
    completion = ManagedImportCompletion(source="ratings", status="succeeded", managed_write=receipt())

    assert completion.triggers_publication is False


def test_successful_completion_requires_a_managed_write_receipt() -> None:
    with pytest.raises(ValidationError, match="managed-write receipt"):
        ManagedImportCompletion(source="shares", status="succeeded")


def test_failed_completion_carries_no_managed_write_receipt() -> None:
    with pytest.raises(ValidationError, match="failed import"):
        ManagedImportCompletion(source="financials", status="failed", managed_write=receipt())


def test_source_input_identity_is_deterministic_order_independent_and_sanitized() -> None:
    shares = ReadySourceInput(source="shares", revision_fingerprint=FINGERPRINT_A)
    financials = ReadySourceInput(source="financials", revision_fingerprint=FINGERPRINT_B)

    first = SourceInputIdentity.from_inputs((shares, financials))
    second = SourceInputIdentity.from_inputs((financials, shares))
    changed = SourceInputIdentity.from_inputs(
        (shares, ReadySourceInput(source="financials", revision_fingerprint=FINGERPRINT_A))
    )

    assert first == second
    assert first.digest != changed.digest
    assert first.model_dump() == {
        "inputs": (
            {"source": "financials", "revision_fingerprint": FINGERPRINT_B},
            {"source": "shares", "revision_fingerprint": FINGERPRINT_A},
        ),
        "digest": first.digest,
    }


@pytest.mark.parametrize(
    ("outcome", "state", "attempts"),
    [
        ("dispatched", "dispatched", 0),
        ("unchanged_input_no_op", "completed", 0),
        ("analytical_failed", "completed", 1),
        ("published", "completed", 1),
    ],
)
def test_request_outcomes_are_finite_and_typed(outcome: str, state: str, attempts: int) -> None:
    result = PublicationControlOutcome(
        outcome=outcome,
        state=state,
        input_identity=identity(),
        analytical_attempts=attempts,
    )

    assert result.outcome == outcome


def test_failed_import_outcome_never_creates_a_request() -> None:
    result = PublicationControlOutcome(
        outcome="import_failed_no_request",
        state="no_request",
    )

    assert result.input_identity is None


def test_outcomes_reject_free_form_or_inconsistent_state() -> None:
    with pytest.raises(ValidationError, match="bounded request state"):
        PublicationControlOutcome(
            outcome="published", state="dispatched", input_identity=identity(), analytical_attempts=1
        )
