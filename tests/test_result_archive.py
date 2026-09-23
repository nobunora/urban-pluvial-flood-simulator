from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
from fastapi.testclient import TestClient

from floodsim.api import routes_results, routes_runs
from floodsim.api.app import app
from floodsim.domain.geometry import AnalysisArea, GeoBounds, LonLat
from floodsim.domain.manifest import RunManifest
from floodsim.domain.rainfall import ConstantRainfall
from floodsim.domain.run_config import AccuracyMode, RunConfig
from floodsim.domain.run_state import RunState
from floodsim.orchestration.run_coordinator import RunCoordinator
from floodsim.results.archive import (
    EXPECTED_MEMBERS,
    NORMALIZED_ARRAYS,
    create_result_archive,
    import_result_archive,
)
from floodsim.storage.run_store import atomic_write_json


def _contract_files(root: Path) -> tuple[Path, Path, Path, Path]:
    area = AnalysisArea(
        mode="rectangle",
        bounds=GeoBounds(west_deg=139, south_deg=35, east_deg=139.001, north_deg=35.001),
        center=LonLat(lon_deg=139.0005, lat_deg=35.0005),
        width_m=2,
        height_m=2,
        area_m2=4,
    )
    config = RunConfig(
        analysis_area=area,
        requested_accuracy_mode=AccuracyMode.FULL_1M,
        rainfall=ConstantRainfall(intensity_mm_per_h=50, duration_minutes=60),
    )
    manifest = RunManifest(
        application_version="test",
        run_id=uuid4(),
        created_at_utc=datetime.now(timezone.utc),
        analysis_area=area,
        requested_accuracy_mode=AccuracyMode.FULL_1M,
        run_status=RunState.COMPLETE,
        output_files={"normalized_arrays": "normalized_full_1m.npz"},
    )
    config_path = root / "run_config.json"
    manifest_path = root / "manifest.json"
    metadata_path = root / "result_metadata.json"
    arrays_path = root / "normalized_full_1m.npz"
    atomic_write_json(config_path, config.model_dump(mode="json"))
    atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    atomic_write_json(metadata_path, {"schema_version": "1"})
    np.savez(
        arrays_path,
        depth_time_m=np.zeros((1, 2, 2), dtype=np.float32),
        max_depth_m=np.zeros((2, 2), dtype=np.float32),
        terrain_elevation_m=np.ones((2, 2), dtype=np.float32),
        active_mask=np.ones((2, 2), dtype=bool),
        time_values=np.asarray(["0"]),
        grid_resolution_m=np.float32(1),
    )
    return config_path, manifest_path, metadata_path, arrays_path


def test_result_archive_compresses_only_on_export_and_round_trips(tmp_path: Path) -> None:
    config_path, manifest_path, metadata_path, arrays_path = _contract_files(tmp_path)
    with zipfile.ZipFile(arrays_path) as normal_result:
        assert {item.compress_type for item in normal_result.infolist()} == {zipfile.ZIP_STORED}

    archive_path = tmp_path / "export.zip"
    create_result_archive(
        archive_path,
        config_path=config_path,
        manifest_path=manifest_path,
        metadata_path=metadata_path,
        arrays_path=arrays_path,
    )
    with zipfile.ZipFile(archive_path) as exported:
        assert set(exported.namelist()) == EXPECTED_MEMBERS
        arrays_member = exported.getinfo(NORMALIZED_ARRAYS)
        assert arrays_member.compress_type == zipfile.ZIP_DEFLATED

    destination = tmp_path / "imported"
    config, manifest, metadata = import_result_archive(archive_path, destination)
    assert config.analysis_area == manifest.analysis_area
    assert metadata == {"schema_version": "1"}
    assert (destination / "results" / NORMALIZED_ARRAYS).is_file()


def test_result_archive_http_import_and_export(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path, manifest_path, metadata_path, arrays_path = _contract_files(tmp_path)
    archive_path = tmp_path / "input.zip"
    create_result_archive(
        archive_path,
        config_path=config_path,
        manifest_path=manifest_path,
        metadata_path=metadata_path,
        arrays_path=arrays_path,
    )
    coordinator = RunCoordinator(runs_root=tmp_path / "runs")
    monkeypatch.setattr(routes_results, "coordinator", coordinator)
    monkeypatch.setattr(routes_runs, "coordinator", coordinator)
    client = TestClient(app)

    imported = client.post(
        "/api/v1/results/import",
        content=archive_path.read_bytes(),
        headers={"Content-Type": "application/zip"},
    )
    assert imported.status_code == 200
    run_id = imported.json()["run_id"]
    status = client.get(f"/api/v1/runs/{run_id}")
    assert status.status_code == 200
    assert status.json()["state"] == "COMPLETE"

    exported = client.get(f"/api/v1/runs/{run_id}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"
    exported_path = tmp_path / "round-trip.zip"
    exported_path.write_bytes(exported.content)
    with zipfile.ZipFile(exported_path) as round_trip:
        assert set(round_trip.namelist()) == EXPECTED_MEMBERS


def test_demo_result_endpoint_opens_only_allowlisted_archives(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path, manifest_path, metadata_path, arrays_path = _contract_files(tmp_path)
    demo_dir = tmp_path / "demo-results"
    demo_dir.mkdir()
    archive_path = demo_dir / "2025-yokkaichi.zip"
    create_result_archive(
        archive_path,
        config_path=config_path,
        manifest_path=manifest_path,
        metadata_path=metadata_path,
        arrays_path=arrays_path,
    )
    coordinator = RunCoordinator(runs_root=tmp_path / "runs")
    monkeypatch.setattr(routes_results, "coordinator", coordinator)
    monkeypatch.setattr(routes_runs, "coordinator", coordinator)
    monkeypatch.setenv("FLOODSIM_DEMO_RESULTS_DIR", str(demo_dir))
    routes_results._demo_result_runs.clear()
    client = TestClient(app)

    opened = client.post("/api/v1/demo-results/2025-yokkaichi/open")
    assert opened.status_code == 200
    assert client.get(f"/api/v1/runs/{opened.json()['run_id']}").status_code == 200
    missing = client.post("/api/v1/demo-results/not-allowlisted/open")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DEMO_RESULT_NOT_FOUND"


def test_demo_mode_rejects_arbitrary_archive_upload(monkeypatch) -> None:
    monkeypatch.setenv("FLOODSIM_APP_MODE", "demo")

    response = TestClient(app).post(
        "/api/v1/results/import",
        content=b"not-used",
        headers={"Content-Type": "application/zip"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "RESULT_IMPORT_DISABLED_IN_DEMO"
