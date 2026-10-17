"""Workload-identity authentication for internal worker entry points."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, cast

from fastapi import HTTPException, Request


class WorkloadTokenVerifier(Protocol):
    def verify(self, token: str, *, audience: str) -> str: ...


class GoogleWorkloadTokenVerifier:
    def verify(self, token: str, *, audience: str) -> str:
        from google.oauth2 import id_token
        from google.auth.transport import requests

        verifier = cast(Any, id_token.verify_oauth2_token)
        claims: dict[str, Any] = verifier(token, requests.Request(), audience=audience)
        subject = claims.get("email")
        if not isinstance(subject, str) or claims.get("email_verified") is not True:
            raise ValueError("workload token has no verified service identity")
        expected = os.environ.get("WORKER_SERVICE_ACCOUNT")
        if expected and subject != expected:
            raise ValueError("unexpected workload identity")
        return subject


def workload_identity_dependency(
    verifier: WorkloadTokenVerifier,
    *,
    audience: str | None = None,
) -> Callable[[Request], Awaitable[str]]:
    async def require(request: Request) -> str:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        selected_audience = audience or os.environ.get("WORKER_AUDIENCE", "")
        if scheme.lower() != "bearer" or not token or not selected_audience:
            raise HTTPException(status_code=401, detail="unauthenticated")
        try:
            subject = verifier.verify(token, audience=selected_audience)
        except Exception as error:
            raise HTTPException(status_code=403, detail="admission_denied") from error
        request.state.worker_subject = subject
        return subject

    return require


__all__ = ["GoogleWorkloadTokenVerifier", "WorkloadTokenVerifier", "workload_identity_dependency"]
