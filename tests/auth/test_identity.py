from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from backend.auth.identity import (
    AdmissionRepository,
    AuthenticationError,
    FirebaseIdTokenVerifier,
    FirestoreAdmissionRepository,
    authenticate_request,
)


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
            return {"active": True, "email": "a@example.com"}

    class Document:
        def get(self) -> Snapshot:
            return Snapshot()

    class Collection:
        def document(self, uid: str) -> Document:
            assert uid == "user-1"
            return Document()

    class Client:
        def collection(self, name: str) -> Collection:
            assert name == "application_admissions"
            return Collection()

    repository: AdmissionRepository = FirestoreAdmissionRepository(Client())
    assert asyncio.run(repository.is_admitted("user-1", "A@example.com"))
    assert not asyncio.run(repository.is_admitted("user-1", "other@example.com"))
