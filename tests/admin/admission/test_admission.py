from datetime import datetime, timezone

import pytest

from backend.admin.admission import AdmissionError, apply_decision, is_admitted
from backend.recovery.register import InventoryPage, Intent, SubjectHead, build_intent


class MemoryAdapter:
    def __init__(self) -> None:
        self.intents: dict[str, Intent] = {}
        self.heads: dict[str, SubjectHead] = {}

    def get_intent(self, operation_id: str):
        return self.intents.get(operation_id)

    def create_intent(self, intent: Intent) -> bool:
        if intent.operation_id in self.intents:
            return False
        self.intents[intent.operation_id] = intent
        return True

    def get_head(self, subject: str):
        return self.heads.get(subject)

    def compare_and_set_head(self, subject, expected_generation, operation_id, sequence):
        current = self.heads.get(subject)
        if (current is None and expected_generation is not None) or (
            current is not None and current.storage_generation != expected_generation
        ):
            return None
        head = SubjectHead(subject, operation_id, sequence, 1 if current is None else current.storage_generation + 1)
        self.heads[subject] = head
        return head

    def list_intents(self, cursor, *, limit):
        return InventoryPage(tuple(self.intents.values()), None)

    def list_heads(self, cursor, *, limit):
        return InventoryPage(tuple(self.heads.values()), None)


NOW = datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc)


def test_deny_is_live_and_retry_is_idempotent() -> None:
    adapter = MemoryAdapter()
    first = apply_decision(adapter, operation_id="deny-1", subject="user-1", action="deny", operator="admin", predecessor=None, sequence=1, created_at=NOW)
    retry = apply_decision(adapter, operation_id="deny-1", subject="user-1", action="deny", operator="admin", predecessor=None, sequence=1, created_at=NOW)
    assert first == retry
    assert not is_admitted(adapter, "user-1")


def test_grant_requires_complete_runtime_register() -> None:
    with pytest.raises(AdmissionError, match="incomplete"):
        apply_decision(MemoryAdapter(), operation_id="grant-1", subject="user-1", action="grant", operator="admin", predecessor=None, sequence=1, created_at=NOW)


def test_grant_cannot_supersede_deny_without_current_predecessor() -> None:
    adapter = MemoryAdapter()
    runtime = build_intent(operation_id="runtime", subject="runtime", action="recovery", generation=None, operator="system", predecessor=None, sequence=1, created_at=NOW)
    adapter.intents["runtime"] = runtime
    adapter.heads["runtime"] = SubjectHead("runtime", "runtime", 1, 1)
    apply_decision(adapter, operation_id="deny-1", subject="user-1", action="deny", operator="admin", predecessor=None, sequence=1, created_at=NOW)
    with pytest.raises(Exception):
        apply_decision(adapter, operation_id="grant-1", subject="user-1", action="grant", operator="admin", predecessor=None, sequence=1, created_at=NOW)
