"""Firebase token verification and fail-closed current invitation admission."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hmac
from typing import Any, Protocol, cast

from backend.recovery.register import Intent, StorageAdapter

class AuthenticationError(Exception):
    """A request cannot be authenticated or currently admitted."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    uid: str
    email: str
    email_verified: bool


@dataclass(frozen=True, slots=True)
class AdmittedIdentity:
    uid: str
    email: str


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> VerifiedIdentity: ...


class AdmissionRepository(Protocol):
    async def is_admitted(self, uid: str, email: str) -> bool: ...


class AdmissionDenyFence(Protocol):
    def is_denied(self, uid: str) -> bool: ...


class RegisterAdmissionDenyFence:
    """Read the immutable register head as the restore-resistant deny source."""

    def __init__(self, register: StorageAdapter) -> None:
        self._register = register

    def is_denied(self, uid: str) -> bool:
        head = self._register.get_head(uid)
        head_sequence = head.sequence if head is not None else 0
        if head is not None:
            intent = self._register.get_intent(head.operation_id)
            if intent is not None and intent.subject == uid and intent.action == "deny":
                return True
        cursor: str | None = None
        while True:
            page = self._register.list_intents(cursor, limit=100)
            if any(
                isinstance(intent, Intent)
                and intent.subject == uid
                and intent.action == "deny"
                and intent.sequence >= head_sequence
                for intent in page.items
            ):
                return True
            if page.next_cursor is None:
                return False
            cursor = page.next_cursor


def normalize_email(value: str) -> str:
    return value.strip().casefold()


class FirebaseIdTokenVerifier:
    """Verify signed Firebase ID tokens and check revocation with Admin SDK."""

    def __init__(self, verify_token: Callable[..., Mapping[str, Any]] | None = None) -> None:
        self._verify_token = verify_token

    async def verify(self, token: str) -> VerifiedIdentity:
        try:
            claims = await asyncio.to_thread(self._verify, token)
            uid, email, verified = claims.get("uid"), claims.get("email"), claims.get("email_verified")
            if not isinstance(uid, str) or not uid or not isinstance(email, str) or not email:
                raise AuthenticationError("unauthenticated", 401)
            if verified is not True:
                raise AuthenticationError("email_unverified", 403)
            return VerifiedIdentity(uid=uid, email=email, email_verified=True)
        except AuthenticationError:
            raise
        except Exception as error:
            raise AuthenticationError("unauthenticated", 401) from error

    def _verify(self, token: str) -> Mapping[str, Any]:
        if self._verify_token is not None:
            return self._verify_token(token, check_revoked=True)
        import firebase_admin  # type: ignore[import-untyped]
        from firebase_admin import auth

        try:
            app = firebase_admin.get_app()
        except ValueError:
            app = firebase_admin.initialize_app()
        return cast(Mapping[str, Any], auth.verify_id_token(token, app=app, check_revoked=True))


class FirestoreAdmissionRepository:
    """Read the administrator-owned admission record on every protected request."""

    def __init__(self, client: Any | None = None, deny_fence: AdmissionDenyFence | None = None) -> None:
        if client is None:
            from google.cloud import firestore

            client = firestore.Client()
        self._client = client
        self._deny_fence = deny_fence

    async def is_admitted(self, uid: str, email: str) -> bool:
        if self._deny_fence is not None and await asyncio.to_thread(self._deny_fence.is_denied, uid):
            return False
        snapshot, deny_fence = await asyncio.gather(
            asyncio.to_thread(self._client.collection("application_admissions").document(uid).get),
            asyncio.to_thread(self._client.collection("application_admission_denials").document(uid).get),
        )
        if not snapshot.exists or not deny_fence.exists:
            fence_sequence = 0
        else:
            fence_record = deny_fence.to_dict()
            fence_sequence = (
                int(fence_record["decision_sequence"])
                if isinstance(fence_record, dict) and isinstance(fence_record.get("decision_sequence"), int)
                else 0
            )
        if not snapshot.exists:
            return False
        record = snapshot.to_dict()
        return bool(
            isinstance(record, dict)
            and record.get("active") is True
            and isinstance(record.get("email"), str)
            and isinstance(record.get("decision_operation_id"), str)
            and isinstance(record.get("decision_sequence"), int)
            and record.get("decision_sequence", 0) >= 1
            and record.get("decision_sequence", 0) > fence_sequence
            and hmac.compare_digest(normalize_email(record["email"]), normalize_email(email))
        )


async def authenticate_request(
    authorization: str,
    verifier: TokenVerifier,
    admissions: AdmissionRepository,
) -> AdmittedIdentity:
    """Verify one protected request and re-read live admission every time."""
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        raise AuthenticationError("unauthenticated", 401)
    try:
        identity = await verifier.verify(token)
    except AuthenticationError:
        raise
    except Exception as error:
        raise AuthenticationError("unauthenticated", 401) from error
    if not identity.email_verified:
        raise AuthenticationError("email_unverified", 403)
    try:
        admitted = await admissions.is_admitted(identity.uid, identity.email)
    except Exception as error:
        raise AuthenticationError("admission_unavailable", 503) from error
    if not admitted:
        raise AuthenticationError("admission_denied", 403)
    return AdmittedIdentity(uid=identity.uid, email=identity.email)


async def current_admission_check(uid: str, email: str, repository: AdmissionRepository) -> bool:
    """Reusable request/replay guard; repository errors always deny access."""
    try:
        return await repository.is_admitted(uid, email)
    except Exception:
        return False
