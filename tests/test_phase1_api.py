import re

from fastapi.testclient import TestClient

from floodsim.api.app import app


def test_health_returns_typed_phase1_response() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "api_version": "v1",
        "application_version": "0.1.0",
        "engine": {"required": "SFINCS 2.4.0 Galibier"},
    }


def test_built_placeholder_spa_is_served() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Urban Pluvial Flood Simulator" in response.text
    asset_path = re.search(r'<script type="module" crossorigin src="([^"]+)"', response.text)
    assert asset_path is not None
    asset_response = TestClient(app).get(asset_path.group(1))
    assert asset_response.status_code == 200
    assert "Application skeleton is running." in asset_response.text


def test_phase2_endpoints_are_not_fake() -> None:
    openapi = app.openapi()
    required_phase2_paths = {
        "/api/v1/geocode",
        "/api/v1/health",
        "/api/v1/rainfall/events/{event_id}",
        "/api/v1/rainfall/stations",
        "/api/v1/rainfall/stations/{station_id}/extremes",
    }
    assert required_phase2_paths <= set(openapi["paths"])
