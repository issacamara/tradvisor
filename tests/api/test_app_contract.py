from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth.identity import VerifiedIdentity
from backend.openapi import StockChartData
from tests.auth.test_app_startup import AdmissionFixture, TokenVerifierFixture


class WorkloadFixture:
    def verify(self, token: str, *, audience: str) -> str:
        assert token == "worker-token"
        return "worker@example.iam.gserviceaccount.com"


def client() -> TestClient:
    verifier = TokenVerifierFixture(VerifiedIdentity(uid="user-1", email="investor@example.com", email_verified=True))
    return TestClient(create_app(verifier=verifier, admissions=AdmissionFixture(), workload_verifier=WorkloadFixture(), workload_audience="https://worker"))


def test_every_v1_route_requires_user_admission() -> None:
    response = client().get("/v1/swing/recommendations")
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


def test_empty_published_chart_falls_back_to_market_data(monkeypatch) -> None:
    application = client()
    empty_chart = StockChartData(
        symbol="AAA", **{"from": date(2026, 1, 1), "to": date(2026, 1, 2)},
        batch_id="published-batch", points=(),
    )
    market_chart = StockChartData(
        symbol="AAA", **{"from": date(2026, 1, 1), "to": date(2026, 1, 2)},
        batch_id="market-fallback:2026-01-02", points=(),
    )
    monkeypatch.setattr("backend.app.read_chart", lambda *args, **kwargs: empty_chart)
    monkeypatch.setattr("backend.app._market_chart_fallback", lambda **kwargs: market_chart)

    response = application.get(
        "/v1/stocks/AAA/chart",
        params={"from": "2026-01-01", "to": "2026-01-02"},
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["batch_id"] == "market-fallback:2026-01-02"


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


def test_generated_openapi_is_the_application_contract() -> None:
    paths = client().get("/openapi.json").json()["paths"]
    assert sum(len(methods) for methods in paths.values()) == 5
