from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from floodsim.api import routes_results
from floodsim.api.app import app
from floodsim.domain.geometry import AnalysisArea, GeoBounds, LonLat
from floodsim.results.view import (
    DEPTH_BANDS,
    NormalizedArrays,
    PointOutsideResult,
    ResultTimeIndexInvalid,
    inspect_native_point,
    load_normalized_arrays,
    render_grid_resolution_png,
    render_max_depth_png,
    render_time_depth_png,
)


def _area() -> AnalysisArea:
    return AnalysisArea(
        mode="rectangle",
        bounds=GeoBounds(
            west_deg=138.999,
            south_deg=34.999,
            east_deg=139.001,
            north_deg=35.001,
        ),
        center=LonLat(lon_deg=139.0, lat_deg=35.0),
        width_m=2.0,
        height_m=2.0,
        area_m2=4.0,
    )


def _arrays() -> NormalizedArrays:
    depth = np.asarray(
        [
            [[0.0, 0.02], [0.03, 0.04]],
            [[0.005, 0.06], [0.20, 1.20]],
        ],
        dtype=np.float32,
    )
    max_depth = np.asarray([[0.005, 0.06], [0.20, 1.20]], dtype=np.float32)
    terrain = np.asarray([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    active = np.asarray([[True, True], [False, True]])
    return NormalizedArrays(
        depth_time_m=depth,
        max_depth_m=max_depth,
        terrain_elevation_m=terrain,
        active_mask=active,
        time_values=("0", "60"),
        grid_resolution_m=1.0,
    )


def _rgba(png: bytes) -> np.ndarray:
    with Image.open(BytesIO(png)) as image:
        return np.asarray(image.convert("RGBA"))


def test_max_depth_png_is_north_up_and_transparent_for_dry_no_data() -> None:
    rgba = _rgba(render_max_depth_png(_arrays(), max_px=4096))

    assert rgba.shape == (2, 2, 4)
    # PNG row 0 is north, so internal row 1 appears first.
    assert rgba[0, 0, 3] == 0  # inactive cell
    assert tuple(rgba[0, 1]) == DEPTH_BANDS[-1].rgba
    assert rgba[1, 0, 3] == 0  # active but < 0.01 m
    assert tuple(rgba[1, 1]) == DEPTH_BANDS[1].rgba


def test_time_depth_png_validates_time_index() -> None:
    rgba = _rgba(render_time_depth_png(_arrays(), time_index=0))
    assert tuple(rgba[0, 1]) == DEPTH_BANDS[0].rgba

    with pytest.raises(ResultTimeIndexInvalid):
        render_time_depth_png(_arrays(), time_index=2)


def test_grid_resolution_png_uses_native_active_mask() -> None:
    rgba = _rgba(render_grid_resolution_png(_arrays()))
    assert rgba[0, 0, 3] == 0
    assert rgba[0, 1, 3] > 0
    assert rgba[1, 0, 3] > 0


def test_native_point_inspection_does_not_sample_display_png() -> None:
    arrays = _arrays()
    area = _area()

    inspected = inspect_native_point(
        arrays,
        area=area,
        lon_deg=139.0,
        lat_deg=35.0,
        time_index=1,
    )
    assert inspected["has_data"] is True
    assert inspected["row"] == 1
    assert inspected["column"] == 1
    assert inspected["depth_m"] == pytest.approx(1.20)
    assert inspected["max_depth_m"] == pytest.approx(1.20)
    assert inspected["terrain_elevation_m"] == pytest.approx(4.0)
    assert inspected["grid_resolution_m"] == pytest.approx(1.0)
    assert inspected["time_value"] == "60"

    with pytest.raises(PointOutsideResult):
        inspect_native_point(
            arrays,
            area=area,
            lon_deg=140.0,
            lat_deg=35.0,
        )


def test_load_normalized_arrays_supports_scalar_grid_resolution(tmp_path: Path) -> None:
    path = tmp_path / "normalized_full_1m.npz"
    arrays = _arrays()
    np.savez_compressed(
        path,
        depth_time_m=arrays.depth_time_m,
        max_depth_m=arrays.max_depth_m,
        terrain_elevation_m=arrays.terrain_elevation_m,
        active_mask=arrays.active_mask,
        time_values=np.asarray(arrays.time_values),
        grid_resolution_m=np.float32(1.0),
    )

    loaded = load_normalized_arrays(path)

    assert loaded.shape == (2, 2)
    assert loaded.time_values == ("0", "60")
    assert loaded.grid_resolution_m == pytest.approx(1.0)


class _ResultCoordinator:
    def __init__(self, tmp_path: Path) -> None:
        self.run_id = uuid4()
        self.area = _area()
        self.arrays_path = tmp_path / "normalized_full_1m.npz"
        arrays = _arrays()
        np.savez_compressed(
            self.arrays_path,
            depth_time_m=arrays.depth_time_m,
            max_depth_m=arrays.max_depth_m,
            terrain_elevation_m=arrays.terrain_elevation_m,
            active_mask=arrays.active_mask,
            time_values=np.asarray(arrays.time_values),
            grid_resolution_m=np.float32(1.0),
        )

    def result_arrays_path(self, run_id: UUID) -> Path:
        assert run_id == self.run_id
        return self.arrays_path

    def result_metadata(self, run_id: UUID) -> dict[str, object]:
        assert run_id == self.run_id
        return {
            "schema_version": "1",
            "bounds": self.area.bounds.model_dump(),
            "units": {
                "water_depth": "m",
                "terrain_elevation": "m",
                "grid_resolution": "m",
            },
            "available_time_indices": [0, 1],
            "time_values": ["0", "60"],
            "max_depth_summary": {"global_max_depth_m": 1.2},
            "grid_level_summary": {"1m": 3},
            "depth_legend": [band.to_metadata() for band in DEPTH_BANDS],
            "provider_summary": {
                "building_provider": "osm",
                "road_provider": "osm",
                "warnings": ["PLATEAU fallback"],
            },
            "engine_summary": {
                "sfincs_version": "2.4.0 Galibier",
                "sfincs_build_sha256": "ABC",
                "sfincs_engine_source": "SFINCS_BIN",
                "hydromt_sfincs_version": "2.0.0rc3",
            },
            "no_data_policy": "test",
            "limitations": {
                "infiltration_modelled": False,
                "sewer_network_modelled": False,
                "storm_drain_inlets_modelled": False,
                "building_interior_modelled": False,
                "spatial_meteorological_rainfall_modelled": False,
                "river_stage_boundary_modelled": False,
                "coastal_tide_surge_modelled": False,
                "official_forecast": False,
            },
        }

    def get(self, run_id: UUID) -> SimpleNamespace:
        assert run_id == self.run_id
        return SimpleNamespace(config=SimpleNamespace(analysis_area=self.area))


def test_result_api_exposes_png_metadata_and_native_inspection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    coordinator = _ResultCoordinator(tmp_path)
    monkeypatch.setattr(routes_results, "coordinator", coordinator)
    client = TestClient(app)

    metadata = client.get(f"/api/v1/runs/{coordinator.run_id}/result-metadata")
    assert metadata.status_code == 200
    assert metadata.json()["provider_summary"]["building_provider"] == "osm"
    assert metadata.json()["engine_summary"]["sfincs_version"] == "2.4.0 Galibier"

    max_depth = client.get(f"/api/v1/runs/{coordinator.run_id}/layers/max-depth.png")
    assert max_depth.status_code == 200
    assert max_depth.headers["content-type"] == "image/png"
    assert max_depth.content.startswith(b"\x89PNG")

    time_depth = client.get(
        f"/api/v1/runs/{coordinator.run_id}/layers/depth.png",
        params={"time_index": 1},
    )
    assert time_depth.status_code == 200

    bad_time = client.get(
        f"/api/v1/runs/{coordinator.run_id}/layers/depth.png",
        params={"time_index": 99},
    )
    assert bad_time.status_code == 400
    assert bad_time.json()["error"]["code"] == "RESULT_TIME_INDEX_INVALID"

    grid = client.get(f"/api/v1/runs/{coordinator.run_id}/layers/grid-resolution.png")
    assert grid.status_code == 200

    inspection = client.get(
        f"/api/v1/runs/{coordinator.run_id}/inspect",
        params={"lon": 139.0, "lat": 35.0, "time_index": 1},
    )
    assert inspection.status_code == 200
    assert inspection.json()["depth_m"] == pytest.approx(1.20)

    outside = client.get(
        f"/api/v1/runs/{coordinator.run_id}/inspect",
        params={"lon": 140.0, "lat": 35.0},
    )
    assert outside.status_code == 404
    assert outside.json()["error"]["code"] == "POINT_OUTSIDE_RESULT"
