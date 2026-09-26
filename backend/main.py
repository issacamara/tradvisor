"""FastAPI application entry point for the packaged API runtime."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from functools import lru_cache
from typing import Final, cast
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from backend.auth.current_user import (
    CurrentUserRepository,
    CurrentUserState,
    CurrentUserUnavailable,
    FirestoreCurrentUserRepository,
)
from backend.auth.fastapi import admitted_identity_dependency
from backend.auth.identity import (
    AdmissionRepository,
    AdmittedIdentity,
    FirebaseIdTokenVerifier,
    FirestoreAdmissionRepository,
    RegisterAdmissionDenyFence,
    TokenVerifier,
)
from backend.recovery.register import GcsStorageAdapter
from backend.contracts.envelopes import ApiError, ErrorEnvelope, ResponseEnvelope, ResponseMeta
from backend.contracts.routes import MeResource
from backend.contracts.scalars import STARTING_CASH_MAX_XOF, STARTING_CASH_MIN_XOF

PRIVATE_NO_STORE: Final = "private, no-store"
STARTING_CASH_DEFAULT_XOF: Final = 1_000_000
_ERROR_MESSAGES: Final = {
    "unauthenticated": "Authentication is required.",
    "admission_denied": "Current invitation access is required.",
    "admission_unavailable": "Admission could not be verified.",
    "service_unavailable": "Current user state is unavailable.",
}


@lru_cache(maxsize=1)
def _firestore_client() -> object:
    from google.cloud import firestore

    return firestore.Client()


@lru_cache(maxsize=1)
def _production_register() -> GcsStorageAdapter:
    from google.cloud import storage  # type: ignore[attr-defined]

    client = storage.Client()
    if not client.project:
        raise RuntimeError("recovery register project is unavailable")
    bucket = client.bucket(f"{client.project}-v1-recovery-register")
    return GcsStorageAdapter(bucket)


@lru_cache(maxsize=1)
def _production_admissions() -> AdmissionRepository:
    register = _production_register()
    return FirestoreAdmissionRepository(
        _firestore_client(), deny_fence=RegisterAdmissionDenyFence(register)
    )


@lru_cache(maxsize=1)
def _production_current_users() -> CurrentUserRepository:
    return FirestoreCurrentUserRepository(_firestore_client())


class _LazyAdmissionRepository:
    async def is_admitted(self, uid: str, email: str) -> bool:
        return await _production_admissions().is_admitted(uid, email)


class _LazyCurrentUserRepository:
    async def get_current_user(self, owner_uid: str) -> CurrentUserState:
        return await _production_current_users().get_current_user(owner_uid)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _request_id() -> str:
    return uuid4().hex


def create_app(
    *,
    verifier: TokenVerifier | None = None,
    admissions: AdmissionRepository | None = None,
    current_users: CurrentUserRepository | None = None,
    clock: Callable[[], datetime] = _utc_now,
    request_id_factory: Callable[[], str] = _request_id,
) -> FastAPI:
    """Compose the API with injectable identity and owner-scoped repositories."""

    selected_verifier = verifier if verifier is not None else FirebaseIdTokenVerifier()
    selected_admissions = admissions if admissions is not None else _LazyAdmissionRepository()
    selected_current_users = (
        current_users if current_users is not None else _LazyCurrentUserRepository()
    )
    require_identity = admitted_identity_dependency(selected_verifier, selected_admissions)
    application = FastAPI(title="Tradvisor API", version="0.13.0")

    @application.middleware("http")
    async def protected_response_headers(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request.state.request_id = request_id_factory()
        response = await call_next(request)
        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = PRIVATE_NO_STORE
        return response

    async def contract_http_exception(request: Request, error: Exception) -> Response:
        if not isinstance(error, HTTPException):
            raise error
        code = error.detail if isinstance(error.detail, str) else ""
        if request.url.path.startswith("/v1/") and code in _ERROR_MESSAGES:
            request_id = cast(str, request.state.request_id)
            body = ErrorEnvelope(
                error=ApiError(
                    code=code,
                    message=_ERROR_MESSAGES[code],
                    retryable=error.status_code == 503,
                    request_id=request_id,
                )
            )
            headers = dict(error.headers or {})
            headers["Cache-Control"] = PRIVATE_NO_STORE
            return JSONResponse(
                status_code=error.status_code,
                content=body.model_dump(mode="json"),
                headers=headers,
            )
        return await http_exception_handler(request, error)

    application.add_exception_handler(HTTPException, contract_http_exception)

    @application.get("/healthz", include_in_schema=False)
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/v1/me", response_model=ResponseEnvelope[MeResource])
    async def get_me(
        request: Request,
        identity: AdmittedIdentity = Depends(require_identity),
    ) -> ResponseEnvelope[MeResource]:
        try:
            state = await selected_current_users.get_current_user(identity.uid)
        except CurrentUserUnavailable as error:
            raise HTTPException(status_code=503, detail="service_unavailable") from error
        except Exception as error:
            raise HTTPException(status_code=503, detail="service_unavailable") from error

        return ResponseEnvelope[MeResource](
            data=MeResource(
                uid=identity.uid,
                email=identity.email,
                preferences=state.preferences,
                portfolio_setup_state=state.portfolio_setup_state,
                starting_cash_min_xof=STARTING_CASH_MIN_XOF,
                starting_cash_default_xof=STARTING_CASH_DEFAULT_XOF,
                starting_cash_max_xof=STARTING_CASH_MAX_XOF,
            ),
            meta=ResponseMeta(
                request_id=cast(str, request.state.request_id),
                server_time=clock(),
                schema_version=1,
                recovery_id=state.recovery_id,
            ),
        )

    return application


app = create_app()
