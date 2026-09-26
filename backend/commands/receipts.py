"""Recovery-fenced, owner-global idempotency receipt handling."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

from pydantic import TypeAdapter, ValidationError

from backend.contracts.envelopes import CommandMetadata, CommandReceipt, IdempotencyKey
from backend.contracts.paper import PaperCommandReceipt, PortfolioControl
from backend.contracts.routes import (
    HttpMethod,
    PaperMutationRequest,
    canonical_command_fingerprint,
)
from backend.contracts.scalars import OpaqueIdentifier
from backend.store.repositories import (
    PaperRepositories,
    TransactionalStore,
    VersionedDocument,
)
from backend.store.transactions import Transaction, run_transaction

UTC = timezone.utc
FIRST_SUBMISSION_AGE = timedelta(minutes=5)
MAX_CLOCK_AHEAD = timedelta(seconds=60)
RECEIPT_RETENTION = timedelta(days=30)
RECEIPT_SCHEMA_VERSION = 1
_KEY_ADAPTER = TypeAdapter(IdempotencyKey)
_KEY_TIMESTAMP = re.compile(r"^([0-9]{13})\.")


class ReceiptError(ValueError):
    """A command must be rejected before its business mutation is applied."""

    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ReceiptOutcome:
    """Minimal committed command outcome supplied by the mutation handler."""

    operation: OpaqueIdentifier
    http_status: int
    outcome_id: OpaqueIdentifier | None = None
    generation: OpaqueIdentifier | None = None
    state_version: int | None = None


@dataclass(frozen=True, slots=True)
class ReceiptResult:
    receipt: CommandReceipt
    replayed: bool


def parse_idempotency_key(value: object) -> IdempotencyKey:
    """Validate the owner-global timestamped key supplied by the client."""

    try:
        return _KEY_ADAPTER.validate_python(value)
    except ValidationError as error:
        raise ReceiptError(
            "validation_failed", "Malformed Idempotency-Key.", status_code=422
        ) from error


def key_issued_at(key: IdempotencyKey) -> datetime:
    """Decode the millisecond UTC timestamp from a validated key."""

    match = _KEY_TIMESTAMP.match(key)
    if match is None:
        raise ReceiptError("validation_failed", "Malformed Idempotency-Key.", status_code=422)
    milliseconds = int(match.group(1))
    return datetime.fromtimestamp(milliseconds // 1000, tz=UTC).replace(
        microsecond=(milliseconds % 1000) * 1000
    )


def validate_first_submission_window(key: IdempotencyKey, now: datetime) -> None:
    """Enforce inclusive five-minute age and sixty-second future clock bounds."""

    now = _as_utc(now)
    issued_at = key_issued_at(key)
    if issued_at < now - FIRST_SUBMISSION_AGE:
        raise ReceiptError("command_window_expired", "Command key is outside its submission window.")
    if issued_at > now + MAX_CLOCK_AHEAD:
        raise ReceiptError("command_clock_ahead", "Command key is too far ahead of server time.")


def fingerprint_request(
    method: HttpMethod, path: str, request: PaperMutationRequest
) -> str:
    """Fingerprint a validated route request with contract-normalized decimals."""

    return canonical_command_fingerprint(method, path, request)


def execute_with_receipt(
    store: TransactionalStore,
    repositories: PaperRepositories,
    command: CommandMetadata,
    request_fingerprint: str,
    *,
    now: datetime,
    apply_mutation: Callable[[Transaction], ReceiptOutcome],
    max_attempts: int = 5,
) -> ReceiptResult:
    """Atomically apply one mutation and its receipt, replaying committed outcomes.

    ``apply_mutation`` may run more than once and therefore must perform every
    business write through the supplied transaction, with no external effects.
    The receipt key is derived from the authenticated owner's repository scope.
    """

    now = _as_utc(now)
    if not re.fullmatch(r"[0-9a-f]{64}", request_fingerprint):
        raise ValueError("request_fingerprint must be a lowercase SHA-256 digest")

    def transact(transaction: Transaction) -> ReceiptResult:
        control_doc = store.get_in_transaction(transaction, repositories.control_key())
        if control_doc is None:
            raise ReceiptError("service_unavailable", "Current recovery state is unavailable.", status_code=503)
        control = PortfolioControl.model_validate_json(control_doc.record.model_dump_json())

        # Recovery must fence stale commands before even looking up their keys.
        if not command.matches_recovery(control.recovery_id):
            raise ReceiptError("recovery_mismatch", "Refresh recovery state before submitting this command.")

        receipt_key = repositories.receipt_key(command.idempotency_key)
        existing_doc = store.get_in_transaction(transaction, receipt_key)
        if existing_doc is not None:
            existing = PaperCommandReceipt.model_validate_json(
                existing_doc.record.model_dump_json()
            )
            if existing.owner_uid != repositories.owner_uid:
                raise ReceiptError("idempotency_conflict", "Idempotency key is already in use.")
            if existing.expires_at <= now:
                raise ReceiptError("command_window_expired", "The retained command receipt has expired.")
            if (
                existing.idempotency_key != command.idempotency_key
                or existing.recovery_id != command.recovery_id
                or existing.request_fingerprint != request_fingerprint
            ):
                raise ReceiptError("idempotency_conflict", "Idempotency key was used for another intent.")
            if (
                existing.generation is not None
                and control.active_generation != existing.generation
            ):
                raise ReceiptError(
                    "generation_superseded",
                    "The command belongs to a superseded portfolio generation.",
                )
            replay = _public_receipt(existing, replayed=True)
            return ReceiptResult(receipt=replay, replayed=True)

        # A physically purged receipt cannot turn an old key into a fresh write.
        validate_first_submission_window(command.idempotency_key, now)
        outcome = apply_mutation(transaction)
        accepted_at = now
        receipt = PaperCommandReceipt(
            owner_uid=repositories.owner_uid,
            idempotency_key=command.idempotency_key,
            request_fingerprint=request_fingerprint,
            recovery_id=command.recovery_id,
            operation=outcome.operation,
            outcome_id=outcome.outcome_id,
            generation=outcome.generation,
            state_version=outcome.state_version,
            http_status=outcome.http_status,
            replayed=False,
            accepted_at=accepted_at,
            expires_at=accepted_at + RECEIPT_RETENTION,
        )
        store.put_in_transaction(
            transaction,
            VersionedDocument(
                key=receipt_key,
                schema_version=RECEIPT_SCHEMA_VERSION,
                state_version=0,
                record=receipt,
            ),
        )
        return ReceiptResult(receipt=_public_receipt(receipt, replayed=False), replayed=False)

    return run_transaction(store, transact, max_attempts=max_attempts)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("now must be an explicit UTC instant")
    return value.astimezone(UTC)


def _public_receipt(receipt: PaperCommandReceipt, *, replayed: bool) -> CommandReceipt:
    return CommandReceipt.model_validate(
        {
            "operation": receipt.operation,
            "outcome_id": receipt.outcome_id,
            "generation": receipt.generation,
            "state_version": receipt.state_version,
            "http_status": receipt.http_status,
            "replayed": replayed,
            "accepted_at": receipt.accepted_at,
            "expires_at": receipt.expires_at,
        }
    )
