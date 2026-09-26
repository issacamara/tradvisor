"""Fail-closed trusted admission decisions backed by the recovery register."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

from backend.recovery.register import (
    Action,
    RegisterError,
    StorageAdapter,
    build_intent,
    confirm_decision,
    persist_intent,
    verify_completeness,
)


class AdmissionError(RegisterError):
    """An admission decision cannot be safely applied."""


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    subject: str
    admitted: bool
    operation_id: str
    sequence: int


def apply_decision(
    adapter: StorageAdapter,
    *,
    operation_id: str,
    subject: str,
    action: str,
    operator: str,
    predecessor: str | None,
    sequence: int,
    created_at: datetime,
) -> AdmissionDecision:
    """Persist and confirm one serialized deny/grant decision."""
    if action not in {"deny", "grant"}:
        raise AdmissionError("admission action must be deny or grant")
    if action == "grant":
        reconciliation = verify_completeness(adapter)
        if not reconciliation.can_reopen or not reconciliation.subject_is_clear(subject):
            raise AdmissionError("admission inventory is incomplete or subject is blocked")
    intent = build_intent(
        operation_id=operation_id, subject=subject, action=cast(Action, action), generation=None,
        operator=operator, predecessor=predecessor, sequence=sequence, created_at=created_at,
    )
    stored = persist_intent(adapter, intent)
    head = confirm_decision(adapter, stored.operation_id)
    return AdmissionDecision(subject, action == "grant", head.operation_id, head.sequence)


def is_admitted(adapter: StorageAdapter, subject: str) -> bool:
    """Read the live head; any missing or malformed state denies access."""
    try:
        head = adapter.get_head(subject)
        if head is None:
            return False
        intent = adapter.get_intent(head.operation_id)
        return intent is not None and intent.subject == subject and intent.action == "grant"
    except Exception:
        return False
