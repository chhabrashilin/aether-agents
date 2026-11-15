"""Smoke tests for package and API scaffold."""

from aether_agents import __version__


def test_version():
    assert __version__ == "0.1.0"


def test_health_endpoint():
    from fastapi.testclient import TestClient

    from apps.api.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "aether-agents-api"
