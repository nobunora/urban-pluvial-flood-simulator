from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from floodsim.preprocessing.adaptive_grid import (
    ADAPTIVE_LEVELS_M,
    ADAPTIVE_THRESHOLD_IDENTITY,
    AdaptiveGridProduct,
    AdaptiveThresholds,
    _metric_feature_buffer,
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
    roof_allocation = allocate_roof_rainfall(building_mask)
    return FullGridProduct(
        elevation_m=np.zeros((size, size), dtype=np.float32),
        building_mask=building_mask,
        road_mask=road_mask,
        sfincs_mask=sfincs_mask,
        manning_n=np.full((size, size), 0.03, dtype=np.float32),
        rain_weight=roof_allocation.rain_weight.astype(np.float32),
        roof_allocation=roof_allocation,
        width_cells=size,
        height_cells=size,
        dx_m=1.0,
        dy_m=1.0,
        x0_m=-size / 2,
        y0_m=-size / 2,
        crs_wkt="EPSG:3857",
    )


def test_plane_fit_is_zero_for_a_plane_and_records_required_evidence() -> None:
    yy, xx = np.indices((8, 8), dtype=float)
    plane = fit_plane_metrics(2.0 * xx + 0.5 * yy + 4.0)
    assert plane.rmse_m == pytest.approx(0.0)
    assert plane.max_abs_residual_m == pytest.approx(0.0)
    assert plane.curvature_indicator_m == pytest.approx(0.0)
    assert not plane.connectivity_feature_present
    assert 0.0 < plane.flow_accumulation_concentration <= 1.0

    depression = 2.0 * xx + 0.5 * yy + 4.0
    depression[4, 4] -= 20.0
    complex_metric = fit_plane_metrics(depression)
    assert complex_metric.rmse_m > 0
    assert complex_metric.curvature_indicator_m > 0
    assert complex_metric.connectivity_feature_present
    assert complex_metric.flow_accumulation_concentration > 1.0 / depression.size


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


def test_threshold_identity_tracks_actual_configuration() -> None:
    custom = AdaptiveThresholds(
        rmse_by_level_m={2: 0.0, 4: 0.0, 8: 0.0, 16: 0.0, 32: 0.0},
        max_abs_residual_by_level_m={2: 0.0, 4: 0.0, 8: 0.0, 16: 0.0, 32: 0.0},
    )
    result = build_adaptive_grid(_full_grid(), thresholds=custom)

    assert custom.identity != ADAPTIVE_THRESHOLD_IDENTITY
    assert result.threshold_identity == custom.identity
    assert result.threshold_identity.startswith("adaptive-v1-rmse-max-residual:")


def test_terrain_residual_prevents_unsafe_coarsening() -> None:
    full = _full_grid(8)
    rough = np.zeros((8, 8), dtype=np.float32)
    rough[3:5, 3:5] = 1.0
    full = replace(full, elevation_m=rough)

    result = build_adaptive_grid(full)

    assert result.total_hydraulic_cells > 1
    assert np.any(result.resolution_m == 1)
    assert "terrain_or_edge_refinement" in set(result.refinement_reason.ravel())


def test_feature_buffer_uses_projected_cell_footprint_distance() -> None:
    feature = np.zeros((9, 9), dtype=bool)
    feature[4, 4] = True
    buffered = _metric_feature_buffer(feature, dx_m=1.0, dy_m=1.0)

    # Offset three cells axially leaves exactly 2 m between closed 1 m cells.
    assert buffered[1, 4]
    # Offset two cells diagonally leaves sqrt(2) m between cell footprints.
    assert buffered[2, 2]
    # Offset three cells diagonally leaves sqrt(8) m, so it is outside the rule.
    assert not buffered[1, 1]


@pytest.mark.parametrize("feature", ["building", "road"])
def test_hard_features_are_one_metre_and_buffer_is_at_most_two(feature: str) -> None:
    result = build_adaptive_grid(_full_grid(building=feature == "building", road=feature == "road"))
    center = result.resolution_m.shape[0] // 2
    assert result.resolution_m[center, center] == 1
    assert result.refinement_reason[center, center] == feature

    direct = np.zeros_like(result.resolution_m, dtype=bool)
    if feature == "building":
        direct[center, center] = True
    else:
        direct[center, :] = True
    buffered = _metric_feature_buffer(direct, dx_m=1.0, dy_m=1.0) & ~direct
    assert np.all(result.resolution_m[direct] == 1)
    assert np.all(result.resolution_m[buffered] <= 2)
    assert np.any(result.resolution_m[buffered] == 2)

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
