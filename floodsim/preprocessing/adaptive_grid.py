"""Accuracy-first Adaptive grid classification on the Full 1 m source grid.

This module deliberately stops at a deterministic, inspectable resolution map.
The SFINCS quadtree writer is kept separate so classification can be tested
without enabling the Adaptive run path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from floodsim.preprocessing.full_grid import FullGridProduct

ADAPTIVE_LEVELS_M: Final[tuple[int, ...]] = (1, 2, 4, 8, 16, 32)
ADAPTIVE_THRESHOLD_IDENTITY: Final[str] = "adaptive-v1-rmse-max-residual"


@dataclass(frozen=True)
class PlaneFitMetrics:
    """Terrain complexity metrics for one candidate hydraulic block."""

    rmse_m: float
    max_abs_residual_m: float
    curvature_indicator_m: float


@dataclass(frozen=True)
class AdaptiveThresholds:
    """Provisional thresholds from the v0.1 Adaptive specification."""

    rmse_by_level_m: dict[int, float]
    max_abs_residual_by_level_m: dict[int, float]
    identity: str = ADAPTIVE_THRESHOLD_IDENTITY

    @classmethod
    def provisional(cls) -> AdaptiveThresholds:
        return cls(
            rmse_by_level_m={2: 0.03, 4: 0.04, 8: 0.05, 16: 0.06, 32: 0.08},
            max_abs_residual_by_level_m={2: 0.10, 4: 0.12, 8: 0.15, 16: 0.20, 32: 0.25},
        )


DEFAULT_ADAPTIVE_THRESHOLDS: Final[AdaptiveThresholds] = AdaptiveThresholds.provisional()


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


def fit_plane_metrics(elevation_m: np.ndarray) -> PlaneFitMetrics:
    """Fit a plane and summarize residual complexity for a candidate block."""

    values = np.asarray(elevation_m, dtype=float)
    if values.ndim != 2 or min(values.shape) < 2:
        raise ValueError("plane-fit input must be a two-dimensional block")
    if not np.isfinite(values).all():
        raise ValueError("plane-fit input contains non-finite elevation")
    yy, xx = np.indices(values.shape, dtype=float)
    # Centered two-variable least squares avoids a BLAS-backed generic solve;
    # this keeps the small classifier reliable in the pinned Windows runtime.
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
    )


def _expand(mask: np.ndarray, radius: int = 2) -> np.ndarray:
    """Dilate a hard feature mask using metric-aligned Chebyshev cells."""

    source = np.asarray(mask, dtype=bool)
    result = source.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dy == 0 and dx == 0:
                continue
            source_y = slice(max(0, -dy), min(source.shape[0], source.shape[0] - dy))
            source_x = slice(max(0, -dx), min(source.shape[1], source.shape[1] - dx))
            target_y = slice(max(0, dy), min(source.shape[0], source.shape[0] + dy))
            target_x = slice(max(0, dx), min(source.shape[1], source.shape[1] + dx))
            result[target_y, target_x] |= source[source_y, source_x]
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
                neighbors = []
                if row:
                    neighbors.append(int(resolution[row - 1, col]))
                if row + 1 < resolution.shape[0]:
                    neighbors.append(int(resolution[row + 1, col]))
                if col:
                    neighbors.append(int(resolution[row, col - 1]))
                if col + 1 < resolution.shape[1]:
                    neighbors.append(int(resolution[row, col + 1]))
                if not neighbors or size <= 2 * min(neighbors):
                    continue
                top = row - row % size
                left = col - col % size
                before = resolution[top : top + size, left : left + size].copy()
                _refine_block(resolution, reason, top, left, size, "balanced_transition")
                changed |= not np.array_equal(before, resolution[top : top + size, left : left + size])


def _count_cells(resolution: np.ndarray) -> dict[str, int]:
    counts: dict[str, int] = {}
    for size in ADAPTIVE_LEVELS_M:
        area = int(np.count_nonzero(resolution == size))
        if area:
            counts[f"{size}m"] = area // (size * size)
    return counts


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
    expected_threshold_levels = set(ADAPTIVE_LEVELS_M[1:])
    if set(thresholds.rmse_by_level_m) != expected_threshold_levels or set(
        thresholds.max_abs_residual_by_level_m
    ) != expected_threshold_levels:
        raise ValueError("Adaptive thresholds must define every coarsening level")

    direct_features = building | roads
    hard = _expand(direct_features, radius=2)
    resolution = np.ones(elevation.shape, dtype=np.int16)
    reason = np.full(elevation.shape, "terrain_or_edge_refinement", dtype="<U28")
    reason[hard & ~direct_features] = "near_hard_feature"
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
                if hard[row : row + size, col : col + size].any():
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
