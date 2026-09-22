from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from floodsim.domain.geometry import AnalysisArea, GeoBounds, LonLat
from floodsim.preprocessing.adaptive_grid import (
    ADAPTIVE_LEVELS_M,
    ADAPTIVE_THRESHOLD_IDENTITY,
    DEFAULT_ADAPTIVE_GRID_POLICY,
    DEFAULT_ADAPTIVE_THRESHOLDS,
    PRODUCTION_ADAPTIVE_LEVELS_M,
    AdaptiveGridPolicy,
    AdaptiveGridProduct,
    _metric_feature_buffer,
    build_adaptive_grid,
    fit_plane_metrics,
)
from floodsim.preprocessing.full_grid import FullGridProduct, build_full_1m_grid
from floodsim.preprocessing.roof_rainfall import allocate_roof_rainfall


def _full_grid(
    size: int = 64,
    *,
    building: bool = False,
    road: bool = False,
) -> FullGridProduct:
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


def _classifier_policy(**updates: object) -> AdaptiveGridPolicy:
    base = replace(
        DEFAULT_ADAPTIVE_GRID_POLICY,
        target_core_radius_m=0.0,
        target_mid_radius_m=0.0,
    )
    return replace(base, **updates)


def _assert_two_to_one(resolution: np.ndarray) -> None:
    left = resolution[:, :-1]
    right = resolution[:, 1:]
    upper = resolution[:-1, :]
    lower = resolution[1:, :]
    assert np.all(np.maximum(left, right) <= 2 * np.minimum(left, right))
    assert np.all(np.maximum(upper, lower) <= 2 * np.minimum(upper, lower))


def test_plane_fit_is_zero_for_a_plane_and_records_required_evidence() -> None:
    yy, xx = np.indices((8, 8), dtype=float)
    plane_values = 2.0 * xx + 0.5 * yy + 4.0
    plane = fit_plane_metrics(plane_values)

    assert plane.rmse_m == pytest.approx(0.0)
    assert plane.max_abs_residual_m == pytest.approx(0.0)
    assert plane.curvature_indicator_m == pytest.approx(0.0)
    assert plane.elevation_range_m > 0
    assert plane.elevation_std_m > 0
    assert plane.detrended_relief_m == pytest.approx(0.0)
    assert not plane.connectivity_feature_present
    assert 0.0 < plane.flow_accumulation_concentration <= 1.0


def test_flat_open_area_safely_coarsens_to_production_8m_level() -> None:
    result = build_adaptive_grid(_full_grid(), policy=_classifier_policy())

    assert isinstance(result, AdaptiveGridProduct)
    assert result.active_levels_m == PRODUCTION_ADAPTIVE_LEVELS_M
    assert result.cell_count_by_level == {"1m": 0, "2m": 0, "4m": 0, "8m": 64}
    assert result.total_hydraulic_cells == 64
    assert result.full_1m_equivalent_cells == 64 * 64
    assert result.reduction_ratio == pytest.approx(64 / (64 * 64))
    assert set(np.unique(result.resolution_m)) == {8}
    assert ADAPTIVE_LEVELS_M == (1, 2, 4, 8, 16, 32)


def test_adaptive_classifier_reports_granular_progress() -> None:
    updates: list[tuple[float, str]] = []

    build_adaptive_grid(
        _full_grid(),
        policy=_classifier_policy(),
        progress_callback=lambda fraction, detail: updates.append((fraction, detail)),
    )

    assert updates[0][0] == pytest.approx(0.02)
    assert updates[-1] == (1.0, "Adaptive分類: 完了")
    assert any("建物・道路" in detail for _, detail in updates)
    assert any("地形の段差" in detail for _, detail in updates)
    assert any("候補ブロック" in detail for _, detail in updates)
    assert any("2:1整合" in detail for _, detail in updates)
    assert [fraction for fraction, _ in updates] == sorted(fraction for fraction, _ in updates)


def test_smooth_uniform_steep_slope_is_not_kept_at_one_metre() -> None:
    full = _full_grid()
    yy, xx = np.indices(full.elevation_m.shape, dtype=np.float32)
    full = replace(full, elevation_m=(0.8 * xx + 0.5 * yy).astype(np.float32))

    result = build_adaptive_grid(full, policy=_classifier_policy())

    assert set(np.unique(result.resolution_m)) == {8}
    assert result.cell_count_by_level == {"1m": 0, "2m": 0, "4m": 0, "8m": 64}


def test_small_depression_on_flat_surface_remains_high_resolution_with_buffer() -> None:
    full = _full_grid()
    terrain = np.zeros_like(full.elevation_m)
    terrain[32, 32] = -1.0
    full = replace(full, elevation_m=terrain)

    result = build_adaptive_grid(full, policy=_classifier_policy())

    assert result.resolution_m[32, 32] == 1
    assert np.max(result.resolution_m) == 8
    assert result.protection_counts["terrain"] > 0
    _assert_two_to_one(result.resolution_m)


def test_steep_flat_boundary_has_transition_and_never_jumps_one_to_eight() -> None:
    full = _full_grid()
    terrain = np.zeros_like(full.elevation_m)
    x = np.arange(32, dtype=np.float32)
    terrain[:, :32] = x[None, :] * 0.5
    terrain[:, 32:] = terrain[:, 31:32]
    full = replace(full, elevation_m=terrain)

    result = build_adaptive_grid(full, policy=_classifier_policy())

    assert 1 in np.unique(result.resolution_m)
    assert 8 in np.unique(result.resolution_m)
    _assert_two_to_one(result.resolution_m)


def test_one_to_eight_requirement_creates_two_and_four_metre_transition() -> None:
    full = _full_grid(building=True)
    result = build_adaptive_grid(full, policy=_classifier_policy())

    levels = {int(value) for value in np.unique(result.resolution_m)}
    assert {1, 2, 4, 8}.issubset(levels)
    _assert_two_to_one(result.resolution_m)


def test_registered_hard_boundary_is_never_crossed_by_a_coarse_block() -> None:
    full = _full_grid()
    zones = np.zeros(full.elevation_m.shape, dtype=np.int16)
    zones[:, 32:] = 1

    result = build_adaptive_grid(
        full,
        policy=_classifier_policy(),
        hard_boundary_zone=zones,
    )

    assert result.hard_boundary_preserved
    assert result.protection_counts["hard_boundary"] > 0
    for row in range(64):
        for col in range(64):
            size = int(result.resolution_m[row, col])
            top = row - row % size
            left = col - col % size
            block = zones[top : top + size, left : left + size]
            assert np.all(block == block.flat[0])


def test_existing_two_vs_eight_boundary_is_fixed_and_four_metre_band_is_added() -> None:
    full = _full_grid()
    zones = np.zeros(full.elevation_m.shape, dtype=np.int16)
    zones[:, 32:] = 1
    ceiling = np.full(full.elevation_m.shape, 8, dtype=np.int16)
    ceiling[:, :32] = 2

    result = build_adaptive_grid(
        full,
        policy=_classifier_policy(),
        hard_boundary_zone=zones,
        existing_resolution_ceiling_m=ceiling,
    )

    assert np.max(result.resolution_m[:, :32]) <= 2
    assert 4 in np.unique(result.resolution_m[:, 32:])
    assert 8 in np.unique(result.resolution_m[:, 32:])
    _assert_two_to_one(result.resolution_m)


def test_building_narrow_passage_is_not_erased_by_coarsening() -> None:
    full = _full_grid()
    buildings = full.building_mask.copy()
    buildings[20:44, 28:30] = True
    buildings[20:44, 34:36] = True
    sfincs = full.sfincs_mask.copy()
    sfincs[buildings] = 0
    full = replace(full, building_mask=buildings, sfincs_mask=sfincs)

    result = build_adaptive_grid(full, policy=_classifier_policy())

    passage = result.resolution_m[20:44, 30:34]
    assert np.max(passage) <= 2
    assert np.all(full.sfincs_mask[20:44, 30:34] == 1)
    _assert_two_to_one(result.resolution_m)


def test_same_inputs_produce_identical_topology_counts_and_assignment() -> None:
    full = _full_grid(building=True, road=True)
    first = build_adaptive_grid(full, policy=_classifier_policy())
    second = build_adaptive_grid(full, policy=_classifier_policy())

    np.testing.assert_array_equal(first.resolution_m, second.resolution_m)
    np.testing.assert_array_equal(first.level, second.level)
    np.testing.assert_array_equal(first.refinement_reason, second.refinement_reason)
    assert first.cell_count_by_level == second.cell_count_by_level
    assert first.diagnostics == second.diagnostics


def test_target_protection_enforces_configurable_one_and_two_metre_zones() -> None:
    assert DEFAULT_ADAPTIVE_GRID_POLICY.target_core_radius_m == 100.0
    assert DEFAULT_ADAPTIVE_GRID_POLICY.target_mid_radius_m == 250.0

    policy = replace(
        DEFAULT_ADAPTIVE_GRID_POLICY,
        target_core_radius_m=10.0,
        target_mid_radius_m=24.0,
    )
    full = _full_grid(64)
    result = build_adaptive_grid(full, policy=policy)

    yy, xx = np.indices((64, 64), dtype=np.float64)
    radius = np.hypot(xx + 0.5 - 32.0, yy + 0.5 - 32.0)
    core = radius <= policy.target_core_radius_m
    mid = (radius <= policy.target_mid_radius_m) & ~core

    assert np.all(result.resolution_m[core] == 1)
    assert np.all(result.resolution_m[mid] <= policy.target_mid_max_resolution_m)
    assert np.max(result.resolution_m[radius > policy.target_mid_radius_m]) == 8
    assert result.protection_counts["target"] > 0


@pytest.mark.parametrize("feature", ["building", "road"])
def test_hard_structures_are_one_metre_and_buffer_is_at_most_two(feature: str) -> None:
    result = build_adaptive_grid(
        _full_grid(building=feature == "building", road=feature == "road"),
        policy=_classifier_policy(),
    )
    center = result.resolution_m.shape[0] // 2
    assert result.resolution_m[center, center] == 1

    direct = np.zeros_like(result.resolution_m, dtype=bool)
    if feature == "building":
        direct[center, center] = True
    else:
        direct[center, :] = True
    buffered = _metric_feature_buffer(
        direct,
        dx_m=1.0,
        dy_m=1.0,
        distance_m=2.0,
    ) & ~direct
    assert np.all(result.resolution_m[direct] == 1)
    assert np.all(result.resolution_m[buffered] <= 2)
    _assert_two_to_one(result.resolution_m)


def test_threshold_identity_tracks_all_terrain_error_configuration() -> None:
    custom = replace(
        DEFAULT_ADAPTIVE_THRESHOLDS,
        rmse_by_level_m={
            **DEFAULT_ADAPTIVE_THRESHOLDS.rmse_by_level_m,
            8: 0.123,
        },
    )
    result = build_adaptive_grid(
        _full_grid(),
        thresholds=custom,
        policy=_classifier_policy(),
    )

    assert custom.identity != ADAPTIVE_THRESHOLD_IDENTITY
    assert result.threshold_identity == custom.identity
    assert result.threshold_identity.startswith("adaptive-v2-static-terrain-error:")


def test_diagnostics_expose_required_protection_and_resolution_counts() -> None:
    result = build_adaptive_grid(
        _full_grid(building=True, road=True),
        policy=_classifier_policy(),
    )
    diagnostics = result.diagnostics

    assert diagnostics["cell_count_by_level"] == result.cell_count_by_level
    assert diagnostics["full_1m_equivalent_cells"] == 4096
    assert diagnostics["structure_protected_cells"] > 0
    assert "terrain_protected_cells" in diagnostics
    assert "target_protected_cells" in diagnostics
    assert "transition_balance_cells" in diagnostics
    assert diagnostics["minimum_resolution_m"] == 1
    assert diagnostics["maximum_resolution_m"] <= 8



def test_full_1m_mask_is_the_default_adaptive_hard_boundary_source() -> None:
    area = AnalysisArea(
        mode="rectangle",
        bounds=GeoBounds(
            west_deg=139.0,
            south_deg=35.0,
            east_deg=139.001,
            north_deg=35.001,
        ),
        center=LonLat(lon_deg=139.0005, lat_deg=35.0005),
        width_m=8.0,
        height_m=8.0,
        area_m2=64.0,
    )
    elevation = SimpleNamespace(z=np.zeros((8, 8), dtype=np.float32))
    building = np.asarray(
        [
            [-1.0, -1.0],
            [1.0, -1.0],
            [1.0, 1.0],
            [-1.0, 1.0],
            [-1.0, -1.0],
        ],
        dtype=np.float64,
    )
    vectors = SimpleNamespace(
        buildings=[building],
        road_lines=[],
        road_polygons=[],
    )

    full = build_full_1m_grid(area, elevation, vectors)

    assert full.adaptive_hard_boundary_zone is not None
    np.testing.assert_array_equal(
        full.adaptive_hard_boundary_zone,
        full.sfincs_mask.astype(np.int32),
    )
    zones = {int(value) for value in np.unique(full.adaptive_hard_boundary_zone)}
    assert 0 in zones  # building obstacle
    assert 1 in zones  # normal active Full 1 m cells
    assert 3 in zones  # immutable analysis-domain edge
