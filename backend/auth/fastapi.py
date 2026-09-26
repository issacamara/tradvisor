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
            raise HTTPException(status_code=error.status_code, detail=code, headers=headers) from error
        request.state.owner_uid = identity.uid
        return identity

    return require
