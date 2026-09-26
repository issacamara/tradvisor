from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from httpx import Response as HttpxResponse

from backend.auth.current_user import CurrentUserState, CurrentUserUnavailable
from backend.auth.identity import AuthenticationError, VerifiedIdentity
from backend.contracts.envelopes import ErrorEnvelope, ResponseEnvelope
from backend.contracts.paper import PaperPreferences
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


class CurrentUserFixture:
    def __init__(self) -> None:
        self.failure = False
        self.calls: list[str] = []
        self.state = CurrentUserState(
            preferences=PaperPreferences(
                objective="growth",
                fee_rate_pct="0.500000",
                preference_version=3,
                updated_at=NOW,
            ),
            portfolio_setup_state="configured",
            recovery_id="recovery-1",
        )

    async def get_current_user(self, owner_uid: str) -> CurrentUserState:
        self.calls.append(owner_uid)
        if self.failure:
            raise CurrentUserUnavailable("private profile failure")
        return self.state


def api_client() -> tuple[TestClient, TokenVerifierFixture, AdmissionFixture, CurrentUserFixture]:
    verifier = TokenVerifierFixture(
        VerifiedIdentity(
            uid="verified-user",
            email="investor@example.com",
            email_verified=True,
        )
    )
    admissions = AdmissionFixture()
    current_users = CurrentUserFixture()
    application = create_app(
        verifier=verifier,
        admissions=admissions,
        current_users=current_users,
        clock=lambda: NOW,
        request_id_factory=lambda: "request-123",
    )
    return TestClient(application), verifier, admissions, current_users


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
    client, verifier, admissions, current_users = api_client()

    response = client.get("/v1/me")

    assert_contract_error(response, 401, "unauthenticated")
    assert verifier.calls == []
    assert admissions.calls == []
    assert current_users.calls == []


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
    client, verifier, admissions, current_users = api_client()
    verifier.errors[token] = error

    response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert_contract_error(response, 401, "unauthenticated")
    assert admissions.calls == []
    assert current_users.calls == []
    assert "revoked token details" not in response.text


def test_me_denies_unverified_identity_with_the_frozen_public_code() -> None:
    client, verifier, admissions, current_users = api_client()
    verifier.identity = VerifiedIdentity(
        uid="verified-user",
        email="investor@example.com",
        email_verified=False,
    )

    response = client.get("/v1/me", headers={"Authorization": "Bearer fixture-token"})

    assert_contract_error(response, 403, "admission_denied")
    assert admissions.calls == []
    assert current_users.calls == []


def test_me_rechecks_live_admission_and_denies_removed_identity() -> None:
    client, _, admissions, current_users = api_client()
    headers = {"Authorization": "Bearer fixture-token"}

    admitted = client.get("/v1/me", headers=headers)
    admissions.admitted = False
    removed = client.get("/v1/me", headers=headers)

    assert admitted.status_code == 200
    assert_contract_error(removed, 403, "admission_denied")
    assert len(admissions.calls) == 2
    assert current_users.calls == ["verified-user"]


def test_me_fails_closed_when_admission_is_unavailable() -> None:
    client, _, admissions, current_users = api_client()
    admissions.failure = True

    response = client.get(
        "/v1/me",
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert_contract_error(response, 503, "admission_unavailable")
    assert current_users.calls == []
    assert "private admission failure" not in response.text


def test_me_uses_token_identity_and_returns_the_frozen_response_envelope() -> None:
    client, _, admissions, current_users = api_client()

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
            "preferences": {
                "objective": "growth",
                "fee_rate_pct": "0.5",
                "preference_version": 3,
                "updated_at": "2026-09-26T12:00:00Z",
            },
            "portfolio_setup_state": "configured",
            "starting_cash_min_xof": 100_000,
            "starting_cash_default_xof": 1_000_000,
            "starting_cash_max_xof": 100_000_000,
        },
        "meta": {
            "request_id": "request-123",
            "server_time": "2026-09-26T12:00:00Z",
            "schema_version": 1,
            "recovery_id": "recovery-1",
        },
    }
    assert admissions.calls == [("verified-user", "investor@example.com")]
    assert current_users.calls == ["verified-user"]


def test_me_ignores_caller_selected_ownership_and_uses_verified_uid() -> None:
    client, _, _, current_users = api_client()

    response = client.get(
        "/v1/me?uid=other-user",
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["uid"] == "verified-user"
    assert current_users.calls == ["verified-user"]


def test_me_fails_closed_when_current_profile_state_is_unavailable() -> None:
    client, _, _, current_users = api_client()
    current_users.failure = True

    response = client.get(
        "/v1/me",
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert_contract_error(response, 503, "service_unavailable")
    assert "private profile failure" not in response.text
