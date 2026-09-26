from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from backend.admin.admission import (
    AdmissionDecision,
    AdmissionDecisionError,
    AdmissionRecord,
    apply_admission_decision,
)
from backend.recovery.register import (
    Action,
    Intent,
    InventoryPage,
    RUNTIME_SUBJECT,
    SubjectHead,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


@dataclass
class Store:
    intents: dict[str, Intent] = field(default_factory=dict)
    heads: dict[str, SubjectHead] = field(default_factory=dict)
    admissions: dict[str, AdmissionRecord] = field(default_factory=dict)
    operation_emails: dict[str, str] = field(default_factory=dict)
    incomplete: bool = False
    race: AdmissionRecord | None = None

    def get_intent(self, operation_id: str) -> Intent | None:
        return self.intents.get(operation_id)

    def create_intent(self, intent: Intent) -> bool:
        if intent.operation_id in self.intents:
            return False
        self.intents[intent.operation_id] = intent
        return True

    def get_head(self, subject: str) -> SubjectHead | None:
        return self.heads.get(subject)

    def compare_and_set_head(self, subject: str, expected_generation: int | None, operation_id: str, sequence: int) -> SubjectHead | None:
        current = self.heads.get(subject)
        actual = None if current is None else current.storage_generation
        if actual != expected_generation:
            return None
        head = SubjectHead(subject, operation_id, sequence, (actual or 0) + 1)
        self.heads[subject] = head
        return head

    def list_intents(self, cursor: str | None, *, limit: int) -> InventoryPage:
        return InventoryPage(tuple(self.intents.values()), None, complete=not self.incomplete)

    def list_heads(self, cursor: str | None, *, limit: int) -> InventoryPage:
        return InventoryPage(tuple(self.heads.values()), None)

    def get_admission(self, subject: str) -> AdmissionRecord | None:
        return self.admissions.get(subject)

    def get_operation_email(self, operation_id: str) -> str | None:
        return self.operation_emails.get(operation_id)

    def create_operation_email(self, operation_id: str, email: str) -> bool:
        if operation_id in self.operation_emails:
            return False
        self.operation_emails[operation_id] = email
        return True

    def compare_and_set_admission(self, subject: str, expected_decision_sequence: int | None, record: AdmissionRecord) -> AdmissionRecord | None:
        if self.race is not None:
            self.admissions[subject] = self.race
            self.race = None
        current = self.admissions.get(subject)
        actual = None if current is None else current.decision_sequence
        if actual != expected_decision_sequence:
            return None
        self.admissions[subject] = record
        return record


def decision(operation_id: str, action: Action, *, predecessor: str | None = None, sequence: int = 1) -> AdmissionDecision:
    return AdmissionDecision(
        operation_id=operation_id,
        subject="user-1",
        email="Investor@Example.com",
        action=action,
        generation="generation-1",
        operator="operator-1",
        predecessor=predecessor,
        sequence=sequence,
        created_at=NOW,
    )


def with_runtime_root(store: Store) -> None:
    from backend.recovery.register import build_intent

    root = build_intent(
        operation_id="runtime-root",
        subject=RUNTIME_SUBJECT,
        action="recovery",
        generation="generation-1",
        operator="operator-1",
        predecessor=None,
        sequence=1,
        created_at=NOW,
    )
    store.intents[root.operation_id] = root
    store.heads[RUNTIME_SUBJECT] = SubjectHead(RUNTIME_SUBJECT, root.operation_id, 1, 1)


def test_deny_publishes_live_protection_and_retry_reuses_projection() -> None:
    store = Store()
    with_runtime_root(store)
    first = apply_admission_decision(store, decision("deny-1", "deny"))
    retry = apply_admission_decision(store, decision("deny-1", "deny"))

    assert first.active is False
    assert first.email == "investor@example.com"
    assert retry == first


def test_stale_grant_cannot_supersede_newer_deny() -> None:
    store = Store()
    with_runtime_root(store)
    denied = apply_admission_decision(store, decision("deny-1", "deny"))
    with pytest.raises(AdmissionDecisionError, match="stale"):
        apply_admission_decision(store, decision("grant-stale", "grant"))
    assert store.admissions["user-1"] == denied


def test_incomplete_inventory_blocks_grant_but_allows_deny() -> None:
    store = Store(incomplete=True)
    with_runtime_root(store)
    with pytest.raises(AdmissionDecisionError, match="complete"):
        apply_admission_decision(store, decision("grant-1", "grant"))
    denied = apply_admission_decision(store, decision("deny-1", "deny"))
    assert denied.active is False


def test_projection_race_never_turns_into_an_allow() -> None:
    store = Store()
    with_runtime_root(store)
    store.race = AdmissionRecord("user-1", "other@example.com", False, "deny-newer", 2, NOW)
    with pytest.raises(AdmissionDecisionError, match="projection changed"):
        apply_admission_decision(store, decision("grant-1", "grant"))
    assert store.admissions["user-1"].active is False


def test_old_allowlist_projection_cannot_restore_access_after_deny() -> None:
    store = Store()
    with_runtime_root(store)
    denied = apply_admission_decision(store, decision("deny-1", "deny"))
    stale_allow = AdmissionRecord("user-1", "investor@example.com", True, "old-grant", 1, NOW)

    assert store.compare_and_set_admission("user-1", None, stale_allow) is None
    assert store.admissions["user-1"] == denied


def test_reusing_operation_id_with_changed_payload_is_rejected() -> None:
    store = Store()
    with_runtime_root(store)
    apply_admission_decision(store, decision("deny-1", "deny"))
    changed = decision("deny-1", "deny", predecessor="deny-1", sequence=2)

    with pytest.raises(AdmissionDecisionError, match="immutable payload"):
        apply_admission_decision(store, changed)


def test_reusing_operation_id_with_changed_email_is_rejected() -> None:
    store = Store()
    with_runtime_root(store)
    apply_admission_decision(store, decision("deny-1", "deny"))
    changed = decision("deny-1", "deny")
    changed = AdmissionDecision(
        operation_id=changed.operation_id,
        subject=changed.subject,
        email="other@example.com",
        action=changed.action,
        generation=changed.generation,
        operator=changed.operator,
        predecessor=changed.predecessor,
        sequence=changed.sequence,
        created_at=changed.created_at,
    )

    with pytest.raises(AdmissionDecisionError, match="email"):
        apply_admission_decision(store, changed)
