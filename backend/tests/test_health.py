import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pitchsense.api.routes.health import get_database_status


def test_health_ok_when_database_available(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_database_status] = lambda: True

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_returns_503_when_database_unavailable(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_database_status] = lambda: False

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}


@pytest.mark.integration
def test_health_against_real_database(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"] == "ok"
