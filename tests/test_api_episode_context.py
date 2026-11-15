"""FastAPI read endpoints for stations / episodes / context."""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_list_stations():
    response = client.get("/stations")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert "station_id" in body[0]
    assert "latitude" in body[0]


def test_list_episodes():
    response = client.get("/episodes")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    ep = body[0]
    assert "onset_at" in ep
    assert "peak_aqi" in ep
    assert "severity" in ep
    assert "uncertainty" in ep


def test_list_episodes_filter_station():
    stations = client.get("/stations").json()
    sid = stations[0]["station_id"]
    response = client.get("/episodes", params={"station_id": sid})
    assert response.status_code == 200
    for ep in response.json():
        assert ep["station_id"] == sid


def test_latest_context():
    response = client.get("/context/latest")
    assert response.status_code == 200
    body = response.json()
    assert "upwind_fire_count_24h" in body
    assert "wind_speed_ms" in body
    assert "boundary_layer_height_m" in body
    assert "is_delhi_winter_season" in body
    assert 0.0 <= body["feature_completeness"] <= 1.0


def test_root_lists_new_routes():
    body = client.get("/").json()
    assert body["stations"] == "/stations"
    assert body["episodes"] == "/episodes"
    assert body["context_latest"] == "/context/latest"
