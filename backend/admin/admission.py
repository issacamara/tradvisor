"""Ordered, retry-safe admission decisions backed by the recovery register.

The operator boundary persists an immutable register intent before changing the
runtime admission projection. Grants require a complete, clear register; deny
decisions remain available so an incomplete inventory cannot prolong access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from backend.auth.identity import normalize_email
from backend.recovery.register import (
    Action,
    Reconciliation,
    StorageAdapter,
    StalePredecessor,
    SubjectHead,
    Intent,
    InventoryPage,
    build_intent,
    confirm_decision,
    persist_intent,
    verify_completeness,
)

UTC = timezone.utc
ADMISSION_ACTIONS: tuple[Action, ...] = ("deny", "grant")


class AdmissionDecisionError(RuntimeError):
    """A trusted admission decision could not be safely committed."""


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    operation_id: str
    subject: str
    email: str
    action: Action
    generation: str | None
    operator: str
    predecessor: str | None
    sequence: int
    created_at: datetime

    def __post_init__(self) -> None:
        if self.action not in ADMISSION_ACTIONS:
            raise ValueError("admission action must be deny or grant")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() != UTC.utcoffset(self.created_at):
            raise ValueError("created_at must be an explicit UTC instant")
        if not self.subject or not self.email:
            raise ValueError("subject and email are required")


@dataclass(frozen=True, slots=True)
class AdmissionRecord:
    """The materialized state read by the live request admission check."""

    subject: str
    email: str
    active: bool
    decision_operation_id: str
    decision_sequence: int
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.subject or not self.email or not self.decision_operation_id:
            raise ValueError("admission records require identity and decision evidence")
        if self.decision_sequence < 1:
            raise ValueError("decision sequence must be positive")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() != UTC.utcoffset(self.updated_at):
            raise ValueError("updated_at must be an explicit UTC instant")


class AdmissionStore(StorageAdapter, Protocol):
    """Register storage plus a compare-and-set admission projection."""

    def get_admission(self, subject: str) -> AdmissionRecord | None: ...

    def get_operation_email(self, operation_id: str) -> str | None: ...

    def create_operation_email(self, operation_id: str, email: str) -> bool: ...

    def compare_and_set_admission(
        self,
        subject: str,
        expected_decision_sequence: int | None,
        record: AdmissionRecord,
    ) -> AdmissionRecord | None: ...


class FirestoreAdmissionProjection:
    """Concrete compare-and-set projection for the live admission document."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_admission(self, subject: str) -> AdmissionRecord | None:
        snapshot = self._client.collection("application_admissions").document(subject).get()
        if not snapshot.exists:
            return None
        record = snapshot.to_dict()
        if not isinstance(record, dict):
            return None
        try:
            return AdmissionRecord(
                subject=subject,
                email=str(record["email"]),
                active=record["active"] is True,
                decision_operation_id=str(record["decision_operation_id"]),
                decision_sequence=int(record["decision_sequence"]),
                updated_at=record["updated_at"],
            )
        except (KeyError, TypeError, ValueError):
            return None

    def get_operation_email(self, operation_id: str) -> str | None:
        snapshot = self._client.collection("application_admission_operations").document(operation_id).get()
        if not snapshot.exists:
            return None
        record = snapshot.to_dict()
        return record.get("email") if isinstance(record, dict) and isinstance(record.get("email"), str) else None

    def create_operation_email(self, operation_id: str, email: str) -> bool:
        reference = self._client.collection("application_admission_operations").document(operation_id)
        if reference.get().exists:
            return False
        reference.create({"email": email})
        return True

    def compare_and_set_admission(
        self,
        subject: str,
        expected_decision_sequence: int | None,
        record: AdmissionRecord,
    ) -> AdmissionRecord | None:
        transaction = self._client.transaction()
        reference = self._client.collection("application_admissions").document(subject)
        fence_reference = self._client.collection("application_admission_denials").document(subject)
        snapshot = transaction.get(reference)
        if not hasattr(snapshot, "exists"):
            snapshot = next(snapshot, None)
        if snapshot is None:
            return None
        current = None
        if snapshot.exists:
            fields = snapshot.to_dict() or {}
            try:
                current = int(fields["decision_sequence"])
            except (KeyError, TypeError, ValueError):
                return None
        fence_snapshot = transaction.get(fence_reference)
        if not hasattr(fence_snapshot, "exists"):
            fence_snapshot = next(fence_snapshot, None)
        fence_sequence = 0
        if fence_snapshot is not None and fence_snapshot.exists:
            fence_fields = fence_snapshot.to_dict() or {}
            try:
                fence_sequence = int(fence_fields["decision_sequence"])
            except (KeyError, TypeError, ValueError):
                return None
        if current != expected_decision_sequence:
            return None
        transaction.set(reference, {
            "active": record.active,
            "email": record.email,
            "decision_operation_id": record.decision_operation_id,
            "decision_sequence": record.decision_sequence,
            "updated_at": record.updated_at,
        })
        if not record.active and record.decision_sequence > fence_sequence:
            transaction.set(fence_reference, {
                "decision_operation_id": record.decision_operation_id,
                "decision_sequence": record.decision_sequence,
                "updated_at": record.updated_at,
            })
        transaction.commit()
        return record


class FirestoreAdmissionStore:
    """Compose the durable register adapter with the live Firestore projection."""

    def __init__(self, register: StorageAdapter, client: Any) -> None:
        self._register = register
        self._projection = FirestoreAdmissionProjection(client)

    def get_intent(self, operation_id: str) -> Intent | None:
        return self._register.get_intent(operation_id)

    def create_intent(self, intent: Intent) -> bool:
        return self._register.create_intent(intent)

    def get_head(self, subject: str) -> SubjectHead | None:
        return self._register.get_head(subject)

    def compare_and_set_head(
        self, subject: str, expected_generation: int | None, operation_id: str, sequence: int
    ) -> SubjectHead | None:
        return self._register.compare_and_set_head(
            subject, expected_generation, operation_id, sequence
        )

    def list_intents(self, cursor: str | None, *, limit: int) -> InventoryPage:
        return self._register.list_intents(cursor, limit=limit)

    def list_heads(self, cursor: str | None, *, limit: int) -> InventoryPage:
        return self._register.list_heads(cursor, limit=limit)

    def get_admission(self, subject: str) -> AdmissionRecord | None:
        return self._projection.get_admission(subject)

    def get_operation_email(self, operation_id: str) -> str | None:
        return self._projection.get_operation_email(operation_id)

    def create_operation_email(self, operation_id: str, email: str) -> bool:
        return self._projection.create_operation_email(operation_id, email)

    def compare_and_set_admission(
        self,
        subject: str,
        expected_decision_sequence: int | None,
        record: AdmissionRecord,
    ) -> AdmissionRecord | None:
        return self._projection.compare_and_set_admission(
            subject, expected_decision_sequence, record
        )


def apply_admission_decision(
    store: AdmissionStore,
    decision: AdmissionDecision,
    *,
    runtime_subject: str = "runtime",
) -> AdmissionRecord:
    """Confirm an ordered decision, then atomically publish its live projection.

    Replaying an identical operation returns the already-published record. A
    stale predecessor, incomplete grant inventory, or projection race fails
    without turning a grant into an implicit allow.
    """

    requested_intent = build_intent(
        operation_id=decision.operation_id,
        subject=decision.subject,
        action=decision.action,
        generation=decision.generation,
        operator=decision.operator,
        predecessor=decision.predecessor,
        sequence=decision.sequence,
        created_at=decision.created_at,
    )
    normalized_email = normalize_email(decision.email)
    stored_email = store.get_operation_email(decision.operation_id)
    if stored_email is not None and stored_email != normalized_email:
        raise AdmissionDecisionError("operation ID is bound to another admission email")
    if stored_email is None and not store.create_operation_email(decision.operation_id, normalized_email):
        stored_email = store.get_operation_email(decision.operation_id)
        if stored_email != normalized_email:
            raise AdmissionDecisionError("operation ID is bound to another admission email")
    stored_intent = store.get_intent(decision.operation_id)
    if stored_intent is not None and not _same_intent(stored_intent, requested_intent):
        raise AdmissionDecisionError("operation ID is bound to another immutable payload")
    current = store.get_admission(decision.subject)
    if current is not None and current.decision_operation_id == decision.operation_id:
        if stored_intent is None:
            raise AdmissionDecisionError("admission projection has no matching durable intent")
        try:
            confirm_decision(store, decision.operation_id)
        except StalePredecessor as error:
            raise AdmissionDecisionError("admission decision is stale; refresh the current subject head") from error
        return current

    reconciliation = verify_completeness(store, runtime_subject=runtime_subject)
    if decision.action == "grant" and not reconciliation.subject_is_clear(decision.subject):
        raise AdmissionDecisionError(_grant_block_reason(reconciliation, decision.subject))

    try:
        persist_intent(store, requested_intent)
    except StalePredecessor as error:
        raise AdmissionDecisionError("admission decision is stale; refresh the current subject head") from error

    expected_sequence = None if current is None else current.decision_sequence
    record = AdmissionRecord(
        subject=decision.subject,
        email=normalized_email,
        active=decision.action == "grant",
        decision_operation_id=decision.operation_id,
        decision_sequence=decision.sequence,
        updated_at=decision.created_at.astimezone(UTC),
    )
    if decision.action == "deny":
        published = store.compare_and_set_admission(decision.subject, expected_sequence, record)
        if published is None:
            latest = store.get_admission(decision.subject)
            if latest is not None and latest.decision_operation_id == decision.operation_id:
                published = latest
            else:
                raise AdmissionDecisionError("admission projection changed while publishing denial")
        try:
            head = confirm_decision(store, decision.operation_id)
        except StalePredecessor as error:
            raise AdmissionDecisionError("denial was published but ordered finalization is stale") from error
        if head.operation_id != decision.operation_id:
            raise AdmissionDecisionError("confirmed denial head does not match the requested operation")
        return published

    try:
        head = confirm_decision(store, decision.operation_id)
    except StalePredecessor as error:
        raise AdmissionDecisionError("admission decision is stale; refresh the current subject head") from error
    if head.operation_id != decision.operation_id:
        raise AdmissionDecisionError("confirmed decision head does not match the requested operation")
    published = store.compare_and_set_admission(decision.subject, expected_sequence, record)
    if published is None:
        latest = store.get_admission(decision.subject)
        if latest is not None and latest.decision_operation_id == decision.operation_id:
            return latest
        raise AdmissionDecisionError("admission projection changed while publishing decision")
    return published


def _same_intent(left: Intent, right: Intent) -> bool:
    return (
        left.operation_id == right.operation_id
        and left.subject == right.subject
        and left.action == right.action
        and left.generation == right.generation
        and left.operator == right.operator
        and left.predecessor == right.predecessor
        and left.sequence == right.sequence
        and left.payload_hash == right.payload_hash
    )


def _grant_block_reason(reconciliation: Reconciliation, subject: str) -> str:
    if reconciliation.globally_blocked:
        return "grant blocked until the recovery register is complete"
    if subject in reconciliation.blocked_subjects:
        return "grant blocked until the subject recovery chain is reconciled"
    return "grant blocked by recovery reconciliation"


__all__ = [
    "AdmissionDecision",
    "AdmissionDecisionError",
    "AdmissionRecord",
    "AdmissionStore",
    "apply_admission_decision",
]
