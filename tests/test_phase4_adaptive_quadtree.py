from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pyproj import CRS

from floodsim.preprocessing.adaptive_grid import (
    AdaptiveGridPolicy,
    build_adaptive_grid,
)

_EXTENSION_POLICY = AdaptiveGridPolicy(
    active_levels_m=(1, 2, 4, 8, 16, 32),
    target_core_radius_m=0.0,
    target_mid_radius_m=0.0,
)
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.preprocessing.roof_rainfall import allocate_roof_rainfall
from floodsim.sfincs.adaptive_quadtree import create_adaptive_quadtree
from floodsim.sfincs.model_builder import _load_sfincs_model, _sfincs_environment


def _authorityless_crs() -> CRS:
    return CRS.from_proj4(
        "+proj=aeqd +lat_0=35.0005 +lon_0=139.0005 +datum=WGS84 +units=m +no_defs"
    )


def _full_grid(
    width: int,
    height: int,
    *,
    building: tuple[int, int] | None = None,
    road_row: int | None = None,
) -> FullGridProduct:
    building_mask = np.zeros((height, width), dtype=bool)
    road_mask = np.zeros((height, width), dtype=bool)
    if building is not None:
        building_mask[building] = True
    if road_row is not None:
        road_mask[road_row, :] = True

    sfincs_mask = np.ones((height, width), dtype=np.uint8)
    sfincs_mask[0, :] = 3
    sfincs_mask[-1, :] = 3
    sfincs_mask[:, 0] = 3
    sfincs_mask[:, -1] = 3
    sfincs_mask[building_mask] = 0

    manning = np.full((height, width), 0.030, dtype=np.float32)
    manning[road_mask & ~building_mask] = 0.020
    allocation = allocate_roof_rainfall(building_mask)
    return FullGridProduct(
        elevation_m=np.zeros((height, width), dtype=np.float32),
        building_mask=building_mask,
        road_mask=road_mask,
        sfincs_mask=sfincs_mask,
        manning_n=manning,
        rain_weight=allocation.rain_weight.astype(np.float32),
        roof_allocation=allocation,
        width_cells=width,
        height_cells=height,
        dx_m=1.0,
        dy_m=1.0,
        x0_m=-width / 2.0,
        y0_m=-height / 2.0,
        crs_wkt=_authorityless_crs().to_wkt(),
    )


def _model(tmp_path: Path):
    with _sfincs_environment():
        SfincsModel = _load_sfincs_model()
        model = SfincsModel(root=tmp_path, mode="w+", write_gis=False)
        _ = model.config.data
    return model


def _face_for_source_cell(component, resolution: np.ndarray, row: int, col: int) -> int:
    rows = np.asarray(component.data["n"].values, dtype=int) - 1
    cols = np.asarray(component.data["m"].values, dtype=int) - 1
    for index, size_value in enumerate(resolution):
        size = int(size_value)
        row0 = int(rows[index]) * size
        col0 = int(cols[index]) * size
        if row0 <= row < row0 + size and col0 <= col < col0 + size:
            return index
    raise AssertionError("source cell is not covered by any quadtree face")


def _source_coverage(component, resolution: np.ndarray, height: int, width: int) -> np.ndarray:
    rows = np.asarray(component.data["n"].values, dtype=int) - 1
    cols = np.asarray(component.data["m"].values, dtype=int) - 1
    coverage = np.zeros((height, width), dtype=np.uint8)
    for index, size_value in enumerate(resolution):
        size = int(size_value)
        row0 = int(rows[index]) * size
        col0 = int(cols[index]) * size
        row1 = min(row0 + size, height)
        col1 = min(col0 + size, width)
        if row0 < height and col0 < width and row1 > row0 and col1 > col0:
            coverage[row0:row1, col0:col1] += 1
    return coverage


def test_flat_open_classifier_maps_to_four_32m_faces(tmp_path: Path) -> None:
    full = _full_grid(64, 64)
    adaptive = build_adaptive_grid(full, policy=_EXTENSION_POLICY)
    model = _model(tmp_path)

    result = create_adaptive_quadtree(model, full, adaptive)

    assert result.base_nmax == 2
    assert result.base_mmax == 2
    assert result.padded_width_m == 64.0
    assert result.padded_height_m == 64.0
    assert result.refinement_polygon_count == 0
    assert result.refined_parent_count == 0
    assert result.face_count == 4
    np.testing.assert_array_equal(result.face_fields.resolution_m, np.full(4, 32))
    np.testing.assert_allclose(result.face_fields.manning_n, 0.030)
    assert result.face_fields.hydraulic_weighted_area_m2 == pytest.approx(
        float(np.sum(full.rain_weight, dtype=np.float64))
    )
    assert model.quadtree_grid.crs.equals(_authorityless_crs())
    assert model.quadtree_grid.crs.to_epsg() is None
    assert model.config.get("epsg", None) is None
    assert model.config.get("crsgeo") == 0


def test_hard_building_and_road_survive_actual_rc3_face_mapping(tmp_path: Path) -> None:
    full = _full_grid(64, 64, building=(32, 32), road_row=32)
    adaptive = build_adaptive_grid(full, policy=_EXTENSION_POLICY)
    model = _model(tmp_path)

    result = create_adaptive_quadtree(model, full, adaptive)
    fields = result.face_fields

    assert result.refined_parent_count > 0
    building_face = _face_for_source_cell(model.quadtree_grid, fields.resolution_m, 32, 32)
    road_face = _face_for_source_cell(model.quadtree_grid, fields.resolution_m, 32, 10)
    assert fields.resolution_m[building_face] == 1
    assert fields.sfincs_mask[building_face] == 0
    assert fields.resolution_m[road_face] == 1
    assert fields.sfincs_mask[road_face] != 0
    assert fields.manning_n[road_face] == pytest.approx(0.020)

    rows = np.asarray(model.quadtree_grid.data["n"].values, dtype=int) - 1
    cols = np.asarray(model.quadtree_grid.data["m"].values, dtype=int) - 1
    for index, size_value in enumerate(fields.resolution_m):
        size = int(size_value)
        row0 = int(rows[index]) * size
        col0 = int(cols[index]) * size
        row1 = min(row0 + size, full.height_cells)
        col1 = min(col0 + size, full.width_cells)
        if row1 > row0 and col1 > col0:
            assert np.all(size <= adaptive.resolution_m[row0:row1, col0:col1])

    np.testing.assert_array_equal(
        _source_coverage(
            model.quadtree_grid,
            fields.resolution_m,
            full.height_cells,
            full.width_cells,
        ),
        1,
    )
    assert fields.hydraulic_weighted_area_m2 == pytest.approx(
        float(np.sum(full.rain_weight, dtype=np.float64)), abs=1e-6
    )
    np.testing.assert_array_equal(model.quadtree_grid.data["mask"].values, fields.sfincs_mask)
    np.testing.assert_allclose(model.quadtree_grid.data["manning"].values, fields.manning_n)


def test_odd_domain_is_padded_but_padding_is_inactive_and_rain_mass_is_exact(tmp_path: Path) -> None:
    full = _full_grid(33, 35)
    adaptive = build_adaptive_grid(full, policy=_EXTENSION_POLICY)
    model = _model(tmp_path)

    result = create_adaptive_quadtree(model, full, adaptive)
    fields = result.face_fields

    assert result.base_nmax == 2
    assert result.base_mmax == 2
    assert result.padded_width_m == 64.0
    assert result.padded_height_m == 64.0
    assert result.refined_parent_count > 0
    assert np.any(fields.source_overlap_area_m2 == 0.0)
    np.testing.assert_array_equal(fields.sfincs_mask[fields.source_overlap_area_m2 == 0.0], 0)
    np.testing.assert_array_equal(
        _source_coverage(
            model.quadtree_grid,
            fields.resolution_m,
            full.height_cells,
            full.width_cells,
        ),
        1,
    )
    assert fields.hydraulic_weighted_area_m2 == pytest.approx(
        float(np.sum(full.rain_weight, dtype=np.float64)), abs=1e-6
    )

    edge_face = _face_for_source_cell(model.quadtree_grid, fields.resolution_m, 34, 32)
    assert fields.resolution_m[edge_face] == 1


def test_asymmetric_domain_preserves_n_m_orientation_and_source_coverage(tmp_path: Path) -> None:
    full = _full_grid(65, 34, building=(10, 64), road_row=20)
    adaptive = build_adaptive_grid(full, policy=_EXTENSION_POLICY)
    model = _model(tmp_path)

    result = create_adaptive_quadtree(model, full, adaptive)
    fields = result.face_fields

    assert result.base_nmax == 2
    assert result.base_mmax == 3
    assert result.padded_width_m == 96.0
    assert result.padded_height_m == 64.0
    assert result.refined_parent_count > 0
    np.testing.assert_array_equal(
        _source_coverage(
            model.quadtree_grid,
            fields.resolution_m,
            full.height_cells,
            full.width_cells,
        ),
        1,
    )

    building_face = _face_for_source_cell(model.quadtree_grid, fields.resolution_m, 10, 64)
    road_face = _face_for_source_cell(model.quadtree_grid, fields.resolution_m, 20, 5)
    assert fields.resolution_m[building_face] == 1
    assert fields.sfincs_mask[building_face] == 0
    assert fields.resolution_m[road_face] == 1
    assert fields.manning_n[road_face] == pytest.approx(0.020)
    assert fields.hydraulic_weighted_area_m2 == pytest.approx(
        float(np.sum(full.rain_weight, dtype=np.float64)), abs=1e-6
    )


def test_face_rain_weights_preserve_float64_mass_at_realistic_scale(tmp_path: Path) -> None:
    """Many refined faces must not accumulate float32 round-off into mass loss."""
    full = _full_grid(257, 257)
    # Use a non-binary redistribution field so aggregation exercises fractional
    # weights rather than the trivial all-ones open-area case.
    building_mask = full.building_mask.copy()
    building_mask[128, 128] = True
    allocation = allocate_roof_rainfall(building_mask)
    full = FullGridProduct(
        elevation_m=full.elevation_m,
        building_mask=building_mask,
        road_mask=full.road_mask,
        sfincs_mask=np.where(building_mask, 0, full.sfincs_mask).astype(np.uint8),
        manning_n=full.manning_n,
        rain_weight=allocation.rain_weight.astype(np.float32),
        roof_allocation=allocation,
        width_cells=full.width_cells,
        height_cells=full.height_cells,
        dx_m=full.dx_m,
        dy_m=full.dy_m,
        x0_m=full.x0_m,
        y0_m=full.y0_m,
        crs_wkt=full.crs_wkt,
    )
    adaptive = build_adaptive_grid(full, policy=_EXTENSION_POLICY)
    model = _model(tmp_path)

    result = create_adaptive_quadtree(model, full, adaptive)

    assert result.face_fields.rain_weight.dtype == np.float64
    expected = float(np.sum(full.rain_weight, dtype=np.float64))
    assert result.face_fields.hydraulic_weighted_area_m2 == pytest.approx(
        expected, rel=1e-12, abs=1e-9
    )
