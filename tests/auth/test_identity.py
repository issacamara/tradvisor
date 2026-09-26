from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, cast

import pytest

from backend.auth.identity import (
    AdmissionRepository,
    AuthenticationError,
    FirebaseIdTokenVerifier,
    FirestoreAdmissionRepository,
    RegisterAdmissionDenyFence,
    authenticate_request,
)
from backend.recovery.register import Intent, StorageAdapter


class AdmissionFixture:
    def __init__(self, admitted: bool = True, failure: bool = False, email: str = "a@example.com") -> None:
        self.admitted = admitted
        self.failure = failure
        self.email = email
        self.calls: list[tuple[str, str]] = []

    async def is_admitted(self, uid: str, email: str) -> bool:
        self.calls.append((uid, email))
        if self.failure:
            raise RuntimeError("private store error")
        return self.admitted and email.casefold() == self.email.casefold()


def verifier_for(claims: Mapping[str, Any]) -> FirebaseIdTokenVerifier:
    def verify(token: str, *, check_revoked: bool) -> Mapping[str, Any]:
        assert token == "fixture-token"
        assert check_revoked is True
        return claims

    return FirebaseIdTokenVerifier(verify)


def test_verified_identity_is_taken_from_revocation_checked_token() -> None:
    repository = AdmissionFixture(email="a@example.com")
    identity = asyncio.run(authenticate_request(
        "Bearer fixture-token",
        verifier_for({"uid": "verified-uid", "email": "a@example.com", "email_verified": True}),
        repository,
    ))
    assert identity.uid == "verified-uid"
    assert repository.calls == [("verified-uid", "a@example.com")]


def test_missing_and_unverified_identity_are_rejected_before_admission() -> None:
    repository = AdmissionFixture()
    with pytest.raises(AuthenticationError) as missing:
        asyncio.run(authenticate_request("", verifier_for({}), repository))
    assert (missing.value.status_code, missing.value.code) == (401, "unauthenticated")
    with pytest.raises(AuthenticationError) as unverified:
        asyncio.run(authenticate_request(
            "Bearer fixture-token",
            verifier_for({"uid": "user-1", "email": "a@example.com", "email_verified": False}),
            repository,
        ))
    assert (unverified.value.status_code, unverified.value.code) == (403, "email_unverified")
    assert repository.calls == []


def test_revoked_or_invalid_firebase_token_fails_closed_before_admission() -> None:
    repository = AdmissionFixture()

    def rejected_token(_token: str, *, check_revoked: bool) -> Mapping[str, Any]:
        assert check_revoked is True
        raise RuntimeError("revoked token provider detail")

    with pytest.raises(AuthenticationError) as denied:
        asyncio.run(
            authenticate_request(
                "Bearer fixture-token",
                FirebaseIdTokenVerifier(rejected_token),
                repository,
            )
        )

    assert (denied.value.status_code, denied.value.code) == (401, "unauthenticated")
    assert repository.calls == []
    assert "revoked token provider detail" not in str(denied.value)


def test_current_admission_is_checked_again_on_every_request() -> None:
    repository = AdmissionFixture()
    verifier = verifier_for({"uid": "user-1", "email": "a@example.com", "email_verified": True})
    asyncio.run(authenticate_request("Bearer fixture-token", verifier, repository))
    repository.admitted = False
    with pytest.raises(AuthenticationError, match="admission_denied"):
        asyncio.run(authenticate_request("Bearer fixture-token", verifier, repository))
    assert len(repository.calls) == 2


def test_email_change_does_not_transfer_uid_admission() -> None:
    repository = AdmissionFixture(email="a@example.com")
    verifier = verifier_for({"uid": "user-1", "email": "new@example.com", "email_verified": True})
    with pytest.raises(AuthenticationError) as denied:
        asyncio.run(authenticate_request("Bearer fixture-token", verifier, repository))
    assert denied.value.code == "admission_denied"
    assert repository.calls == [("user-1", "new@example.com")]


def test_membership_failure_fails_closed_and_hides_store_details() -> None:
    repository = AdmissionFixture(failure=True)
    verifier = verifier_for({"uid": "private-uid", "email": "private@example.com", "email_verified": True})
    with pytest.raises(AuthenticationError) as denied:
        asyncio.run(authenticate_request("Bearer fixture-token", verifier, repository))
    assert (denied.value.status_code, denied.value.code) == (503, "admission_unavailable")
    assert "private" not in str(denied.value)


def test_firestore_membership_matches_active_uid_and_normalized_email() -> None:
    class Snapshot:
        exists = True

        def to_dict(self) -> dict[str, object]:
            return {
                "active": True,
                "email": "a@example.com",
                "decision_operation_id": "grant-1",
                "decision_sequence": 1,
            }

    class Document:
        def get(self) -> Snapshot:
            return Snapshot()

    class Collection:
        def document(self, uid: str) -> Document:
            assert uid == "user-1"
            return Document()

    class EmptySnapshot:
        exists = False

        def to_dict(self) -> dict[str, object]:
            return {}

    class EmptyDocument:
        def get(self) -> EmptySnapshot:
            return EmptySnapshot()

    class EmptyCollection:
        def document(self, uid: str) -> EmptyDocument:
            assert uid == "user-1"
            return EmptyDocument()

    class Client:
        def collection(self, name: str) -> Collection:
            if name == "application_admissions":
                return Collection()
            assert name == "application_admission_denials"
            return EmptyCollection()  # type: ignore[return-value]

    repository: AdmissionRepository = FirestoreAdmissionRepository(Client())
    assert asyncio.run(repository.is_admitted("user-1", "A@example.com"))
    assert not asyncio.run(repository.is_admitted("user-1", "other@example.com"))


def test_restored_old_allowlist_is_rejected_by_durable_deny_fence() -> None:
    class Snapshot:
        exists = True

        def __init__(self, record: dict[str, object]) -> None:
            self.record = record

        def to_dict(self) -> dict[str, object]:
            return self.record

    class Document:
        def __init__(self, snapshot: Snapshot) -> None:
            self.snapshot = snapshot

        def get(self) -> Snapshot:
            return self.snapshot

    class Collection:
        def __init__(self, snapshot: Snapshot) -> None:
            self.snapshot = snapshot

        def document(self, uid: str) -> Document:
            return Document(self.snapshot)

    class Client:
        def collection(self, name: str) -> Collection:
            if name == "application_admissions":
                return Collection(Snapshot({
                    "active": True,
                    "email": "a@example.com",
                    "decision_operation_id": "old-grant",
                    "decision_sequence": 1,
                }))
            assert name == "application_admission_denials"
            return Collection(Snapshot({"decision_sequence": 2}))

    repository: AdmissionRepository = FirestoreAdmissionRepository(Client())
    assert not asyncio.run(repository.is_admitted("user-1", "A@example.com"))


def test_register_head_deny_fence_rejects_restored_allowlist() -> None:
    from backend.recovery.register import InventoryPage, Intent, SubjectHead, build_intent

    class Register:
        def get_head(self, subject: str) -> SubjectHead:
            return SubjectHead(subject, "deny-2", 2, 2)

        def get_intent(self, operation_id: str) -> Intent:
            return build_intent(
                operation_id=operation_id,
                subject="user-1",
                action="deny",
                generation="g1",
                operator="operator-1",
                predecessor="grant-1",
                sequence=2,
                created_at=datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc),
            )

        def create_intent(self, intent: Intent) -> bool:
            raise AssertionError

        def compare_and_set_head(self, subject: str, expected_generation: int | None, operation_id: str, sequence: int) -> SubjectHead | None:
            raise AssertionError

        def list_intents(self, cursor: str | None, *, limit: int) -> InventoryPage:
            return InventoryPage((), None)

        def list_heads(self, cursor: str | None, *, limit: int) -> InventoryPage:
            return InventoryPage((), None)

    class Snapshot:
        exists = True

        def to_dict(self) -> dict[str, object]:
            return {"active": True, "email": "a@example.com", "decision_operation_id": "old-grant", "decision_sequence": 1}

    class Document:
        def get(self) -> Snapshot:
            return Snapshot()

    class Client:
        def collection(self, name: str) -> Any:
            return type("Collection", (), {"document": lambda self, uid: Document()})()

    repository: AdmissionRepository = FirestoreAdmissionRepository(
        Client(), RegisterAdmissionDenyFence(Register())
    )
    assert not asyncio.run(repository.is_admitted("user-1", "A@example.com"))


def test_pending_register_deny_fence_rejects_after_projection_interruption() -> None:
    from backend.recovery.register import InventoryPage, SubjectHead, build_intent

    pending = build_intent(
        operation_id="deny-2",
        subject="user-1",
        action="deny",
        generation="g1",
        operator="operator-1",
        predecessor="grant-1",
        sequence=1,
        created_at=datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc),
    )

    class Register:
        def get_head(self, subject: str) -> SubjectHead:
            return SubjectHead(subject, "grant-1", 1, 1)

        def get_intent(self, operation_id: str) -> Intent | None:
            return None

        def list_intents(self, cursor: str | None, *, limit: int) -> InventoryPage:
            return InventoryPage((pending,), None)

    fence = RegisterAdmissionDenyFence(cast(StorageAdapter, Register()))
    assert fence.is_denied("user-1")
