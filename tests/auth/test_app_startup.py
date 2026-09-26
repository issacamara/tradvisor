from fastapi.testclient import TestClient

from backend.main import app


def test_api_entrypoint_starts_and_serves_healthcheck() -> None:
    response = TestClient(app).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
