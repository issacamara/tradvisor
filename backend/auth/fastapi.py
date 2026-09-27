"""FastAPI adapter for the framework-independent authentication boundary."""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request

from backend.auth.identity import (
    AdmissionRepository,
    AdmittedIdentity,
    AuthenticationError,
    TokenVerifier,
    authenticate_request,
)


def admitted_identity_dependency(
    verifier: TokenVerifier,
    admissions: AdmissionRepository,
) -> Callable[[Request], Awaitable[AdmittedIdentity]]:
    async def require(request: Request) -> AdmittedIdentity:
        try:
            identity = await authenticate_request(
                request.headers.get("authorization", ""), verifier, admissions
            )
        except AuthenticationError as error:
            headers = {"Cache-Control": "private, no-store"}
            code = error.code
            if code == "admission_unavailable":
                raise HTTPException(status_code=503, detail=code, headers=headers) from error
            public_code = "admission_denied" if code == "email_unverified" else code
            raise HTTPException(
                status_code=error.status_code,
                detail=public_code,
                headers=headers,
            ) from error
        request.state.owner_uid = identity.uid
        return identity

    return require


def verified_identity_dependency(verifier: TokenVerifier) -> Callable[[Request], Awaitable[AdmittedIdentity]]:
    """Require a valid bearer token whose Firebase email is verified."""
    async def require(request: Request) -> AdmittedIdentity:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.casefold() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="unauthenticated", headers={"Cache-Control": "private, no-store"})
        try:
            identity = await verifier.verify(token)
        except AuthenticationError as error:
            raise HTTPException(status_code=error.status_code, detail=error.code, headers={"Cache-Control": "private, no-store"}) from error
        except Exception as error:
            raise HTTPException(status_code=401, detail="unauthenticated", headers={"Cache-Control": "private, no-store"}) from error
        if not identity.email_verified:
            raise HTTPException(status_code=403, detail="email_unverified", headers={"Cache-Control": "private, no-store"})
        request.state.owner_uid = identity.uid
        return AdmittedIdentity(uid=identity.uid, email=identity.email)

    return require
