"""Accuracy-first Adaptive grid classification on the Full 1 m source grid.

This module deliberately stops at a deterministic, inspectable resolution map.
The SFINCS quadtree writer is kept separate so classification can be tested
without enabling the Adaptive run path.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Final

import numpy as np

from floodsim.preprocessing.full_grid import FullGridProduct

ADAPTIVE_LEVELS_M: Final[tuple[int, ...]] = (1, 2, 4, 8, 16, 32)
_ADAPTIVE_THRESHOLD_SCHEMA: Final[str] = "adaptive-v1-rmse-max-residual"
_FEATURE_BUFFER_DISTANCE_M: Final[float] = 2.0


@dataclass(frozen=True)
class PlaneFitMetrics:
    """Terrain-complexity evidence for one candidate hydraulic block."""

    rmse_m: float
    max_abs_residual_m: float
    curvature_indicator_m: float
    connectivity_feature_present: bool
    flow_accumulation_concentration: float


@dataclass(frozen=True)
class AdaptiveThresholds:
    """Provisional thresholds from the v0.1 Adaptive specification."""

    rmse_by_level_m: dict[int, float]
    max_abs_residual_by_level_m: dict[int, float]

    @classmethod
    def provisional(cls) -> AdaptiveThresholds:
        return cls(
            rmse_by_level_m={2: 0.03, 4: 0.04, 8: 0.05, 16: 0.06, 32: 0.08},
            max_abs_residual_by_level_m={2: 0.10, 4: 0.12, 8: 0.15, 16: 0.20, 32: 0.25},
        )

    @property
    def identity(self) -> str:
        """Return a deterministic identity for the actual threshold values."""

        payload = {
            "schema": _ADAPTIVE_THRESHOLD_SCHEMA,
            "rmse_by_level_m": sorted(
                (int(level), float(value)) for level, value in self.rmse_by_level_m.items()
            ),
            "max_abs_residual_by_level_m": sorted(
                (int(level), float(value))
                for level, value in self.max_abs_residual_by_level_m.items()
            ),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return f"{_ADAPTIVE_THRESHOLD_SCHEMA}:{digest}"


DEFAULT_ADAPTIVE_THRESHOLDS: Final[AdaptiveThresholds] = AdaptiveThresholds.provisional()
ADAPTIVE_THRESHOLD_IDENTITY: Final[str] = DEFAULT_ADAPTIVE_THRESHOLDS.identity


@dataclass(frozen=True)
class AdaptiveGridProduct:
    """Deterministic Adaptive diagnostics over a 1 m equivalent raster."""

    resolution_m: np.ndarray
    level: np.ndarray
    refinement_reason: np.ndarray
    plane_fit_metrics: dict[str, PlaneFitMetrics]
    cell_count_by_level: dict[str, int]
    total_hydraulic_cells: int
    full_1m_equivalent_cells: int
    reduction_ratio: float
    threshold_identity: str

    @property
    def resolution_layer_m(self) -> np.ndarray:
        """Return the resolution layer used by previews and diagnostics."""

        return self.resolution_m

    @property
    def diagnostics(self) -> dict[str, object]:
        """Return serializable Adaptive diagnostics for a manifest/report."""

        labels, counts = np.unique(self.refinement_reason, return_counts=True)
        return {
            "cell_count_by_level": dict(self.cell_count_by_level),
            "total_hydraulic_cells": self.total_hydraulic_cells,
            "full_1m_equivalent_cells": self.full_1m_equivalent_cells,
            "reduction_ratio": self.reduction_ratio,
            "threshold_identity": self.threshold_identity,
            "refinement_reason_1m_cells": {
                str(label): int(count) for label, count in zip(labels, counts)
            },
        }


def _connectivity_feature_present(values: np.ndarray) -> bool:
    """Detect strict interior depressions/ridges using the 8-neighbour stencil.

    This is evidence only. The canonical specification fixes no numerical
    threshold that would allow this diagnostic alone to change coarsening.
    """

    if min(values.shape) < 3:
        return False
    center = values[1:-1, 1:-1]
    neighbours = np.stack(
        [
            values[dy : dy + center.shape[0], dx : dx + center.shape[1]]
            for dy in range(3)
            for dx in range(3)
            if (dy, dx) != (1, 1)
        ]
    )
    local_minimum = center < np.min(neighbours, axis=0)
    local_maximum = center > np.max(neighbours, axis=0)
    return bool(np.any(local_minimum | local_maximum))


def _flow_accumulation_concentration(values: np.ndarray) -> float:
    """Return deterministic D8 peak contributing-area fraction for a block.

    Each source cell contributes one unit and drains to its lowest strictly
    lower 8-neighbour. Equal-elevation ties use row-major cell order. The
    returned maximum accumulated count divided by block cell count is an
    inspectable concentration indicator in [1/N, 1]. No coarsening threshold
    for this indicator is invented here because v0.1 does not specify one.
    """

    rows, cols = values.shape
    cell_count = rows * cols
    downstream = np.full(cell_count, -1, dtype=np.int64)
    offsets = (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    )
    for row in range(rows):
        for col in range(cols):
            current = float(values[row, col])
            best_elevation = current
            best_index = -1
            for dy, dx in offsets:
                neighbour_row = row + dy
                neighbour_col = col + dx
                if not (0 <= neighbour_row < rows and 0 <= neighbour_col < cols):
                    continue
                neighbour = float(values[neighbour_row, neighbour_col])
                neighbour_index = neighbour_row * cols + neighbour_col
                if neighbour < best_elevation or (
                    neighbour == best_elevation
                    and neighbour < current
                    and (best_index < 0 or neighbour_index < best_index)
                ):
                    best_elevation = neighbour
                    best_index = neighbour_index
            downstream[row * cols + col] = best_index

    accumulation = np.ones(cell_count, dtype=np.float64)
    order = np.argsort(values.ravel(), kind="stable")[::-1]
    for source in order:
        destination = int(downstream[int(source)])
        if destination >= 0:
            accumulation[destination] += accumulation[int(source)]
    return float(accumulation.max() / cell_count)


def fit_plane_metrics(elevation_m: np.ndarray) -> PlaneFitMetrics:
    """Fit a plane and summarize all required candidate terrain evidence."""

    values = np.asarray(elevation_m, dtype=float)
    if values.ndim != 2 or min(values.shape) < 2:
        raise ValueError("plane-fit input must be a two-dimensional block")
    if not np.isfinite(values).all():
        raise ValueError("plane-fit input contains non-finite elevation")
    yy, xx = np.indices(values.shape, dtype=float)
    xc = xx - xx.mean()
    yc = yy - yy.mean()
    zc = values - values.mean()
    sxx = float(np.sum(xc * xc))
    syy = float(np.sum(yc * yc))
    sxy = float(np.sum(xc * yc))
    sxz = float(np.sum(xc * zc))
    syz = float(np.sum(yc * zc))
    determinant = sxx * syy - sxy * sxy
    if determinant <= 0:
        raise ValueError("plane-fit input has insufficient spatial variation")
    slope_x = (sxz * syy - syz * sxy) / determinant
    slope_y = (syz * sxx - sxz * sxy) / determinant
    residual = zc - (slope_x * xc + slope_y * yc)
    abs_residual = np.abs(residual)
    if min(values.shape) >= 3:
        curvature = np.concatenate(
            (
                np.diff(values, n=2, axis=0).ravel(),
                np.diff(values, n=2, axis=1).ravel(),
            )
        )
        curvature_indicator = float(np.sqrt(np.mean(curvature**2)))
    else:
        curvature_indicator = 0.0
    return PlaneFitMetrics(
        rmse_m=float(np.sqrt(np.mean(residual**2))),
        max_abs_residual_m=float(abs_residual.max()),
        curvature_indicator_m=curvature_indicator,
        connectivity_feature_present=_connectivity_feature_present(values),
        flow_accumulation_concentration=_flow_accumulation_concentration(values),
    )


def _shift_mask(source: np.ndarray, dy: int, dx: int) -> np.ndarray:
    shifted = np.zeros_like(source, dtype=bool)
    source_y = slice(max(0, -dy), min(source.shape[0], source.shape[0] - dy))
    source_x = slice(max(0, -dx), min(source.shape[1], source.shape[1] - dx))
    target_y = slice(max(0, dy), min(source.shape[0], source.shape[0] + dy))
    target_x = slice(max(0, dx), min(source.shape[1], source.shape[1] + dx))
    shifted[target_y, target_x] = source[source_y, source_x]
    return shifted


def _metric_feature_buffer(
    mask: np.ndarray,
    *,
    dx_m: float,
    dy_m: float,
    distance_m: float = _FEATURE_BUFFER_DISTANCE_M,
) -> np.ndarray:
    """Return source cells whose closed cell footprints are within distance.

    The feature mask is already the normalized 1 m raster representation of a
    building/road footprint. Therefore the precise projected-metric contract is
    evaluated between closed source-cell rectangles, not between cell centres.
    """

    source = np.asarray(mask, dtype=bool)
    if dx_m <= 0 or dy_m <= 0 or distance_m < 0:
        raise ValueError("Adaptive feature-buffer spacing and distance must be valid")
    max_dx = math.ceil(distance_m / dx_m) + 1
    max_dy = math.ceil(distance_m / dy_m) + 1
    result = source.copy()
    tolerance = 1e-12
    for offset_y in range(-max_dy, max_dy + 1):
        for offset_x in range(-max_dx, max_dx + 1):
            gap_x = max(abs(offset_x) * dx_m - dx_m, 0.0)
            gap_y = max(abs(offset_y) * dy_m - dy_m, 0.0)
            if math.hypot(gap_x, gap_y) <= distance_m + tolerance:
                result |= _shift_mask(source, offset_y, offset_x)
    return result


def _block_key(size: int, row: int, col: int) -> str:
    return f"{size}m@{row},{col}"


def _refine_block(
    resolution: np.ndarray,
    reason: np.ndarray,
    row: int,
    col: int,
    size: int,
    label: str,
) -> None:
    next_size = size // 2
    block = resolution[row : row + size, col : col + size]
    if not np.all(block == size):
        return
    block[:] = next_size
    reason[row : row + size, col : col + size] = label


def _balance_two_to_one(resolution: np.ndarray, reason: np.ndarray) -> None:
    """Refine coarse blocks until edge-adjacent raster cells differ by <=2:1."""

    changed = True
    while changed:
        changed = False
        for row in range(resolution.shape[0]):
            for col in range(resolution.shape[1]):
                size = int(resolution[row, col])
                if size <= 1:
                    continue
                neighbours = []
                if row:
                    neighbours.append(int(resolution[row - 1, col]))
                if row + 1 < resolution.shape[0]:
                    neighbours.append(int(resolution[row + 1, col]))
                if col:
                    neighbours.append(int(resolution[row, col - 1]))
                if col + 1 < resolution.shape[1]:
                    neighbours.append(int(resolution[row, col + 1]))
                if not neighbours or size <= 2 * min(neighbours):
                    continue
                top = row - row % size
                left = col - col % size
                before = resolution[top : top + size, left : left + size].copy()
                _refine_block(resolution, reason, top, left, size, "balanced_transition")
                changed |= not np.array_equal(
                    before, resolution[top : top + size, left : left + size]
                )


def _count_cells(resolution: np.ndarray) -> dict[str, int]:
    counts: dict[str, int] = {}
    for size in ADAPTIVE_LEVELS_M:
        area = int(np.count_nonzero(resolution == size))
        if area:
            counts[f"{size}m"] = area // (size * size)
    return counts


def _validate_thresholds(thresholds: AdaptiveThresholds) -> None:
    expected_levels = set(ADAPTIVE_LEVELS_M[1:])
    if set(thresholds.rmse_by_level_m) != expected_levels or set(
        thresholds.max_abs_residual_by_level_m
    ) != expected_levels:
        raise ValueError("Adaptive thresholds must define every coarsening level")
    values = [
        *thresholds.rmse_by_level_m.values(),
        *thresholds.max_abs_residual_by_level_m.values(),
    ]
    if not all(math.isfinite(value) and value >= 0 for value in values):
        raise ValueError("Adaptive thresholds must be finite and non-negative")


def build_adaptive_grid(
    full_grid: FullGridProduct,
    *,
    thresholds: AdaptiveThresholds = DEFAULT_ADAPTIVE_THRESHOLDS,
) -> AdaptiveGridProduct:
    """Classify an existing Full 1 m product into a balanced resolution map.

    Blocks are only coarsened when they are complete aligned blocks. This keeps
    cell counts integral and leaves partial edge blocks at 1 m resolution.
    """

    elevation = np.asarray(full_grid.elevation_m, dtype=np.float32)
    building = np.asarray(full_grid.building_mask, dtype=bool)
    roads = (
        np.zeros_like(building, dtype=bool)
        if full_grid.road_mask is None
        else np.asarray(full_grid.road_mask, dtype=bool)
    )
    if elevation.ndim != 2 or elevation.shape != building.shape or elevation.shape != roads.shape:
        raise ValueError("Full grid terrain and feature masks must have the same 2D shape")
    if not np.isfinite(elevation).all():
        raise ValueError("Adaptive terrain contains non-finite elevations")
    if not math.isclose(full_grid.dx_m, 1.0) or not math.isclose(full_grid.dy_m, 1.0):
        raise ValueError("Adaptive classification requires the canonical Full 1 m source grid")
    _validate_thresholds(thresholds)

    direct_features = building | roads
    feature_buffer = _metric_feature_buffer(
        direct_features,
        dx_m=full_grid.dx_m,
        dy_m=full_grid.dy_m,
    ) & ~direct_features
    resolution = np.ones(elevation.shape, dtype=np.int16)
    reason = np.full(elevation.shape, "terrain_or_edge_refinement", dtype="<U28")
    reason[feature_buffer] = "near_hard_feature"
    reason[roads] = "road"
    reason[building] = "building"
    metrics: dict[str, PlaneFitMetrics] = {}

    for size in reversed(ADAPTIVE_LEVELS_M[1:]):
        for row in range(0, elevation.shape[0] - size + 1, size):
            for col in range(0, elevation.shape[1] - size + 1, size):
                block = elevation[row : row + size, col : col + size]
                metric = fit_plane_metrics(block)
                metrics[_block_key(size, row, col)] = metric
                if not np.all(resolution[row : row + size, col : col + size] == 1):
                    continue
                if direct_features[row : row + size, col : col + size].any():
                    continue
                if feature_buffer[row : row + size, col : col + size].any() and size > 2:
                    continue
                if (
                    metric.rmse_m <= thresholds.rmse_by_level_m[size]
                    and metric.max_abs_residual_m <= thresholds.max_abs_residual_by_level_m[size]
                ):
                    resolution[row : row + size, col : col + size] = size
                    reason[row : row + size, col : col + size] = "terrain_coarsened"

    _balance_two_to_one(resolution, reason)
    counts = _count_cells(resolution)
    total = int(sum(counts.values()))
    full_cells = int(elevation.size)
    return AdaptiveGridProduct(
        resolution_m=resolution,
        level=np.rint(np.log2(resolution)).astype(np.int8),
        refinement_reason=reason,
        plane_fit_metrics=metrics,
        cell_count_by_level=counts,
        total_hydraulic_cells=total,
        full_1m_equivalent_cells=full_cells,
        reduction_ratio=float(total / full_cells) if full_cells else 1.0,
        threshold_identity=thresholds.identity,
    )
