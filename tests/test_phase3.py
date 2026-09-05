from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient
from shapely.geometry import box

from floodsim.api import routes_results, routes_runs
from floodsim.api.app import app
from floodsim.domain.geometry import AnalysisArea, GeoBounds, LonLat
from floodsim.domain.manifest import Limitations
from floodsim.domain.rainfall import ConstantRainfall
from floodsim.domain.run_config import AccuracyMode, RunConfig
from floodsim.domain.run_state import RunState
from floodsim.orchestration.run_coordinator import RunCoordinator
from floodsim.preprocessing.full_grid import (
    GENERAL_MANNING,
    ROAD_MANNING,
    build_full_1m_grid,
)
from floodsim.preprocessing.roof_rainfall import (
    RoofRunoffNoRecipient,
    allocate_roof_rainfall,
)
from floodsim.providers.common import ProviderProvenance
from floodsim.providers.gsi_elevation import ElevationProduct
from floodsim.results.normalize import normalize_regular_result
from floodsim.sfincs.model_builder import (
    ModelBuildResult,
    derive_output_interval_seconds,
)
from floodsim.sfincs.output_reader import SfincsResultError, read_regular_result
from floodsim.sfincs.runner import ResolvedEngine, SfincsRunResult


def _area(size: int = 4) -> AnalysisArea:
    return AnalysisArea(
        mode="rectangle",
        bounds=GeoBounds(west_deg=139.0, south_deg=35.0, east_deg=139.001, north_deg=35.001),
        center=LonLat(lon_deg=139.0005, lat_deg=35.0005),
        width_m=float(size),
        height_m=float(size),
        area_m2=float(size * size),
    )


def _provenance(provider_id: str, area: AnalysisArea, **details: object) -> ProviderProvenance:
    return ProviderProvenance.create(
        provider_id,
        provider_id,
        area.bounds,
        provider_id,
        "https://example.invalid/terms",
        source_details=details,
        acquired_at_utc="2026-01-01T00:00:00+00:00",
    )


def _elevation(area: AnalysisArea) -> ElevationProduct:
    size = int(area.width_m)
    z = np.zeros((size + 1, size + 1), dtype=np.float32)
    return ElevationProduct(
        z=z,
        x=np.linspace(-size / 2, size / 2, size + 1, dtype=np.float32),
        y=np.linspace(-size / 2, size / 2, size + 1, dtype=np.float32),
        source=np.ones_like(z, dtype=np.uint8),
        source_names=["DEM1A"],
        nearest_filled=0,
        provenance=_provenance("gsi", area, provider_counts={"DEM1A": z.size}),
    )


def _vectors(area: AnalysisArea, *, with_building: bool = True) -> SimpleNamespace:
    building = np.asarray(box(-0.4, -0.4, 0.4, 0.4).exterior.coords, dtype=float)
    road = np.asarray([[-1.5, -1.5], [1.5, -1.5]], dtype=float)
    return SimpleNamespace(
        buildings=[building] if with_building else [],
        road_lines=[road],
        road_polygons=[],
        provenance=_provenance("plateau", area),
    )


def test_roof_rainfall_conserves_mass_and_blocks_roof() -> None:
    building = np.zeros((7, 7), dtype=bool)
    building[3, 3] = True
    allocation = allocate_roof_rainfall(building)
    assert allocation.rain_weight[3, 3] == 0
    assert np.count_nonzero(allocation.rain_weight > 1) == 8
    assert allocation.relative_mass_error <= 1e-9
    assert allocation.hydraulic_weighted_area_m2 == pytest.approx(49.0)


def test_roof_rainfall_fails_without_recipient() -> None:
    with pytest.raises(RoofRunoffNoRecipient):
        allocate_roof_rainfall(np.ones((3, 3), dtype=bool))


def test_full_grid_sets_building_boundary_and_manning() -> None:
    area = _area()
    grid = build_full_1m_grid(area, _elevation(area), _vectors(area))
    assert grid.elevation_m.shape == (4, 4)
    assert grid.cell_count == 16
    assert np.any(grid.building_mask)
    assert np.all(grid.sfincs_mask[grid.building_mask] == 0)
    boundary = np.zeros((4, 4), dtype=bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    assert np.all(grid.sfincs_mask[boundary & ~grid.building_mask] == 3)
    assert np.any(np.isclose(grid.manning_n, ROAD_MANNING))
    assert np.any(np.isclose(grid.manning_n, GENERAL_MANNING))
    assert grid.roof_allocation.relative_mass_error <= 1e-9


def _write_synthetic_result(path: Path, *, nonfinite: bool = False) -> None:
    h = np.asarray(
        [[[0.0, 0.01], [0.02, 0.03]], [[0.0, 0.02], [0.04, 0.05]]],
        dtype=np.float32,
    )
    if nonfinite:
        h[0, 0, 0] = np.nan
    hmax = np.nanmax(h, axis=0, keepdims=True)
    dataset = xr.Dataset(
        {
            "h": (("time", "n", "m"), h),
            "hmax": (("timemax", "n", "m"), hmax),
            "zs": (("time", "n", "m"), h + 1.0),
            "zb": (("n", "m"), np.ones((2, 2), dtype=np.float32)),
            "msk": (("n", "m"), np.ones((2, 2), dtype=np.int16)),
        },
        coords={"time": [0, 60], "timemax": [60]},
    )
    dataset.to_netcdf(path)


def test_output_reader_and_normalizer_expose_max_depth(tmp_path: Path) -> None:
    result_path = tmp_path / "sfincs_map.nc"
    _write_synthetic_result(result_path)
    result = read_regular_result(result_path)
    assert result.global_max_depth_m == pytest.approx(0.05)
    normalized = normalize_regular_result(
        result,
        area=_area(2),
        results_dir=tmp_path / "normalized",
        limitations=Limitations(),
    )
    assert normalized.metadata["max_depth_summary"]["global_max_depth_m"] == pytest.approx(0.05)
    assert normalized.arrays_path.is_file()


def test_output_reader_rejects_nonfinite_active_depth(tmp_path: Path) -> None:
    path = tmp_path / "bad.nc"
    _write_synthetic_result(path, nonfinite=True)
    with pytest.raises(SfincsResultError):
        read_regular_result(path)


def test_output_interval_is_whole_minute_and_bounded() -> None:
    assert derive_output_interval_seconds(60) == 60
    assert derive_output_interval_seconds(3600) == 60
    assert derive_output_interval_seconds(12 * 3600) % 60 == 0
    assert 60 <= derive_output_interval_seconds(12 * 3600) <= 900


class _FakeElevationProvider:
    def acquire(self, area: AnalysisArea, **_: object) -> ElevationProduct:
        return _elevation(area)


class _FakeModelBuilder:
    def build(self, model_dir: Path, grid: object, rainfall: object) -> ModelBuildResult:
        model_dir.mkdir(parents=True, exist_ok=True)
        report = model_dir / "model_build_report.json"
        report.write_text("{}\n", encoding="utf-8")
        return ModelBuildResult(model_dir=model_dir, report_path=report, report={})


class _FakeRunner:
    def cancel(self) -> None:
        return None

    def run(
        self,
        model_dir: Path,
        *,
        logs_dir: Path,
        engine: ResolvedEngine,
        cancel_event: object,
    ) -> SfincsRunResult:
        logs_dir.mkdir(parents=True, exist_ok=True)
        result = model_dir / "sfincs_map.nc"
        _write_synthetic_result(result)
        stdout = logs_dir / "sfincs.stdout.log"
        stderr = logs_dir / "sfincs.stderr.log"
        stdout.write_text("ok\n", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        return SfincsRunResult(0, result, stdout, stderr, engine)


def _test_coordinator(tmp_path: Path) -> RunCoordinator:
    return RunCoordinator(
        runs_root=tmp_path / "runs",
        elevation_provider=_FakeElevationProvider(),
        vector_acquirer=lambda area, **_kwargs: _vectors(area, with_building=False),
        model_builder=_FakeModelBuilder(),
        engine_resolver=lambda: ResolvedEngine(Path(__file__), "test", "TESTSHA"),
        runner_factory=_FakeRunner,
    )


def _config() -> RunConfig:
    return RunConfig(
        analysis_area=_area(2),
        requested_accuracy_mode=AccuracyMode.FULL_1M,
        rainfall=ConstantRainfall(intensity_mm_per_h=60, duration_minutes=1),
    )


def test_coordinator_runs_full_1m_to_normalized_result(tmp_path: Path) -> None:
    coordinator = _test_coordinator(tmp_path)
    record = coordinator.create_run(_config())
    assert record.future is not None
    record.future.result(timeout=10)
    assert record.machine.state is RunState.COMPLETE
    metadata = coordinator.result_metadata(record.run_id)
    assert metadata["max_depth_summary"]["global_max_depth_m"] == pytest.approx(0.05)
    manifest = coordinator.store.read_manifest(record.run_id)
    assert manifest is not None
    assert manifest["run_status"] == "COMPLETE"
    assert manifest["limitations"]["infiltration_modelled"] is False
    assert manifest["limitations"]["sewer_network_modelled"] is False
    assert manifest["roof_rain_mass_diagnostic"]["relative_error"] <= 1e-9
    assert [event.sequence for event in record.events] == list(range(1, len(record.events) + 1))


def test_phase3_api_accepts_run_and_exposes_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator = _test_coordinator(tmp_path)
    monkeypatch.setattr(routes_runs, "coordinator", coordinator)
    monkeypatch.setattr(routes_results, "coordinator", coordinator)
    client = TestClient(app)
    response = client.post("/api/v1/runs", json=_config().model_dump(mode="json"))
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    record = coordinator.get(UUID(run_id))
    assert record.future is not None
    record.future.result(timeout=10)
    status = client.get(f"/api/v1/runs/{run_id}")
    assert status.status_code == 200
    assert status.json()["state"] == "COMPLETE"
    metadata = client.get(f"/api/v1/runs/{run_id}/result-metadata")
    assert metadata.status_code == 200
    assert metadata.json()["max_depth_summary"]["global_max_depth_m"] == pytest.approx(0.05)


def test_run_mutation_requires_json_content_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator = _test_coordinator(tmp_path)
    monkeypatch.setattr(routes_runs, "coordinator", coordinator)
    client = TestClient(app)
    response = client.post("/api/v1/runs", content="{}", headers={"Content-Type": "text/plain"})
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "INPUT_UNSUPPORTED_CONTENT_TYPE"
