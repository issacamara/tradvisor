from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from httpx import Response as HttpxResponse

from backend.auth.identity import AuthenticationError, VerifiedIdentity
from backend.contracts.envelopes import ErrorEnvelope, ResponseEnvelope
from backend.contracts.routes import MeResource
from backend.main import app, create_app

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
class TokenVerifierFixture:
    def __init__(self, identity: VerifiedIdentity) -> None:
        self.identity = identity
        self.errors: dict[str, Exception] = {}
        self.calls: list[str] = []

    async def verify(self, token: str) -> VerifiedIdentity:
        self.calls.append(token)
        error = self.errors.get(token)
        if error is not None:
            raise error
        return self.identity


class AdmissionFixture:
    def __init__(self) -> None:
        self.admitted = True
        self.failure = False
        self.expected_email = "investor@example.com"
        self.calls: list[tuple[str, str]] = []

    async def is_admitted(self, uid: str, email: str) -> bool:
        self.calls.append((uid, email))
        if self.failure:
            raise RuntimeError("private admission failure")
        return self.admitted and email.casefold() == self.expected_email.casefold()


def api_client() -> tuple[TestClient, TokenVerifierFixture, AdmissionFixture]:
    verifier = TokenVerifierFixture(
        VerifiedIdentity(
            uid="verified-user",
            email="investor@example.com",
            email_verified=True,
        )
    )
    admissions = AdmissionFixture()
    application = create_app(
        verifier=verifier,
        admissions=admissions,
        clock=lambda: NOW,
        request_id_factory=lambda: "request-123",
    )
    return TestClient(application), verifier, admissions


def assert_contract_error(response: HttpxResponse, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"
    parsed = ErrorEnvelope.model_validate(response.json())
    assert parsed.error.code == code
    assert parsed.error.request_id == "request-123"


def test_api_entrypoint_starts_and_serves_healthcheck() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_me_denies_a_request_without_a_bearer_token_before_live_reads() -> None:
    client, verifier, admissions = api_client()

    response = client.get("/v1/me")

    assert_contract_error(response, 401, "unauthenticated")
    assert verifier.calls == []
    assert admissions.calls == []


@pytest.mark.parametrize(
    ("token", "error"),
    [
        ("invalid-token", AuthenticationError("unauthenticated", 401)),
        ("revoked-token", RuntimeError("revoked token details")),
    ],
)
def test_me_denies_invalid_and_revoked_tokens(
    token: str,
    error: Exception,
) -> None:
    client, verifier, admissions = api_client()
    verifier.errors[token] = error

    response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert_contract_error(response, 401, "unauthenticated")
    assert admissions.calls == []
    assert "revoked token details" not in response.text


def test_me_denies_unverified_identity_with_the_frozen_public_code() -> None:
    client, verifier, admissions = api_client()
    verifier.identity = VerifiedIdentity(
        uid="verified-user",
        email="investor@example.com",
        email_verified=False,
    )

    response = client.get("/v1/me", headers={"Authorization": "Bearer fixture-token"})

    assert_contract_error(response, 403, "email_unverified")
    assert admissions.calls == []


def test_me_does_not_require_live_admission() -> None:
    client, _, admissions = api_client()
    headers = {"Authorization": "Bearer fixture-token"}

    admitted = client.get("/v1/me", headers=headers)
    assert admitted.status_code == 200
    admissions.admitted = False
    still_admitted = client.get("/v1/me", headers=headers)
    assert still_admitted.status_code == 200
    assert admissions.calls == []


def test_me_ignores_admission_repository_failures() -> None:
    client, _, admissions = api_client()
    admissions.failure = True

    response = client.get(
        "/v1/me",
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert response.status_code == 200
    assert "private admission failure" not in response.text


def test_me_uses_token_identity_and_returns_the_frozen_response_envelope() -> None:
    client, _, admissions = api_client()

    response = client.get(
        "/v1/me",
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    parsed = ResponseEnvelope[MeResource].model_validate_json(response.text)
    assert parsed.model_dump(mode="json") == {
        "data": {
            "uid": "verified-user",
            "email": "investor@example.com",
        },
        "meta": {
            "request_id": "request-123",
            "server_time": "2026-09-26T12:00:00Z",
            "schema_version": 1,
            "recovery_id": None,
        },
    }
    assert admissions.calls == []



def test_me_ignores_caller_selected_ownership_and_uses_verified_uid() -> None:
    client, _, _ = api_client()

    response = client.get(
        "/v1/me?uid=other-user",
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["uid"] == "verified-user"
