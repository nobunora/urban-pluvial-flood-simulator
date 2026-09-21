from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pyproj import CRS

from floodsim.domain.geometry import AnalysisArea, GeoBounds, LonLat
from floodsim.domain.rainfall import ConstantRainfall, RainfallTimeSeries
from floodsim.domain.run_config import AccuracyMode, RunConfig
from floodsim.domain.run_state import RunState
from floodsim.orchestration.run_coordinator import (
    AdaptiveNotAvailable,
    RunCoordinator,
)
from floodsim.preprocessing.adaptive_grid import build_adaptive_grid
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.preprocessing.roof_rainfall import allocate_roof_rainfall
from floodsim.results.normalize import NormalizedResult
from floodsim.sfincs.model_builder import ModelBuildResult
from floodsim.sfincs.runner import ResolvedEngine, SfincsRunResult


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
        width_m=4.0,
        height_m=4.0,
        area_m2=16.0,
    )


def _grid() -> FullGridProduct:
    size = 4
    building = np.zeros((size, size), dtype=bool)
    road = np.zeros((size, size), dtype=bool)
    mask = np.ones((size, size), dtype=np.uint8)
    manning = np.full((size, size), 0.030, dtype=np.float32)
    allocation = allocate_roof_rainfall(building)
    crs = CRS.from_proj4(
        "+proj=aeqd +lat_0=35 +lon_0=139 +datum=WGS84 +units=m +no_defs"
    )
    return FullGridProduct(
        elevation_m=np.zeros((size, size), dtype=np.float32),
        building_mask=building,
        road_mask=road,
        sfincs_mask=mask,
        manning_n=manning,
        rain_weight=allocation.rain_weight.astype(np.float32),
        roof_allocation=allocation,
        width_cells=size,
        height_cells=size,
        dx_m=1.0,
        dy_m=1.0,
        x0_m=-2.0,
        y0_m=-2.0,
        crs_wkt=crs.to_wkt(),
    )


def _config() -> RunConfig:
    return RunConfig(
        analysis_area=_area(),
        requested_accuracy_mode=AccuracyMode.ADAPTIVE,
        rainfall=ConstantRainfall(intensity_mm_per_h=30, duration_minutes=1),
    )


def _rainfall(*_args: object, **_kwargs: object) -> RainfallTimeSeries:
    return RainfallTimeSeries(
        start_time=datetime(2026, 9, 21, tzinfo=timezone.utc),
        elapsed_seconds=[0.0, 60.0],
        intensity_mm_per_h=[30.0, 0.0],
        source_metadata={"kind": "test"},
    )


class _AdaptiveBuilder:
    def __init__(self) -> None:
        self.adaptive = None

    def build(
        self,
        model_dir: Path,
        grid: FullGridProduct,
        adaptive: object,
        rainfall: RainfallTimeSeries,
    ) -> ModelBuildResult:
        del grid, rainfall
        self.adaptive = adaptive
        model_dir.mkdir(parents=True, exist_ok=True)
        report_path = model_dir / "model_build_report.json"
        report_path.write_text("{}\n", encoding="utf-8")
        layout_path = model_dir / "adaptive_face_layout.npz"
        np.savez_compressed(
            layout_path,
            resolution_m=np.asarray([4], dtype=np.int16),
        )
        return ModelBuildResult(
            model_dir=model_dir,
            report_path=report_path,
            report={"grid_type": "quadtree"},
            adaptive_layout_path=layout_path,
        )


class _Runner:
    def cancel(self) -> None:
        return None

    def run(
        self,
        model_dir: Path,
        *,
        logs_dir: Path,
        engine: ResolvedEngine,
        cancel_event: object,
        progress_callback=None,
        line_callback=None,
    ) -> SfincsRunResult:
        del cancel_event
        logs_dir.mkdir(parents=True, exist_ok=True)
        result = model_dir / "sfincs_map.nc"
        result.write_bytes(b"adaptive-test")
        stdout = logs_dir / "sfincs.stdout.log"
        stderr = logs_dir / "sfincs.stderr.log"
        stdout.write_text("ok\n", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        if line_callback is not None:
            line_callback("100% complete, 0.0 s remaining")
        if progress_callback is not None:
            progress_callback(SimpleNamespace(fraction=1.0))
        return SfincsRunResult(
            0,
            result,
            stdout,
            stderr,
            engine,
            elapsed_seconds=0.1,
        )


def _normalizer(
    raw_result: object,
    *,
    results_dir: Path,
    **_kwargs: object,
) -> NormalizedResult:
    assert raw_result == {"kind": "adaptive"}
    results_dir.mkdir(parents=True, exist_ok=True)
    arrays_path = results_dir / "normalized_adaptive_faces.npz"
    np.savez_compressed(
        arrays_path,
        storage_kind=np.asarray("quadtree_faces"),
    )
    metadata_path = results_dir / "result_metadata.json"
    metadata = {
        "schema_version": "1",
        "max_depth_summary": {"global_max_depth_m": 0.2},
        "grid_level_summary": {"4m": 1},
    }
    metadata_path.write_text("{}\n", encoding="utf-8")
    return NormalizedResult(arrays_path, metadata_path, metadata)


def _coordinator(tmp_path: Path, *, enabled: bool) -> tuple[RunCoordinator, _AdaptiveBuilder]:
    builder = _AdaptiveBuilder()

    def reader(path: Path, *, layout_path: Path) -> dict[str, str]:
        assert path.name == "sfincs_map.nc"
        assert layout_path.name == "adaptive_face_layout.npz"
        return {"kind": "adaptive"}

    coordinator = RunCoordinator(
        runs_root=tmp_path / "runs",
        adaptive_enabled=enabled,
        rainfall_resolver=_rainfall,
        adaptive_model_builder=builder,
        adaptive_result_reader=reader,
        adaptive_result_normalizer=_normalizer,
        engine_resolver=lambda: ResolvedEngine(
            Path(__file__),
            "2.4.0 Galibier",
            "TESTSHA",
        ),
        runner_factory=_Runner,
    )
    coordinator.prepared_cache.save(
        _area(),
        _grid(),
        metadata={
            "elevation_provider_counts": {"test": 25},
            "elevation_source_summary": {"grid_m": 1.0},
            "building_provider": "test",
            "road_provider": "test",
            "provider_warnings": [],
        },
    )
    return coordinator, builder


def test_adaptive_remains_disabled_by_default(tmp_path: Path) -> None:
    coordinator, _builder = _coordinator(tmp_path, enabled=False)

    with pytest.raises(AdaptiveNotAvailable):
        coordinator.create_run(_config())


def test_enabled_adaptive_runs_through_native_face_result_path(tmp_path: Path) -> None:
    coordinator, builder = _coordinator(tmp_path, enabled=True)

    record = coordinator.create_run(_config())
    assert record.future is not None
    record.future.result(timeout=10)

    assert record.machine.state is RunState.COMPLETE, (
        record.failure_code,
        record.failure_message,
        record.activity_lines,
    )
    assert builder.adaptive is not None
    assert record.result_metadata is not None
    assert record.result_metadata["grid_level_summary"] == {"4m": 1}
    assert record.manifest.requested_accuracy_mode is AccuracyMode.ADAPTIVE
    assert record.manifest.output_files["normalized_arrays"] == (
        "normalized_adaptive_faces.npz"
    )
    assert record.manifest.final_grid_level_counts
    assert any("Adaptive格子分類完了" in line for line in record.activity_lines)
    assert any("Adaptive計算が完了" in line for line in record.activity_lines)


def test_adaptive_constraints_survive_cache_and_reach_classifier(tmp_path: Path) -> None:
    hard_boundary = np.zeros((4, 4), dtype=np.int32)
    hard_boundary[:, 2:] = 1
    resolution_ceiling = np.full((4, 4), 4, dtype=np.int16)
    resolution_ceiling[:, :2] = 2
    native_structure = np.zeros((4, 4), dtype=bool)
    native_structure[1, 1] = True
    constrained_grid = replace(
        _grid(),
        adaptive_hard_boundary_zone=hard_boundary,
        adaptive_resolution_ceiling_m=resolution_ceiling,
        native_structure_mask=native_structure,
    )

    captured: dict[str, object] = {}

    def classifier(grid: FullGridProduct, **kwargs: object):
        captured.update(kwargs)
        return build_adaptive_grid(grid, **kwargs)

    builder = _AdaptiveBuilder()

    def reader(path: Path, *, layout_path: Path) -> dict[str, str]:
        assert path.name == "sfincs_map.nc"
        assert layout_path.name == "adaptive_face_layout.npz"
        return {"kind": "adaptive"}

    coordinator = RunCoordinator(
        runs_root=tmp_path / "runs",
        adaptive_enabled=True,
        adaptive_grid_builder=classifier,
        rainfall_resolver=_rainfall,
        adaptive_model_builder=builder,
        adaptive_result_reader=reader,
        adaptive_result_normalizer=_normalizer,
        engine_resolver=lambda: ResolvedEngine(
            Path(__file__),
            "2.4.0 Galibier",
            "TESTSHA",
        ),
        runner_factory=_Runner,
    )
    coordinator.prepared_cache.save(
        _area(),
        constrained_grid,
        metadata={
            "elevation_provider_counts": {"test": 25},
            "elevation_source_summary": {"grid_m": 1.0},
            "building_provider": "test",
            "road_provider": "test",
            "provider_warnings": [],
        },
    )

    loaded = coordinator.prepared_cache.load(_area())
    assert loaded is not None
    np.testing.assert_array_equal(
        loaded.grid.adaptive_hard_boundary_zone,
        hard_boundary,
    )
    np.testing.assert_array_equal(
        loaded.grid.adaptive_resolution_ceiling_m,
        resolution_ceiling,
    )
    np.testing.assert_array_equal(
        loaded.grid.native_structure_mask,
        native_structure,
    )

    record = coordinator.create_run(_config())
    assert record.future is not None
    record.future.result(timeout=10)

    assert record.machine.state is RunState.COMPLETE, (
        record.failure_code,
        record.failure_message,
        record.activity_lines,
    )
    np.testing.assert_array_equal(captured["hard_boundary_zone"], hard_boundary)
    np.testing.assert_array_equal(
        captured["existing_resolution_ceiling_m"],
        resolution_ceiling,
    )
    np.testing.assert_array_equal(
        captured["native_structure_mask"],
        native_structure,
    )
    assert "policy" in captured
