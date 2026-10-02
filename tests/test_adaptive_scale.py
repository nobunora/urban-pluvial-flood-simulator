"""Acceptance cases for spatially weighted perceptual classification."""

import json
from dataclasses import replace
from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from floodsim.results.adaptive_scale import (
    boundary_labels,
    color_indices,
    generate_adaptive_breaks,
)
from floodsim.results.view import NormalizedArrays, render_time_depth_png


@pytest.mark.parametrize("outlier", [10.17, 100.0])
def test_localized_extreme_preserves_core_and_true_maximum(outlier: float) -> None:
    values = np.r_[np.linspace(0.01, 1, 10000), outlier]
    scale = generate_adaptive_breaks(values)
    assert scale.mode == "hybrid"
    assert scale.class_count == 7
    assert scale.core_class_count == 5
    assert scale.tail_class_count == 2
    assert scale.breaks[5] <= 1.1
    assert scale.breaks[-1] == outlier
    assert np.all(np.diff(scale.breaks) > 0)
    metadata = json.loads(json.dumps(scale.to_metadata(), allow_nan=False))
    assert metadata["core_class_count"] == 5
    assert metadata["tail_class_count"] == 2


def test_uniform_area_has_no_tail_compression() -> None:
    scale = generate_adaptive_breaks(np.linspace(0.001, 1, 10000))
    assert scale.mode == "quantile"
    assert len(scale.breaks) == 8
    counts = np.bincount(color_indices(np.linspace(0.001, 1, 10000), scale))
    assert np.min(counts) > 800


def test_dry_and_invalid_cells_do_not_distort_quantiles() -> None:
    wet = np.linspace(0.02, 1, 1000)
    expected = generate_adaptive_breaks(wet, zero_epsilon=0.01)
    actual = generate_adaptive_breaks(
        np.r_[np.zeros(9000), 0.01, np.nan, np.inf, wet], zero_epsilon=0.01
    )
    assert actual.breaks == expected.breaks
    assert actual.active_area == 1000
    assert generate_adaptive_breaks(np.zeros(3)).mode == "empty"


def test_nonuniform_mesh_is_invariant_to_subdivision() -> None:
    values = np.linspace(0.1, 1, 20)
    values = np.r_[values, 100]
    weights = np.r_[np.full(20, 10.0), 0.01]
    original = generate_adaptive_breaks(values, weights)
    subdivided = generate_adaptive_breaks(
        np.repeat(values, 10), np.repeat(weights / 10, 10)
    )
    assert subdivided.breaks == original.breaks
    assert subdivided.active_area == pytest.approx(original.active_area)
    assert (
        generate_adaptive_breaks(np.array([1, 2, 3]), np.array([0, -1, np.nan])).mode
        == "empty"
    )


@pytest.mark.parametrize("offset", [-100, 0, 100])
def test_elevation_preserves_actual_minimum_and_signed_values(offset: float) -> None:
    values = np.r_[np.linspace(10, 11, 10000), 100] + offset
    scale = generate_adaptive_breaks(values, anchor_zero=False)
    assert scale.breaks[0] == 10 + offset
    assert scale.breaks[-1] == 100 + offset
    assert scale.mode == "hybrid"
    assert scale.core_class_count == 5
    assert scale.breaks[5] <= 11.1 + offset


def test_degenerate_values_do_not_generate_zero_width_intervals() -> None:
    for values in [
        np.ones(100),
        np.tile([0.2, 0.5], 100),
        np.linspace(0.18, 0.21, 100),
    ]:
        scale = generate_adaptive_breaks(values)
        assert scale.class_count <= len(np.unique(values))
        assert np.all(np.diff(scale.breaks) > 0)
    terrain = generate_adaptive_breaks(np.full(100, -2), anchor_zero=False)
    assert terrain.breaks == (-2,)
    assert terrain.class_count == 1


def test_repeated_quantiles_preserve_classes_when_real_levels_exist() -> None:
    scale = generate_adaptive_breaks(np.r_[np.linspace(0.1, 0.9, 100), np.ones(10000)])
    assert scale.class_count == 7
    assert np.all(np.diff(scale.breaks) > 0)


def test_labels_cover_true_maximum_and_distinguish_narrow_terrain_ranges() -> None:
    for edges in [
        (0, 1.2, 10.17432),
        (-2.1, -1.4, -0.1234567),
        (100, 100.00001, 100.00002),
    ]:
        labels = boundary_labels(edges)
        assert float(labels[-1]) >= edges[-1]
        assert len(set(labels)) == len(edges)


def test_critical_threshold_has_priority_over_snapping() -> None:
    scale = generate_adaptive_breaks(
        np.linspace(0.001, 1, 10000), critical_thresholds=(0.287,)
    )
    assert 0.287 in scale.breaks
    assert scale.critical_thresholds_used == (0.287,)


def test_reference_scale_keeps_depth_and_speed_colors_stable() -> None:
    reference = np.linspace(0.02, 1, 100).reshape(10, 10)
    arrays = NormalizedArrays(
        depth_time_m=np.stack([reference, reference / 2]),
        max_depth_m=reference,
        terrain_elevation_m=reference - 10,
        active_mask=np.ones(reference.shape, dtype=bool),
        time_values=("0", "1"),
        grid_resolution_m=1.0,
        velocity_u_mps=np.stack([reference, reference / 2]),
        velocity_v_mps=np.zeros((2, 10, 10)),
    )
    same_values = replace(arrays, depth_time_m=np.stack([reference / 2, reference / 2]))
    assert render_time_depth_png(arrays, time_index=1) == render_time_depth_png(
        same_values, time_index=0
    )
    with Image.open(BytesIO(render_time_depth_png(arrays, time_index=1))) as image:
        assert np.asarray(image).shape == (10, 10, 4)
    assert arrays.speed_scale.breaks[-1] == 1
    assert arrays.speed_scale is arrays.speed_scale
