from __future__ import annotations

import numpy as np
import pytest

from floodsim.sfincs.output_reader import (
    AdaptiveFaceLayout,
    SfincsQuadtreeResult,
    SfincsRegularResult,
)
from floodsim.validation.adaptive_accuracy import (
    MAX_ACCOUNTED_VOLUME_REL_DIFF,
    MIN_FLOODED_AREA_IOU,
    adaptive_max_depth_on_source_grid,
    evaluate_adaptive_case,
    evaluate_adaptive_suite,
)


def _full() -> SfincsRegularResult:
    maximum = np.asarray(
        [
            [0.10, 0.10, 0.20, 0.20],
            [0.10, 0.10, 0.20, 0.20],
            [0.00, 0.00, 0.30, 0.30],
            [0.00, 0.00, 0.30, 0.30],
        ],
        dtype=np.float32,
    )
    return SfincsRegularResult(
        depth_time_m=np.stack([np.zeros_like(maximum), maximum], axis=0),
        max_depth_m=maximum,
        terrain_elevation_m=np.zeros_like(maximum),
        active_mask=np.ones_like(maximum, dtype=bool),
        time_values=("0", "60"),
    )


def _adaptive(*, shifted: bool = False) -> SfincsQuadtreeResult:
    values = (
        np.asarray([0.0, 0.20, 0.10, 0.30], dtype=np.float32)
        if shifted
        else np.asarray([0.10, 0.20, 0.00, 0.30], dtype=np.float32)
    )
    layout = AdaptiveFaceLayout(
        resolution_m=np.asarray([2, 2, 2, 2], dtype=np.int16),
        row_index=np.asarray([0, 0, 1, 1], dtype=np.int32),
        col_index=np.asarray([0, 1, 0, 1], dtype=np.int32),
        source_overlap_area_m2=np.asarray([4.0, 4.0, 4.0, 4.0]),
        sfincs_mask=np.ones(4, dtype=np.uint8),
        source_height_cells=4,
        source_width_cells=4,
    )
    return SfincsQuadtreeResult(
        depth_time_m=np.stack([np.zeros(4, dtype=np.float32), values], axis=0),
        max_depth_m=values,
        terrain_elevation_m=np.zeros(4, dtype=np.float32),
        active_mask=np.ones(4, dtype=bool),
        time_values=("0", "60"),
        layout=layout,
        subgrid_volume_m3=np.asarray(
            [[0.0, 0.0, 0.0, 0.0], [0.4, 0.8, 0.0, 1.2]],
            dtype=np.float64,
        ),
    )


def test_adaptive_validation_passes_only_with_complete_evidence() -> None:
    report = evaluate_adaptive_case(
        _full(),
        _adaptive(),
        benchmark_name="flat-open",
        benchmark_class="open_area",
        full_accounted_volume_m3=2.4,
        adaptive_accounted_volume_m3=2.4,
        connectivity_preserved=True,
    )

    assert report.flooded_area_iou == pytest.approx(1.0)
    assert report.median_abs_max_depth_difference_m == pytest.approx(0.0)
    assert report.p95_abs_max_depth_difference_m == pytest.approx(0.0)
    assert report.accounted_volume_relative_difference == pytest.approx(0.0)
    assert report.adaptive_final_surface_water_volume_m3 == pytest.approx(2.4)
    assert report.cell_count_reduced is True
    assert report.passed is True

    suite = evaluate_adaptive_suite([report])
    assert suite.open_area_cell_reduction_proven is True
    assert suite.passed is True


def test_adaptive_validation_does_not_invent_missing_volume_or_connectivity() -> None:
    report = evaluate_adaptive_case(
        _full(),
        _adaptive(),
        benchmark_name="incomplete",
        benchmark_class="urban",
    )

    assert report.criteria["accounted_final_surface_water_volume"] is None
    assert report.criteria["important_flow_path_connectivity"] is None
    assert report.passed is False


def test_adaptive_validation_detects_flood_extent_change() -> None:
    report = evaluate_adaptive_case(
        _full(),
        _adaptive(shifted=True),
        benchmark_name="shifted",
        benchmark_class="urban",
        full_accounted_volume_m3=2.4,
        adaptive_accounted_volume_m3=2.4 * (1 + MAX_ACCOUNTED_VOLUME_REL_DIFF),
        connectivity_preserved=True,
    )

    assert report.flooded_area_iou < MIN_FLOODED_AREA_IOU
    assert report.criteria["flooded_area_iou"] is False
    assert report.passed is False


def test_adaptive_projection_uses_face_footprints() -> None:
    projected = adaptive_max_depth_on_source_grid(_adaptive())

    assert projected.shape == (4, 4)
    assert np.allclose(projected[:2, :2], 0.10)
    assert np.allclose(projected[:2, 2:], 0.20)
    assert np.allclose(projected[2:, :2], 0.00)
    assert np.allclose(projected[2:, 2:], 0.30)
