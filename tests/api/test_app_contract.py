from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth.identity import VerifiedIdentity
from tests.auth.test_app_startup import AdmissionFixture, CurrentUserFixture, TokenVerifierFixture


class WorkloadFixture:
    def verify(self, token: str, *, audience: str) -> str:
        assert token == "worker-token"
        return "worker@example.iam.gserviceaccount.com"


def client() -> TestClient:
    verifier = TokenVerifierFixture(VerifiedIdentity(uid="user-1", email="investor@example.com", email_verified=True))
    return TestClient(create_app(verifier=verifier, admissions=AdmissionFixture(), current_users=CurrentUserFixture(), workload_verifier=WorkloadFixture(), workload_audience="https://worker"))


def test_every_v1_route_requires_user_admission() -> None:
    response = client().get("/v1/paper/portfolio")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_internal_dispatch_requires_workload_identity(monkeypatch) -> None:
    application = client()
    assert application.post("/internal/workflows/daily-wf/dispatch").status_code == 401
    assert application.post("/internal/workflows/daily-wf/dispatch", headers={"Authorization": "Bearer user-token"}).status_code == 403


def test_large_command_body_is_rejected_before_handler() -> None:
    response = client().post("/v1/paper/reset", content=b"x" * (16 * 1024 + 1), headers={"Content-Length": str(16 * 1024 + 1)})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "body_too_large"


def test_generated_openapi_is_the_application_contract() -> None:
    paths = client().get("/openapi.json").json()["paths"]
    assert sum(len(methods) for methods in paths.values()) == 13
    assert "/v1/paper/orders" in paths
    assert "/v1/me/preferences" in paths
