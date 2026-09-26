"""Immutable recovery intents and fail-closed register reconciliation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Literal, Protocol, cast

Action = Literal["reset", "deny", "grant", "recovery"]
UTC = timezone.utc
PAGE_SIZE = 100
RUNTIME_SUBJECT = "runtime"


class RegisterError(RuntimeError):
    """A register operation cannot safely establish the requested decision."""


class IntentConflict(RegisterError):
    """An operation ID was reused for a different immutable payload."""


class StalePredecessor(RegisterError):
    """A subject head moved since the intent's predecessor was observed."""


@dataclass(frozen=True, slots=True)
class Intent:
    operation_id: str
    subject: str
    action: Action
    generation: str | None
    operator: str
    predecessor: str | None
    sequence: int
    created_at: datetime
    payload_hash: str

    def __post_init__(self) -> None:
        if not self.operation_id or not self.subject or not self.operator:
            raise ValueError("operation_id, subject, and operator are required")
        if self.action not in ("reset", "deny", "grant", "recovery"):
            raise ValueError("action is not a supported register decision")
        if self.sequence < 1:
            raise ValueError("sequence must be positive")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() != UTC.utcoffset(
            self.created_at
        ):
            raise ValueError("created_at must be an explicit UTC instant")
        if self.payload_hash != intent_payload_hash(
            operation_id=self.operation_id,
            subject=self.subject,
            action=self.action,
            generation=self.generation,
            operator=self.operator,
            predecessor=self.predecessor,
            sequence=self.sequence,
        ):
            raise ValueError("payload_hash does not match the immutable intent payload")

    @property
    def restrictive(self) -> bool:
        return self.action in ("reset", "deny", "recovery")


@dataclass(frozen=True, slots=True)
class SubjectHead:
    subject: str
    operation_id: str
    sequence: int
    storage_generation: int

    def __post_init__(self) -> None:
        if not self.subject or not self.operation_id:
            raise ValueError("subject and operation_id are required")
        if self.sequence < 1 or self.storage_generation < 1:
            raise ValueError("head sequence and storage generation must be positive")


@dataclass(frozen=True, slots=True)
class InventoryPage:
    items: tuple[Intent | SubjectHead, ...]
    next_cursor: str | None
    complete: bool = True


class StorageAdapter(Protocol):
    """Create-only intent and generation-preconditioned head storage."""

    def get_intent(self, operation_id: str) -> Intent | None: ...

    def create_intent(self, intent: Intent) -> bool:
        """Create once; return false if the operation ID already exists."""
        ...

    def get_head(self, subject: str) -> SubjectHead | None: ...

    def compare_and_set_head(
        self,
        subject: str,
        expected_generation: int | None,
        operation_id: str,
        sequence: int,
    ) -> SubjectHead | None:
        """Return the new head, or None when the generation precondition failed."""
        ...

    def list_intents(self, cursor: str | None, *, limit: int) -> InventoryPage: ...

    def list_heads(self, cursor: str | None, *, limit: int) -> InventoryPage: ...


class GcsStorageAdapter:
    """Versioned GCS implementation of the recovery register adapter."""

    def __init__(self, bucket: Any) -> None:
        self._bucket = bucket

    def get_intent(self, operation_id: str) -> Intent | None:
        return cast(Intent | None, _load_record(self._bucket.blob(f"intents/{operation_id}.json"), Intent))

    def create_intent(self, intent: Intent) -> bool:
        blob = self._bucket.blob(f"intents/{intent.operation_id}.json")
        try:
            blob.upload_from_string(_encode_record(intent), content_type="application/json", if_generation_match=0)
        except Exception as error:
            if _is_precondition_failure(error):
                return False
            raise
        return True

    def get_head(self, subject: str) -> SubjectHead | None:
        return cast(SubjectHead | None, _load_record(self._bucket.blob(f"heads/{subject}.json"), SubjectHead))

    def compare_and_set_head(
        self,
        subject: str,
        expected_generation: int | None,
        operation_id: str,
        sequence: int,
    ) -> SubjectHead | None:
        blob = self._bucket.blob(f"heads/{subject}.json")
        value = SubjectHead(subject, operation_id, sequence, 1)
        try:
            blob.upload_from_string(
                _encode_record(value), content_type="application/json", if_generation_match=0 if expected_generation is None else expected_generation
            )
        except Exception as error:
            if _is_precondition_failure(error):
                return None
            raise
        actual_generation = int(blob.generation or 0)
        if actual_generation < 1:
            raise RegisterError("GCS did not return the committed head generation")
        return SubjectHead(subject, operation_id, sequence, actual_generation)

    def list_intents(self, cursor: str | None, *, limit: int) -> InventoryPage:
        return _list_records(self._bucket, "intents/", cursor, limit, Intent)

    def list_heads(self, cursor: str | None, *, limit: int) -> InventoryPage:
        return _list_records(self._bucket, "heads/", cursor, limit, SubjectHead)


def _encode_record(record: Intent | SubjectHead) -> str:
    payload = {"record_type": type(record).__name__, **asdict(record)}
    if isinstance(record, Intent):
        payload["created_at"] = record.created_at.isoformat()
    return json.dumps(payload, sort_keys=True)


def _load_record(blob: Any, record_type: type[Intent] | type[SubjectHead]) -> Intent | SubjectHead | None:
    try:
        raw = blob.download_as_text()
    except Exception as error:
        if _is_not_found(error):
            return None
        raise
    payload = json.loads(raw)
    if record_type is Intent:
        payload.pop("record_type", None)
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        return Intent(**payload)
    payload.pop("record_type", None)
    payload["storage_generation"] = int(blob.generation or payload["storage_generation"])
    return SubjectHead(**payload)


def _list_records(bucket: Any, prefix: str, cursor: str | None, limit: int, record_type: type[Intent] | type[SubjectHead]) -> InventoryPage:
    names = sorted(blob.name for blob in bucket.list_blobs(prefix=prefix) if blob.name.endswith(".json"))
    start = names.index(cursor) + 1 if cursor in names else 0
    selected = names[start : start + limit]
    items = tuple(item for name in selected if (item := _load_record(bucket.blob(name), record_type)) is not None)
    next_cursor = selected[-1] if len(selected) == limit else None
    # A cursor means more complete data is available, not that this page is
    # incomplete. The caller follows the cursor before trusting the inventory.
    return InventoryPage(items=items, next_cursor=next_cursor, complete=True)


def _is_not_found(error: Exception) -> bool:
    return getattr(error, "code", None) == 404 or error.__class__.__name__ == "NotFound"


def _is_precondition_failure(error: Exception) -> bool:
    return getattr(error, "code", None) in (409, 412) or error.__class__.__name__ in {"Conflict", "PreconditionFailed"}


PageLister = Callable[..., InventoryPage]


@dataclass(frozen=True, slots=True)
class Reconciliation:
    globally_blocked: bool
    global_reasons: tuple[str, ...]
    blocked_subjects: frozenset[str]
    subject_reasons: tuple[tuple[str, str], ...]

    @property
    def can_reopen(self) -> bool:
        return not self.globally_blocked

    def subject_is_clear(self, subject: str) -> bool:
        return not self.globally_blocked and subject not in self.blocked_subjects


def intent_payload_hash(
    *,
    operation_id: str,
    subject: str,
    action: Action,
    generation: str | None,
    operator: str,
    predecessor: str | None,
    sequence: int,
) -> str:
    payload = {
        "action": action,
        "generation": generation,
        "operation_id": operation_id,
        "operator": operator,
        "predecessor": predecessor,
        "sequence": sequence,
        "subject": subject,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_intent(
    *,
    operation_id: str,
    subject: str,
    action: Action,
    generation: str | None,
    operator: str,
    predecessor: str | None,
    sequence: int,
    created_at: datetime,
) -> Intent:
    """Build a validated immutable payload; timestamps remain stable on retry."""
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must be an explicit UTC instant")
    return Intent(
        operation_id=operation_id,
        subject=subject,
        action=action,
        generation=generation,
        operator=operator,
        predecessor=predecessor,
        sequence=sequence,
        created_at=created_at.astimezone(UTC),
        payload_hash=intent_payload_hash(
            operation_id=operation_id,
            subject=subject,
            action=action,
            generation=generation,
            operator=operator,
            predecessor=predecessor,
            sequence=sequence,
        ),
    )


def persist_intent(adapter: StorageAdapter, intent: Intent) -> Intent:
    """Persist the intent create-only and accept only an identical retry."""
    if adapter.create_intent(intent):
        return intent
    existing = adapter.get_intent(intent.operation_id)
    if existing is None:
        raise RegisterError("create-only collision could not be reconciled")
    if _intent_identity(existing) != _intent_identity(intent):
        raise IntentConflict("operation ID is already bound to another payload")
    return existing


def confirm_decision(adapter: StorageAdapter, operation_id: str) -> SubjectHead:
    """Advance the subject chain only when the stored predecessor is current."""
    intent = adapter.get_intent(operation_id)
    if intent is None:
        raise RegisterError("decision intent is missing")
    current = adapter.get_head(intent.subject)
    if (
        current is not None
        and current.operation_id == intent.operation_id
        and current.sequence == intent.sequence
    ):
        return current
    current_operation = current.operation_id if current is not None else None
    current_sequence = current.sequence if current is not None else 0
    expected_generation = current.storage_generation if current is not None else None
    if intent.predecessor != current_operation or intent.sequence != current_sequence + 1:
        raise StalePredecessor("intent predecessor is no longer the subject head")
    advanced = adapter.compare_and_set_head(
        intent.subject,
        expected_generation,
        intent.operation_id,
        intent.sequence,
    )
    if advanced is None:
        raise StalePredecessor("subject head changed while advancing the decision")
    return advanced


def verify_completeness(
    adapter: StorageAdapter, *, runtime_subject: str = RUNTIME_SUBJECT
) -> Reconciliation:
    """Inventory and validate all chains before any recovery reopening."""
    try:
        intents = _list_all(adapter.list_intents)
        heads = _list_all(adapter.list_heads)
    except Exception as error:
        return Reconciliation(
            globally_blocked=True,
            global_reasons=(f"register inventory incomplete: {error}",),
            blocked_subjects=frozenset(),
            subject_reasons=(),
        )

    if any(not isinstance(item, Intent) for item in intents) or any(
        not isinstance(item, SubjectHead) for item in heads
    ):
        return Reconciliation(
            globally_blocked=True,
            global_reasons=("register inventory contains an invalid record",),
            blocked_subjects=frozenset(),
            subject_reasons=(),
        )
    intent_records = [item for item in intents if isinstance(item, Intent)]
    head_records = [item for item in heads if isinstance(item, SubjectHead)]
    intent_by_id = {item.operation_id: item for item in intent_records}
    head_by_subject = {item.subject: item for item in head_records}
    if len(intent_by_id) != len(intent_records) or len(head_by_subject) != len(head_records):
        return Reconciliation(
            globally_blocked=True,
            global_reasons=("register inventory contains duplicate identities",),
            blocked_subjects=frozenset(),
            subject_reasons=(),
        )
    global_reasons: list[str] = []
    reasons: dict[str, set[str]] = {}

    if runtime_subject not in head_by_subject:
        global_reasons.append("runtime recovery head is unavailable")

    by_subject: dict[str, list[Intent]] = {}
    for intent in intent_records:
        by_subject.setdefault(intent.subject, []).append(intent)

    for subject in set(by_subject) | set(head_by_subject):
        subject_intents = by_subject.get(subject, [])
        children: dict[str | None, list[Intent]] = {}
        for intent in subject_intents:
            children.setdefault(intent.predecessor, []).append(intent)
        for siblings in children.values():
            if len(siblings) > 1:
                reasons.setdefault(subject, set()).add("decision chain fork")

        head = head_by_subject.get(subject)
        linked: set[str] = set()
        if head is not None:
            operation_id: str | None = head.operation_id
            expected_sequence = head.sequence
            while operation_id is not None:
                if operation_id in linked:
                    reasons.setdefault(subject, set()).add("decision chain cycle")
                    break
                linked.add(operation_id)
                record = intent_by_id.get(operation_id)
                if record is None:
                    reasons.setdefault(subject, set()).add("decision chain link is missing")
                    break
                if record.subject != subject or record.sequence != expected_sequence:
                    reasons.setdefault(subject, set()).add("decision chain identity mismatch")
                    break
                expected_sequence -= 1
                operation_id = record.predecessor
            if expected_sequence != 0 and operation_id is None:
                reasons.setdefault(subject, set()).add("decision chain does not reach its origin")

        for intent in subject_intents:
            if intent.operation_id not in linked and intent.restrictive:
                reasons.setdefault(subject, set()).add("orphan restrictive intent")

    if runtime_subject in reasons:
        global_reasons.append("runtime recovery chain is invalid")

    blocked = frozenset(reasons)
    flattened = tuple(
        (subject, reason)
        for subject in sorted(reasons)
        for reason in sorted(reasons[subject])
    )
    return Reconciliation(
        globally_blocked=bool(global_reasons),
        global_reasons=tuple(global_reasons),
        blocked_subjects=blocked,
        subject_reasons=flattened,
    )


def _intent_identity(intent: Intent) -> tuple[object, ...]:
    return (
        intent.operation_id,
        intent.subject,
        intent.action,
        intent.generation,
        intent.operator,
        intent.predecessor,
        intent.sequence,
        intent.payload_hash,
    )


def _list_all(
    list_page: PageLister,
) -> tuple[Intent | SubjectHead, ...]:
    items: list[Intent | SubjectHead] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        page = list_page(cursor, limit=PAGE_SIZE)
        if not isinstance(page, InventoryPage) or not page.complete:
            raise RegisterError("storage adapter returned incomplete inventory")
        items.extend(page.items)
        if page.next_cursor is None:
            return tuple(items)
        if page.next_cursor in seen_cursors:
            raise RegisterError("storage adapter repeated an inventory cursor")
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor
