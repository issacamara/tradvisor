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


def test_analysis_routes_return_typed_not_ready_without_a_complete_publication() -> None:
    application = client()
    headers = {"Authorization": "Bearer fixture-token"}
    requests = (
        ("/v1/swing/recommendations", {}),
        ("/v1/long-term/rankings", {"objective": "growth"}),
        ("/v1/stocks/AAA", {}),
        ("/v1/stocks/AAA/chart", {"from": "2026-01-01", "to": "2026-01-02"}),
    )

    for path, params in requests:
        response = application.get(path, params=params, headers=headers)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "analysis_not_ready"


def test_analysis_routes_remain_protected() -> None:
    application = client()
    assert application.get("/v1/swing/recommendations").json()["error"]["code"] == "unauthenticated"
    assert application.get("/v1/long-term/rankings", params={"objective": "growth"}).json()["error"]["code"] == "unauthenticated"
    assert application.get("/v1/stocks/AAA").json()["error"]["code"] == "unauthenticated"
    assert application.get("/v1/stocks/AAA/chart", params={"from": "2026-01-01", "to": "2026-01-02"}).json()["error"]["code"] == "unauthenticated"


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
