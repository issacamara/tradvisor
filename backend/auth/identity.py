"""Firebase token verification and fail-closed current invitation admission."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hmac
from typing import Any, Protocol, cast

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

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            from google.cloud import firestore

            client = firestore.Client()
        self._client = client

    async def is_admitted(self, uid: str, email: str) -> bool:
        snapshot = await asyncio.to_thread(
            self._client.collection("application_admissions").document(uid).get
        )
        if not snapshot.exists:
            return False
        record = snapshot.to_dict()
        return bool(
            isinstance(record, dict)
            and record.get("active") is True
            and isinstance(record.get("email"), str)
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
