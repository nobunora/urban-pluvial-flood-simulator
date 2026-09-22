from __future__ import annotations

import dataclasses
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from pyproj import CRS

from floodsim.domain.rainfall import RainfallTimeSeries
from floodsim.preprocessing.adaptive_grid import (
    DEFAULT_ADAPTIVE_GRID_POLICY,
    build_adaptive_grid,
)
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.preprocessing.roof_rainfall import allocate_roof_rainfall
from floodsim.sfincs.model_builder import AdaptiveSfincsModelBuilder


def _authorityless_crs() -> CRS:
    return CRS.from_proj4(
        "+proj=aeqd +lat_0=35.0005 +lon_0=139.0005 +datum=WGS84 +units=m +no_defs"
    )


def _grid(size: int = 32) -> FullGridProduct:
    building = np.zeros((size, size), dtype=bool)
    road = np.zeros((size, size), dtype=bool)
    mask = np.ones((size, size), dtype=np.uint8)
    mask[0, :] = 3
    mask[-1, :] = 3
    mask[:, 0] = 3
    mask[:, -1] = 3
    manning = np.full((size, size), 0.030, dtype=np.float32)
    allocation = allocate_roof_rainfall(building)
    yy, xx = np.indices((size, size), dtype=np.float32)
    elevation = 0.002 * xx + 0.001 * yy
    return FullGridProduct(
        elevation_m=elevation.astype(np.float32),
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
        x0_m=-size / 2.0,
        y0_m=-size / 2.0,
        crs_wkt=_authorityless_crs().to_wkt(),
    )


def _rainfall() -> RainfallTimeSeries:
    return RainfallTimeSeries(
        start_time=datetime(2026, 9, 21, tzinfo=timezone.utc),
        elapsed_seconds=[0.0, 60.0],
        intensity_mm_per_h=[30.0, 0.0],
        source_metadata={"kind": "test"},
    )


def test_adaptive_builder_writes_quadtree_subgrid_and_distributed_rainfall(
    tmp_path: Path,
) -> None:
    full = _grid()
    adaptive = build_adaptive_grid(
        full,
        policy=replace(
            DEFAULT_ADAPTIVE_GRID_POLICY,
            target_core_radius_m=0.0,
            target_mid_radius_m=0.0,
        ),
    )
    builder = AdaptiveSfincsModelBuilder(subgrid_pixels=2, subgrid_levels=3)

    result = builder.build(tmp_path / "model", full, adaptive, _rainfall())

    assert result.report["grid_type"] == "quadtree"
    assert result.report["subgrid"]["source_terrain_resolution_m"] == 1.0
    assert result.report["subgrid"]["pixels_per_hydraulic_cell"] == 2
    assert result.report["subgrid"]["hypsometric_levels"] == 3
    assert result.report["subgrid"]["face_count"] == result.report["total_hydraulic_cells"]
    assert result.report["subgrid"]["uv_point_count"] > 0
    assert result.report["subgrid"]["sample_evaluations"] == (
        result.report["subgrid"]["face_count"]
        + result.report["subgrid"]["uv_point_count"]
    ) * 4
    assert result.report["build_phase_timings_seconds"]["subgrid_create_cpu_s"] >= 0
    assert result.report["threshold_identity"] == adaptive.threshold_identity
    assert result.report["classifier_diagnostics"]["active_levels_m"] == [1, 2, 4, 8]
    assert result.report["classifier_diagnostics"]["maximum_resolution_m"] <= 8
    assert "terrain_protected_cells" in result.report["classifier_diagnostics"]
    assert "structure_protected_cells" in result.report["classifier_diagnostics"]
    assert "target_protected_cells" in result.report["classifier_diagnostics"]
    assert "transition_balance_cells" in result.report["classifier_diagnostics"]
    assert result.report["rainfall_volume_after_weight_area_m2"] == pytest.approx(
        result.report["rainfall_volume_before_weight_area_m2"]
    )
    assert result.report["total_hydraulic_cells"] < full.cell_count

    model_dir = result.model_dir
    for name in (
        "sfincs.inp",
        "sfincs.nc",
        "sfincs_subgrid.nc",
        "sfincs_netampr.nc",
        "adaptive_face_layout.npz",
        "model_build_report.json",
    ):
        assert (model_dir / name).is_file(), name

    inp = (model_dir / "sfincs.inp").read_text(encoding="utf-8")
    assert "qtrfile" in inp
    assert "sbgfile" in inp
    assert "netamprfile" in inp
    assert "storehsubgrid" in inp
    assert "storezvolume" in inp
    assert "regular_output_on_mesh" in inp
    assert re.search(r"^alpha\s*=\s*0\.75\s*$", inp, re.MULTILINE)
    assert result.adaptive_layout_path == model_dir / "adaptive_face_layout.npz"
    assert result.report["depth_output"]["storehsubgrid"] == 1
    assert result.report["volume_output"]["storezvolume"] == 1
    assert result.report["mesh_output"]["regular_output_on_mesh"] == 1
    assert result.report["mesh_output"]["face_dimension"] == "nmesh2d_face"

    with xr.open_dataset(model_dir / "sfincs.nc") as dataset:
        assert "mesh2d_crs" in dataset
        assert "crs_wkt" in dataset["mesh2d_crs"].attrs
        assert "mask" in dataset
        assert "manning" in dataset
        assert "epsg" not in dataset["mesh2d_crs"].attrs
        assert "epsg_code" not in dataset["mesh2d_crs"].attrs

    with xr.open_dataset(model_dir / "sfincs_subgrid.nc") as dataset:
        assert "z_level" in dataset

    with xr.open_dataset(model_dir / "sfincs_netampr.nc") as dataset:
        assert "Precipitation" in dataset
        assert dataset["Precipitation"].dims == ("time", "y", "x")
        assert dataset.sizes["x"] == full.width_cells
        assert dataset.sizes["y"] == full.height_cells


def test_adaptive_subgrid_cache_reuses_rainfall_independent_table(tmp_path: Path) -> None:
    full = _grid()
    adaptive = build_adaptive_grid(
        full,
        policy=replace(
            DEFAULT_ADAPTIVE_GRID_POLICY,
            target_core_radius_m=0.0,
            target_mid_radius_m=0.0,
        ),
    )
    builder = AdaptiveSfincsModelBuilder(
        subgrid_pixels=2,
        subgrid_levels=3,
        cache_root=tmp_path / "cache",
    )

    first = builder.build(tmp_path / "first", full, adaptive, _rainfall())
    changed_rain = RainfallTimeSeries(
        start_time=datetime(2026, 9, 21, tzinfo=timezone.utc),
        elapsed_seconds=[0.0, 120.0],
        intensity_mm_per_h=[75.0, 0.0],
        source_metadata={"kind": "changed-rain"},
    )
    second = builder.build(tmp_path / "second", full, adaptive, changed_rain)

    assert first.report["static_model_cache"]["cache_hit"] is False
    assert second.report["static_model_cache"]["cache_hit"] is True
    assert first.report["static_model_cache"]["cache_key"] == second.report["static_model_cache"]["cache_key"]
    for name in ("sfincs.nc", "sfincs_subgrid.nc", "adaptive_face_layout.npz"):
        assert (second.model_dir / name).read_bytes() == (first.model_dir / name).read_bytes()
    with xr.open_dataset(second.model_dir / "sfincs_netampr.nc") as dataset:
        assert float(dataset["Precipitation"].isel(time=0).max()) == pytest.approx(75.0)


def test_adaptive_static_cache_rebuilds_incomplete_bundle(tmp_path: Path) -> None:
    full = _grid()
    adaptive = build_adaptive_grid(
        full,
        policy=replace(
            DEFAULT_ADAPTIVE_GRID_POLICY,
            target_core_radius_m=0.0,
            target_mid_radius_m=0.0,
        ),
    )
    cache_root = tmp_path / "cache"
    builder = AdaptiveSfincsModelBuilder(
        subgrid_pixels=2,
        subgrid_levels=3,
        cache_root=cache_root,
    )
    first = builder.build(tmp_path / "first", full, adaptive, _rainfall())
    cache_key = first.report["static_model_cache"]["cache_key"]
    (cache_root / cache_key / "adaptive_face_layout.npz").unlink()

    second = builder.build(tmp_path / "second", full, adaptive, _rainfall())

    assert second.report["static_model_cache"]["cache_hit"] is False
    assert (cache_root / cache_key / "adaptive_face_layout.npz").is_file()


def test_adaptive_static_cache_key_changes_with_grid_origin(tmp_path: Path) -> None:
    grid = _grid()
    adaptive = build_adaptive_grid(grid)
    builder = AdaptiveSfincsModelBuilder(cache_root=tmp_path)

    shifted = dataclasses.replace(grid, x0_m=grid.x0_m + 1000.0)
    assert builder._subgrid_cache_key(grid, adaptive) != builder._subgrid_cache_key(
        shifted, adaptive
    )


def test_adaptive_subgrid_strategy_changes_cache_key(tmp_path: Path) -> None:
    grid = _grid()
    adaptive = build_adaptive_grid(grid)
    uniform = AdaptiveSfincsModelBuilder(cache_root=tmp_path)
    variable = AdaptiveSfincsModelBuilder(
        cache_root=tmp_path, subgrid_strategy="2-2-4-8"
    )

    assert uniform._subgrid_cache_key(grid, adaptive) != variable._subgrid_cache_key(
        grid, adaptive
    )


def test_adaptive_builder_rejects_unknown_subgrid_strategy() -> None:
    with pytest.raises(ValueError, match="unsupported subgrid_strategy"):
        AdaptiveSfincsModelBuilder(subgrid_strategy="unknown")


def test_adaptive_builder_writes_2248_subgrid_strategy(tmp_path: Path) -> None:
    full = _grid()
    adaptive = build_adaptive_grid(full)
    result = AdaptiveSfincsModelBuilder(
        subgrid_levels=3,
        subgrid_strategy="2-2-4-8",
    ).build(tmp_path / "model", full, adaptive, _rainfall())

    assert result.report["subgrid"]["strategy"] == "2-2-4-8"
    assert result.report["subgrid"]["pixels_by_cell_size_m"] == {
        "1": 2,
        "2": 2,
        "4": 4,
        "8": 8,
    }
    assert result.report["subgrid"]["effective_coarsest_subpixel_m"] == 1.0
    with xr.open_dataset(result.model_dir / "sfincs_subgrid.nc") as dataset:
        assert set(dataset.data_vars) == {
            "z_zmin",
            "z_zmax",
            "z_volmax",
            "z_level",
            "uv_zmin",
            "uv_zmax",
            "uv_havg",
            "uv_nrep",
            "uv_pwet",
            "uv_ffit",
            "uv_navg",
        }


def test_adaptive_builder_writes_optimized_2248_strategy(tmp_path: Path) -> None:
    full = _grid()
    adaptive = build_adaptive_grid(full)
    result = AdaptiveSfincsModelBuilder(
        subgrid_levels=3,
        subgrid_strategy="2-2-4-8-optimized",
    ).build(tmp_path / "model", full, adaptive, _rainfall())

    subgrid = result.report["subgrid"]
    assert subgrid["strategy"] == "2-2-4-8-optimized"
    assert subgrid["pixels_by_cell_size_m"] == {"1": 2, "2": 2, "4": 4, "8": 8}
    assert subgrid["optimizations"] == [
        "elide_repeated_1m_2x2_samples",
        "direct_aligned_2m_4m_8m_tables",
        "selected_uv_ordered_scan",
        "no_global_uv_sort",
        "parallel_face_uv_tables",
        "specialized_1m_2m_kernels",
    ]


def test_adaptive_static_cache_key_changes_with_sfincs_mask(tmp_path: Path) -> None:
    grid = _grid()
    adaptive = build_adaptive_grid(grid)
    builder = AdaptiveSfincsModelBuilder(cache_root=tmp_path)

    changed_mask = grid.sfincs_mask.copy()
    changed_mask[1, 1] = 0 if changed_mask[1, 1] else 1
    changed = dataclasses.replace(grid, sfincs_mask=changed_mask)
    assert builder._subgrid_cache_key(grid, adaptive) != builder._subgrid_cache_key(
        changed, adaptive
    )
