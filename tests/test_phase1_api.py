import re

from fastapi.testclient import TestClient

from floodsim.api.app import app


def test_health_returns_typed_phase1_response() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "api_version": "v1",
        "application_version": "0.1.16",
        "engine": {"required": "SFINCS 2.4.0 Galibier"},
    }


def test_app_config_defaults_to_local_mode(monkeypatch) -> None:
    monkeypatch.delenv("FLOODSIM_APP_MODE", raising=False)
    monkeypatch.delenv("FLOODSIM_DEMO_RESULTS_DIR", raising=False)
    response = TestClient(app).get("/api/v1/app-config")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "local",
        "allow_run": True,
        "allow_result_import": True,
        "download_url": (
            "https://github.com/nobunora/urban-pluvial-flood-simulator/releases/latest"
        ),
        "demo_result_event_ids": [],
    }


def test_app_config_demo_mode_exposes_only_existing_allowlisted_results(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "2025-yokkaichi.zip").write_bytes(b"placeholder")
    (tmp_path / "not-allowlisted.zip").write_bytes(b"placeholder")
    monkeypatch.setenv("FLOODSIM_APP_MODE", "demo")
    monkeypatch.setenv("FLOODSIM_DEMO_RESULTS_DIR", str(tmp_path))

    response = TestClient(app).get("/api/v1/app-config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "demo"
    assert payload["allow_run"] is False
    assert payload["allow_result_import"] is False
    assert payload["demo_result_event_ids"] == ["2025-yokkaichi"]


def test_built_placeholder_spa_is_served() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Urban Pluvial Flood Simulator" in response.text
    asset_path = re.search(r'<script type="module" crossorigin src="([^"]+)"', response.text)
    assert asset_path is not None
    asset_response = TestClient(app).get(asset_path.group(1))
    assert asset_response.status_code == 200
    assert asset_response.headers["content-type"].startswith(
        ("text/javascript", "application/javascript")
    )
    assert len(asset_response.content) > 1_000


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
