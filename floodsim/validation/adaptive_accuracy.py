"""Full 1 m versus Adaptive validation gate from specification section 20.6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from floodsim.sfincs.output_reader import SfincsQuadtreeResult, SfincsRegularResult

FLOODED_DEPTH_THRESHOLD_M = 0.05
MIN_FLOODED_AREA_IOU = 0.90
MAX_MEDIAN_ABS_DEPTH_DIFF_M = 0.03
MAX_P95_ABS_DEPTH_DIFF_M = 0.10
MAX_ACCOUNTED_VOLUME_REL_DIFF = 0.02


@dataclass(frozen=True)
class AdaptiveValidationReport:
    benchmark_name: str
    benchmark_class: str
    flooded_area_iou: float
    median_abs_max_depth_difference_m: float | None
    p95_abs_max_depth_difference_m: float | None
    full_final_surface_water_volume_m3: float
    adaptive_final_surface_water_volume_m3: float | None
    accounted_volume_relative_difference: float | None
    connectivity_preserved: bool | None
    full_1m_equivalent_cells: int
    adaptive_hydraulic_cells: int
    criteria: Mapping[str, bool | None]

    @property
    def cell_count_reduced(self) -> bool:
        return self.adaptive_hydraulic_cells < self.full_1m_equivalent_cells

    @property
    def passed(self) -> bool:
        """Return True only when every hydraulic acceptance criterion is proven."""
        return all(value is True for value in self.criteria.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_name": self.benchmark_name,
            "benchmark_class": self.benchmark_class,
            "flooded_area_iou": self.flooded_area_iou,
            "median_abs_max_depth_difference_m": self.median_abs_max_depth_difference_m,
            "p95_abs_max_depth_difference_m": self.p95_abs_max_depth_difference_m,
            "full_final_surface_water_volume_m3": self.full_final_surface_water_volume_m3,
            "adaptive_final_surface_water_volume_m3": self.adaptive_final_surface_water_volume_m3,
            "accounted_volume_relative_difference": self.accounted_volume_relative_difference,
            "connectivity_preserved": self.connectivity_preserved,
            "full_1m_equivalent_cells": self.full_1m_equivalent_cells,
            "adaptive_hydraulic_cells": self.adaptive_hydraulic_cells,
            "cell_count_reduced": self.cell_count_reduced,
            "criteria": dict(self.criteria),
            "passed": self.passed,
        }


@dataclass(frozen=True)
class AdaptiveValidationSuite:
    reports: tuple[AdaptiveValidationReport, ...]
    open_area_cell_reduction_proven: bool

    @property
    def passed(self) -> bool:
        return (
            bool(self.reports)
            and all(report.passed for report in self.reports)
            and self.open_area_cell_reduction_proven
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reports": [report.to_dict() for report in self.reports],
            "open_area_cell_reduction_proven": self.open_area_cell_reduction_proven,
            "passed": self.passed,
        }


def adaptive_max_depth_on_source_grid(
    result: SfincsQuadtreeResult,
) -> np.ndarray:
    """Project one Adaptive face field to the source 1 m comparison grid."""
    layout = result.layout
    raster = np.full(
        (layout.source_height_cells, layout.source_width_cells),
        np.nan,
        dtype=np.float32,
    )
    coverage = np.zeros(raster.shape, dtype=np.uint8)
    for index, size_value in enumerate(layout.resolution_m):
        size = int(size_value)
        row0 = int(layout.row_index[index]) * size
        col0 = int(layout.col_index[index]) * size
        row1 = min(row0 + size, layout.source_height_cells)
        col1 = min(col0 + size, layout.source_width_cells)
        if row1 <= row0 or col1 <= col0:
            continue
        coverage[row0:row1, col0:col1] += 1
        if result.active_mask[index] and np.isfinite(result.max_depth_m[index]):
            raster[row0:row1, col0:col1] = result.max_depth_m[index]

    if np.any(coverage != 1):
        raise ValueError(
            "Adaptive face layout must cover the source comparison grid exactly once"
        )
    return raster


def _relative_difference(reference: float, candidate: float) -> float:
    if not np.isfinite(reference) or not np.isfinite(candidate):
        raise ValueError("volume comparison inputs must be finite")
    if reference < 0.0 or candidate < 0.0:
        raise ValueError("volume comparison inputs must be non-negative")
    if reference == 0.0:
        return 0.0 if candidate == 0.0 else float("inf")
    return abs(candidate - reference) / reference


def evaluate_adaptive_case(
    full: SfincsRegularResult,
    adaptive: SfincsQuadtreeResult,
    *,
    benchmark_name: str,
    benchmark_class: str,
    full_accounted_volume_m3: float | None = None,
    adaptive_accounted_volume_m3: float | None = None,
    connectivity_preserved: bool | None = None,
) -> AdaptiveValidationReport:
    """Evaluate one representative case against the fixed section 20.6 thresholds.

    The two accounted-volume arguments must already account for open-boundary
    outflow. The evaluator deliberately does not infer that correction from
    storage alone.
    """
    if full.max_depth_m.shape != (
        adaptive.layout.source_height_cells,
        adaptive.layout.source_width_cells,
    ):
        raise ValueError("Full and Adaptive comparison grids do not match")

    adaptive_depth = adaptive_max_depth_on_source_grid(adaptive)
    full_depth = np.asarray(full.max_depth_m, dtype=np.float32)

    full_flooded = np.isfinite(full_depth) & (
        full_depth >= FLOODED_DEPTH_THRESHOLD_M
    )
    adaptive_flooded = np.isfinite(adaptive_depth) & (
        adaptive_depth >= FLOODED_DEPTH_THRESHOLD_M
    )
    union = full_flooded | adaptive_flooded
    intersection = full_flooded & adaptive_flooded
    union_count = int(np.count_nonzero(union))
    flooded_iou = (
        1.0
        if union_count == 0
        else float(np.count_nonzero(intersection) / union_count)
    )

    if np.any(intersection):
        differences = np.abs(
            full_depth[intersection].astype(np.float64)
            - adaptive_depth[intersection].astype(np.float64)
        )
        median_difference: float | None = float(np.median(differences))
        p95_difference: float | None = float(np.percentile(differences, 95))
    elif union_count == 0:
        median_difference = 0.0
        p95_difference = 0.0
    else:
        median_difference = None
        p95_difference = None

    full_final_volume = float(np.nansum(full.depth_time_m[-1], dtype=np.float64))
    adaptive_final_volume = (
        float(np.nansum(adaptive.subgrid_volume_m3[-1], dtype=np.float64))
        if adaptive.subgrid_volume_m3 is not None
        and adaptive.subgrid_volume_m3.shape[0] > 0
        else None
    )

    accounted_relative_difference: float | None = None
    if (
        full_accounted_volume_m3 is not None
        and adaptive_accounted_volume_m3 is not None
    ):
        accounted_relative_difference = _relative_difference(
            float(full_accounted_volume_m3),
            float(adaptive_accounted_volume_m3),
        )

    criteria: dict[str, bool | None] = {
        "flooded_area_iou": flooded_iou >= MIN_FLOODED_AREA_IOU,
        "median_abs_max_depth_difference": (
            None
            if median_difference is None
            else median_difference <= MAX_MEDIAN_ABS_DEPTH_DIFF_M
        ),
        "p95_abs_max_depth_difference": (
            None
            if p95_difference is None
            else p95_difference <= MAX_P95_ABS_DEPTH_DIFF_M
        ),
        "accounted_final_surface_water_volume": (
            None
            if accounted_relative_difference is None
            else accounted_relative_difference <= MAX_ACCOUNTED_VOLUME_REL_DIFF
        ),
        "important_flow_path_connectivity": connectivity_preserved,
    }
    return AdaptiveValidationReport(
        benchmark_name=benchmark_name,
        benchmark_class=benchmark_class,
        flooded_area_iou=flooded_iou,
        median_abs_max_depth_difference_m=median_difference,
        p95_abs_max_depth_difference_m=p95_difference,
        full_final_surface_water_volume_m3=full_final_volume,
        adaptive_final_surface_water_volume_m3=adaptive_final_volume,
        accounted_volume_relative_difference=accounted_relative_difference,
        connectivity_preserved=connectivity_preserved,
        full_1m_equivalent_cells=int(full.max_depth_m.size),
        adaptive_hydraulic_cells=adaptive.layout.face_count,
        criteria=criteria,
    )


def evaluate_adaptive_suite(
    reports: list[AdaptiveValidationReport] | tuple[AdaptiveValidationReport, ...],
) -> AdaptiveValidationSuite:
    frozen = tuple(reports)
    open_area_reduction = any(
        report.benchmark_class == "open_area" and report.cell_count_reduced
        for report in frozen
    )
    return AdaptiveValidationSuite(
        reports=frozen,
        open_area_cell_reduction_proven=open_area_reduction,
    )
