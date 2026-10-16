from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.auth.identity import VerifiedIdentity
from backend.openapi import ChartPoint, StockChartData
from backend.read_api.analysis import AnalysisNotReady
from tests.auth.test_app_startup import AdmissionFixture, TokenVerifierFixture


class WorkloadFixture:
    def verify(self, token: str, *, audience: str) -> str:
        assert token == "worker-token"
        return "worker@example.iam.gserviceaccount.com"


def client() -> TestClient:
    verifier = TokenVerifierFixture(VerifiedIdentity(uid="user-1", email="investor@example.com", email_verified=True))
    return TestClient(create_app(verifier=verifier, admissions=AdmissionFixture(), workload_verifier=WorkloadFixture(), workload_audience="https://worker"))


def _block_bigquery(monkeypatch) -> list[object]:
    calls: list[object] = []

    class Client:
        def __init__(self, *args, **kwargs) -> None:
            calls.append((args, kwargs))

    monkeypatch.setattr("google.cloud.bigquery.Client", Client)
    return calls


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


def test_absent_chart_returns_typed_unavailability_without_bigquery(monkeypatch) -> None:
    application = client()
    bigquery_calls = _block_bigquery(monkeypatch)

    class Configuration:
        project_id = "test-project"
        market_data_table = "test-project.market.prices"

    def no_chart(*args, **kwargs):
        raise AnalysisNotReady

    monkeypatch.setattr("backend.app._api_configuration", lambda: Configuration())
    monkeypatch.setattr("backend.app.read_chart", no_chart)

    response = application.get(
        "/v1/stocks/AAA/chart",
        params={"from": "2026-01-01", "to": "2026-01-02"},
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "analysis_not_ready"
    assert bigquery_calls == []


def test_empty_published_chart_keeps_its_published_batch_without_bigquery(monkeypatch) -> None:
    application = client()
    bigquery_calls = _block_bigquery(monkeypatch)
    empty_chart = StockChartData(
        symbol="AAA", **{"from": date(2026, 1, 1), "to": date(2026, 1, 2)},
        batch_id="published-batch", points=(),
    )
    monkeypatch.setattr("backend.app.read_chart", lambda *args, **kwargs: empty_chart)

    response = application.get(
        "/v1/stocks/AAA/chart",
        params={"from": "2026-01-01", "to": "2026-01-02"},
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == empty_chart.model_dump(mode="json", by_alias=True)
    assert bigquery_calls == []


def test_previous_complete_chart_batch_is_returned_without_bigquery(monkeypatch) -> None:
    application = client()
    bigquery_calls = _block_bigquery(monkeypatch)
    previous_chart = StockChartData(
        symbol="AAA", **{"from": date(2026, 1, 1), "to": date(2026, 1, 2)},
        batch_id="previous-complete-batch", points=(),
    )
    monkeypatch.setattr("backend.app.read_chart", lambda *args, **kwargs: previous_chart)

    response = application.get(
        "/v1/stocks/AAA/chart",
        params={"from": "2026-01-01", "to": "2026-01-02"},
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["batch_id"] == "previous-complete-batch"
    assert bigquery_calls == []


def test_published_chart_points_are_returned_without_bigquery(monkeypatch) -> None:
    application = client()
    bigquery_calls = _block_bigquery(monkeypatch)
    chart = StockChartData(
        symbol="AAA", **{"from": date(2026, 1, 1), "to": date(2026, 1, 2)},
        batch_id="current-complete-batch",
        points=(ChartPoint.model_validate({
            "session_date": date(2026, 1, 2), "status": "traded",
            "open": None, "high": None, "low": None,
            "close": {"amount": "100", "currency": "XOF"},
            "last_traded_close": {"amount": "100", "currency": "XOF"},
            "analytical_carried_close": None, "volume": None,
            "indicators": {}, "source_evidence": (),
        }),),
    )
    monkeypatch.setattr("backend.app.read_chart", lambda *args, **kwargs: chart)

    response = application.get(
        "/v1/stocks/AAA/chart",
        params={"from": "2026-01-01", "to": "2026-01-02"},
        headers={"Authorization": "Bearer fixture-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == chart.model_dump(mode="json", by_alias=True)
    assert bigquery_calls == []


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
