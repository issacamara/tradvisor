from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from backend.recovery.register import (
    Action,
    Intent,
    IntentConflict,
    InventoryPage,
    RUNTIME_SUBJECT,
    StalePredecessor,
    SubjectHead,
    build_intent,
    confirm_decision,
    persist_intent,
    verify_completeness,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


@dataclass
class FakeStorage:
    intents: dict[str, Intent] = field(default_factory=dict)
    heads: dict[str, SubjectHead] = field(default_factory=dict)
    incomplete_intent_listing: bool = False

    def get_intent(self, operation_id: str) -> Intent | None:
        return self.intents.get(operation_id)

    def create_intent(self, intent: Intent) -> bool:
        if intent.operation_id in self.intents:
            return False
        self.intents[intent.operation_id] = intent
        return True

    def get_head(self, subject: str) -> SubjectHead | None:
        return self.heads.get(subject)

    def compare_and_set_head(
        self,
        subject: str,
        expected_generation: int | None,
        operation_id: str,
        sequence: int,
    ) -> SubjectHead | None:
        current = self.heads.get(subject)
        actual_generation = current.storage_generation if current is not None else None
        if actual_generation != expected_generation:
            return None
        updated = SubjectHead(
            subject=subject,
            operation_id=operation_id,
            sequence=sequence,
            storage_generation=(actual_generation or 0) + 1,
        )
        self.heads[subject] = updated
        return updated

    def list_intents(self, cursor: str | None, *, limit: int) -> InventoryPage:
        assert cursor is None
        assert limit > 0
        return InventoryPage(
            tuple(self.intents.values()),
            None,
            complete=not self.incomplete_intent_listing,
        )

    def list_heads(self, cursor: str | None, *, limit: int) -> InventoryPage:
        assert cursor is None
        assert limit > 0
        return InventoryPage(tuple(self.heads.values()), None)


def intent(
    operation_id: str,
    *,
    subject: str = "portfolio-1",
    action: Action = "reset",
    predecessor: str | None = None,
    sequence: int = 1,
    created_at: datetime = NOW,
) -> Intent:
    return build_intent(
        operation_id=operation_id,
        subject=subject,
        action=action,
        generation="generation-1",
        operator="operator-1",
        predecessor=predecessor,
        sequence=sequence,
        created_at=created_at,
    )


def with_runtime_head(storage: FakeStorage) -> None:
    runtime = intent("runtime-root", subject=RUNTIME_SUBJECT, action="recovery")
    persist_intent(storage, runtime)
    storage.heads[RUNTIME_SUBJECT] = SubjectHead(RUNTIME_SUBJECT, "runtime-root", 1, 1)


def test_create_only_retry_returns_identity_and_rejects_payload_mismatch() -> None:
    storage = FakeStorage()
    original = intent("operation-1")
    assert persist_intent(storage, original) is original

    # Persistence timestamps may differ on retry; the stored immutable payload wins.
    retry = intent("operation-1", created_at=datetime(2026, 9, 26, 13, 0, tzinfo=UTC))
    assert persist_intent(storage, retry) is original
    assert storage.intents["operation-1"] is original

    changed = intent("operation-1", action="grant")
    with pytest.raises(IntentConflict, match="another payload"):
        persist_intent(storage, changed)
    assert storage.intents["operation-1"] is original


def test_head_advance_rejects_stale_predecessor() -> None:
    storage = FakeStorage()
    persist_intent(storage, intent("stale-operation"))
    storage.heads["portfolio-1"] = SubjectHead(
        "portfolio-1", "newer-operation", 1, 4
    )

    with pytest.raises(StalePredecessor, match="no longer the subject head"):
        confirm_decision(storage, "stale-operation")
    assert storage.heads["portfolio-1"].operation_id == "newer-operation"


def test_confirm_retry_after_committed_head_is_idempotent() -> None:
    storage = FakeStorage()
    persist_intent(storage, intent("operation-1"))

    first = confirm_decision(storage, "operation-1")
    retry = confirm_decision(storage, "operation-1")

    assert retry == first


def test_missing_head_link_blocks_subject() -> None:
    storage = FakeStorage()
    with_runtime_head(storage)
    storage.heads["portfolio-1"] = SubjectHead("portfolio-1", "missing-op", 1, 2)

    result = verify_completeness(storage)

    assert "portfolio-1" in result.blocked_subjects
    assert ("portfolio-1", "decision chain link is missing") in result.subject_reasons


def test_fork_blocks_subject_even_when_one_branch_is_the_head() -> None:
    storage = FakeStorage()
    persist_intent(storage, intent("branch-a"))
    persist_intent(storage, intent("branch-b"))
    storage.heads["portfolio-1"] = SubjectHead("portfolio-1", "branch-a", 1, 1)
    with_runtime_head(storage)

    result = verify_completeness(storage)

    assert "portfolio-1" in result.blocked_subjects
    assert ("portfolio-1", "decision chain fork") in result.subject_reasons


def test_orphan_restrictive_intent_blocks_subject() -> None:
    storage = FakeStorage()
    with_runtime_head(storage)
    persist_intent(storage, intent("unlinked-reset"))

    result = verify_completeness(storage)

    assert "portfolio-1" in result.blocked_subjects
    assert ("portfolio-1", "orphan restrictive intent") in result.subject_reasons
    assert not result.globally_blocked
    assert not result.subject_is_clear("portfolio-1")
    assert result.subject_is_clear("unaffected-subject")


def test_incomplete_global_listing_blocks_reopening() -> None:
    storage = FakeStorage(incomplete_intent_listing=True)
    with_runtime_head(storage)

    result = verify_completeness(storage)

    assert result.globally_blocked
    assert not result.can_reopen
    assert result.global_reasons[0].startswith("register inventory incomplete:")


def test_complete_linked_chains_allow_reopening() -> None:
    storage = FakeStorage()
    for subject, operation_id in (("portfolio-1", "reset-1"), (RUNTIME_SUBJECT, "runtime-1")):
        record = intent(operation_id, subject=subject)
        persist_intent(storage, record)
        storage.heads[subject] = SubjectHead(subject, operation_id, 1, 1)

    result = verify_completeness(storage)

    assert result.can_reopen
    assert result.subject_is_clear("portfolio-1")


def test_builder_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="explicit UTC"):
        intent("naive", created_at=datetime(2026, 9, 26, 12, 0))
