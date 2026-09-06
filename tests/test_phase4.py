from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from floodsim.preprocessing.adaptive_grid import (
    ADAPTIVE_LEVELS_M,
    ADAPTIVE_THRESHOLD_IDENTITY,
    AdaptiveGridProduct,
    build_adaptive_grid,
    fit_plane_metrics,
)
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.preprocessing.roof_rainfall import allocate_roof_rainfall


def _full_grid(size: int = 64, *, building: bool = False, road: bool = False) -> FullGridProduct:
    building_mask = np.zeros((size, size), dtype=bool)
    road_mask = np.zeros((size, size), dtype=bool)
    if building:
        building_mask[size // 2, size // 2] = True
    if road:
        road_mask[size // 2, :] = True
    sfincs_mask = np.ones((size, size), dtype=np.uint8)
    sfincs_mask[building_mask] = 0
    return FullGridProduct(
        elevation_m=np.zeros((size, size), dtype=np.float32),
        building_mask=building_mask,
        road_mask=road_mask,
        sfincs_mask=sfincs_mask,
        manning_n=np.full((size, size), 0.03, dtype=np.float32),
        rain_weight=allocate_roof_rainfall(building_mask).rain_weight.astype(np.float32),
        roof_allocation=allocate_roof_rainfall(building_mask),
        width_cells=size,
        height_cells=size,
        dx_m=1.0,
        dy_m=1.0,
        x0_m=-size / 2,
        y0_m=-size / 2,
        crs_wkt="EPSG:3857",
    )


def test_plane_fit_is_zero_for_a_plane_and_detects_curvature() -> None:
    yy, xx = np.indices((8, 8), dtype=float)
    plane = fit_plane_metrics(2.0 * xx + 0.5 * yy + 4.0)
    assert plane.rmse_m == pytest.approx(0.0)
    assert plane.max_abs_residual_m == pytest.approx(0.0)

    curved = fit_plane_metrics((xx - 3.5) ** 2 + (yy - 3.5) ** 2)
    assert curved.rmse_m > 0
    assert curved.curvature_indicator_m > 0


def test_flat_open_area_uses_coarse_power_of_two_cells() -> None:
    result = build_adaptive_grid(_full_grid())
    assert isinstance(result, AdaptiveGridProduct)
    assert result.cell_count_by_level == {"32m": 4}
    assert result.total_hydraulic_cells == 4
    assert result.full_1m_equivalent_cells == 64 * 64
    assert result.reduction_ratio == pytest.approx(4 / (64 * 64))
    assert set(np.unique(result.resolution_m)) == {32}
    assert result.threshold_identity == ADAPTIVE_THRESHOLD_IDENTITY
    assert result.diagnostics["refinement_reason_1m_cells"] == {
        "terrain_coarsened": 64 * 64
    }
    assert ADAPTIVE_LEVELS_M == (1, 2, 4, 8, 16, 32)


def test_terrain_residual_prevents_unsafe_coarsening() -> None:
    full = _full_grid(8)
    rough = np.zeros((8, 8), dtype=np.float32)
    rough[3:5, 3:5] = 1.0
    full = replace(full, elevation_m=rough)

    result = build_adaptive_grid(full)

    assert result.total_hydraulic_cells > 1
    assert np.any(result.resolution_m == 1)
    assert "terrain_or_edge_refinement" in set(result.refinement_reason.ravel())


@pytest.mark.parametrize("feature", ["building", "road"])
def test_hard_features_and_two_metre_buffer_remain_fine(feature: str) -> None:
    result = build_adaptive_grid(_full_grid(building=feature == "building", road=feature == "road"))
    center = result.resolution_m.shape[0] // 2
    assert result.resolution_m[center, center] == 1
    assert result.refinement_reason[center, center] == feature
    assert result.refinement_reason[center - 2, center] == "near_hard_feature"
    assert np.all(result.resolution_m[center - 2 : center + 3, center - 2 : center + 3] <= 2)

    vertical = result.resolution_m[:, 1:]
    horizontal = result.resolution_m[1:, :]
    assert np.all(
        np.maximum(vertical, result.resolution_m[:, :-1])
        <= 2 * np.minimum(vertical, result.resolution_m[:, :-1])
    )
    assert np.all(
        np.maximum(horizontal, result.resolution_m[:-1, :])
        <= 2 * np.minimum(horizontal, result.resolution_m[:-1, :])
    )
