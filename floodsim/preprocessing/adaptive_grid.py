"""Deterministic terrain-first static Adaptive classification from Full 1 m.

The production policy starts with the canonical Full 1 m raster and only merges
complete aligned blocks when coarsening is proven safe. Dynamic AMR is
explicitly out of scope.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

import numpy as np

from floodsim.preprocessing.full_grid import FullGridProduct

ADAPTIVE_LEVELS_M: Final[tuple[int, ...]] = (1, 2, 4, 8, 16, 32)
PRODUCTION_ADAPTIVE_LEVELS_M: Final[tuple[int, ...]] = (1, 2, 4, 8)
_ADAPTIVE_THRESHOLD_SCHEMA: Final[str] = "adaptive-v2-static-terrain-error"


@dataclass(frozen=True)
class PlaneFitMetrics:
    """Terrain evidence for one candidate coarse hydraulic block."""

    rmse_m: float
    max_abs_residual_m: float
    curvature_indicator_m: float
    elevation_range_m: float
    elevation_std_m: float
    detrended_relief_m: float
    connectivity_feature_present: bool
    flow_accumulation_concentration: float


@dataclass(frozen=True)
class AdaptiveThresholds:
    """Configurable terrain-representation thresholds by candidate cell size."""

    rmse_by_level_m: dict[int, float]
    max_abs_residual_by_level_m: dict[int, float]
    curvature_by_level_m: dict[int, float]
    detrended_relief_by_level_m: dict[int, float]

    @classmethod
    def provisional(cls) -> AdaptiveThresholds:
        return cls(
            rmse_by_level_m={2: 0.03, 4: 0.04, 8: 0.05, 16: 0.06, 32: 0.08},
            max_abs_residual_by_level_m={
                2: 0.10,
                4: 0.12,
                8: 0.15,
                16: 0.20,
                32: 0.25,
            },
            curvature_by_level_m={
                2: 0.08,
                4: 0.08,
                8: 0.08,
                16: 0.10,
                32: 0.12,
            },
            detrended_relief_by_level_m={
                2: 0.18,
                4: 0.22,
                8: 0.28,
                16: 0.36,
                32: 0.45,
            },
        )

    @property
    def identity(self) -> str:
        payload = {
            "schema": _ADAPTIVE_THRESHOLD_SCHEMA,
            "rmse_by_level_m": sorted(
                (int(level), float(value))
                for level, value in self.rmse_by_level_m.items()
            ),
            "max_abs_residual_by_level_m": sorted(
                (int(level), float(value))
                for level, value in self.max_abs_residual_by_level_m.items()
            ),
            "curvature_by_level_m": sorted(
                (int(level), float(value))
                for level, value in self.curvature_by_level_m.items()
            ),
            "detrended_relief_by_level_m": sorted(
                (int(level), float(value))
                for level, value in self.detrended_relief_by_level_m.items()
            ),
        }
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return f"{_ADAPTIVE_THRESHOLD_SCHEMA}:{digest}"


@dataclass(frozen=True)
class AdaptiveGridPolicy:
    """Static Adaptive rules used only when Adaptive mode is enabled."""

    active_levels_m: tuple[int, ...] = PRODUCTION_ADAPTIVE_LEVELS_M
    hard_structure_buffer_m: float = 2.0
    terrain_structure_inner_buffer_m: float = 2.0
    terrain_structure_outer_buffer_m: float = 6.0
    terrain_structure_curvature_threshold_m: float = 0.05
    terrain_structure_min_relief_m: float = 0.05
    target_core_radius_m: float = 100.0
    target_mid_radius_m: float = 250.0
    target_mid_max_resolution_m: int = 2
    connectivity_relief_threshold_m: float = 0.05

    def validate(self) -> None:
        levels = self.active_levels_m
        if not levels or levels[0] != 1:
            raise ValueError("Adaptive policy must start at 1 m")
        if any(level not in ADAPTIVE_LEVELS_M for level in levels):
            raise ValueError("Adaptive policy contains an unsupported resolution")
        if any(right != 2 * left for left, right in pairwise(levels)):
            raise ValueError("Adaptive policy levels must be a contiguous power-of-two series")
        if self.target_mid_max_resolution_m not in levels:
            raise ValueError("target mid-zone resolution must be an active Adaptive level")
        numeric = (
            self.hard_structure_buffer_m,
            self.terrain_structure_inner_buffer_m,
            self.terrain_structure_outer_buffer_m,
            self.terrain_structure_curvature_threshold_m,
            self.terrain_structure_min_relief_m,
            self.target_core_radius_m,
            self.target_mid_radius_m,
            self.connectivity_relief_threshold_m,
        )
        if not all(math.isfinite(value) and value >= 0 for value in numeric):
            raise ValueError("Adaptive policy distances/thresholds must be finite and non-negative")
        if self.target_mid_radius_m < self.target_core_radius_m:
            raise ValueError("target mid radius must be >= target core radius")
        if self.terrain_structure_outer_buffer_m < self.terrain_structure_inner_buffer_m:
            raise ValueError("terrain outer buffer must be >= terrain inner buffer")


DEFAULT_ADAPTIVE_THRESHOLDS: Final[AdaptiveThresholds] = AdaptiveThresholds.provisional()
DEFAULT_ADAPTIVE_GRID_POLICY: Final[AdaptiveGridPolicy] = AdaptiveGridPolicy()
ADAPTIVE_THRESHOLD_IDENTITY: Final[str] = DEFAULT_ADAPTIVE_THRESHOLDS.identity


@dataclass(frozen=True)
class AdaptiveGridProduct:
    """Deterministic Adaptive diagnostics over the Full 1 m source raster."""

    resolution_m: np.ndarray
    level: np.ndarray
    refinement_reason: np.ndarray
    plane_fit_metrics: dict[str, PlaneFitMetrics]
    cell_count_by_level: dict[str, int]
    total_hydraulic_cells: int
    full_1m_equivalent_cells: int
    reduction_ratio: float
    threshold_identity: str
    active_levels_m: tuple[int, ...]
    protection_counts: dict[str, int]
    hard_boundary_preserved: bool

    @property
    def resolution_layer_m(self) -> np.ndarray:
        return self.resolution_m

    @property
    def diagnostics(self) -> dict[str, object]:
        labels, counts = np.unique(self.refinement_reason, return_counts=True)
        return {
            "cell_count_by_level": dict(self.cell_count_by_level),
            "total_hydraulic_cells": self.total_hydraulic_cells,
            "full_1m_equivalent_cells": self.full_1m_equivalent_cells,
            "reduction_ratio": self.reduction_ratio,
            "threshold_identity": self.threshold_identity,
            "active_levels_m": list(self.active_levels_m),
            "minimum_resolution_m": int(np.min(self.resolution_m)),
            "maximum_resolution_m": int(np.max(self.resolution_m)),
            "terrain_protected_cells": self.protection_counts["terrain"],
            "structure_protected_cells": self.protection_counts["structure"],
            "target_protected_cells": self.protection_counts["target"],
            "hard_boundary_cells": self.protection_counts["hard_boundary"],
            "transition_balance_cells": self.protection_counts["transition_balance"],
            "hard_boundary_preserved": self.hard_boundary_preserved,
            "refinement_reason_1m_cells": {
                str(label): int(count) for label, count in zip(labels, counts)
            },
        }


def _connectivity_feature_present(values: np.ndarray) -> bool:
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
    return bool(
        np.any(
            (center < np.min(neighbours, axis=0))
            | (center > np.max(neighbours, axis=0))
        )
    )


def _flow_accumulation_concentration(values: np.ndarray) -> float:
    """Return deterministic D8 peak contributing-area fraction for diagnostics."""

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


def fit_plane_metrics(
    elevation_m: np.ndarray,
    *,
    compute_flow_accumulation: bool = True,
) -> PlaneFitMetrics:
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
        elevation_range_m=float(np.ptp(values)),
        elevation_std_m=float(np.std(values)),
        detrended_relief_m=float(np.ptp(residual)),
        connectivity_feature_present=_connectivity_feature_present(values),
        flow_accumulation_concentration=(
            _flow_accumulation_concentration(values)
            if compute_flow_accumulation
            else 0.0
        ),
    )


def _shift_mask(source: np.ndarray, dy: int, dx: int) -> np.ndarray:
    shifted = np.zeros_like(source, dtype=bool)
    height, width = source.shape
    source_y0 = max(0, -dy)
    source_y1 = min(height, height - dy)
    source_x0 = max(0, -dx)
    source_x1 = min(width, width - dx)
    if source_y0 >= source_y1 or source_x0 >= source_x1:
        return shifted

    target_y0 = source_y0 + dy
    target_y1 = source_y1 + dy
    target_x0 = source_x0 + dx
    target_x1 = source_x1 + dx
    shifted[target_y0:target_y1, target_x0:target_x1] = source[
        source_y0:source_y1,
        source_x0:source_x1,
    ]
    return shifted


def _metric_feature_buffer(
    mask: np.ndarray,
    *,
    dx_m: float,
    dy_m: float,
    distance_m: float,
) -> np.ndarray:
    """Return source cells whose closed footprints are within a metric distance."""

    source = np.asarray(mask, dtype=bool)
    if dx_m <= 0 or dy_m <= 0 or distance_m < 0:
        raise ValueError("Adaptive feature-buffer spacing and distance must be valid")
    if distance_m == 0:
        return source.copy()

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


def _terrain_structure_mask(
    elevation: np.ndarray,
    *,
    curvature_threshold_m: float,
    min_relief_m: float,
) -> np.ndarray:
    """Protect depressions/ridges/steps without penalising a uniform steep plane."""

    values = np.asarray(elevation, dtype=np.float64)
    padded = np.pad(values, 1, mode="edge")
    center = padded[1:-1, 1:-1]
    north = padded[:-2, 1:-1]
    south = padded[2:, 1:-1]
    west = padded[1:-1, :-2]
    east = padded[1:-1, 2:]

    curvature = np.maximum(
        np.abs(west - 2.0 * center + east),
        np.abs(north - 2.0 * center + south),
    )

    neighbours = np.stack(
        [
            padded[dy : dy + values.shape[0], dx : dx + values.shape[1]]
            for dy in range(3)
            for dx in range(3)
            if (dy, dx) != (1, 1)
        ]
    )
    neighbour_delta = np.max(np.abs(neighbours - center), axis=0)
    local_extrema = (
        (center < np.min(neighbours, axis=0))
        | (center > np.max(neighbours, axis=0))
    ) & (neighbour_delta >= min_relief_m)

    structure = (curvature >= curvature_threshold_m) | local_extrema
    # The analysis-domain edge is not itself terrain evidence. Edge padding
    # would otherwise create false curvature on a perfectly planar slope.
    if structure.shape[0] > 1:
        structure[0, :] = False
        structure[-1, :] = False
    if structure.shape[1] > 1:
        structure[:, 0] = False
        structure[:, -1] = False
    return structure


def _target_ceiling(
    shape: tuple[int, int],
    policy: AdaptiveGridPolicy,
) -> tuple[np.ndarray, np.ndarray]:
    max_resolution = max(policy.active_levels_m)
    ceiling = np.full(shape, max_resolution, dtype=np.int16)
    protected = np.zeros(shape, dtype=bool)
    yy, xx = np.indices(shape, dtype=np.float64)
    x_m = xx + 0.5 - shape[1] / 2.0
    y_m = yy + 0.5 - shape[0] / 2.0
    radius = np.hypot(x_m, y_m)

    if policy.target_mid_radius_m > 0:
        mid = radius <= policy.target_mid_radius_m
        ceiling[mid] = np.minimum(
            ceiling[mid],
            np.int16(policy.target_mid_max_resolution_m),
        )
        protected |= mid
    if policy.target_core_radius_m > 0:
        core = radius <= policy.target_core_radius_m
        ceiling[core] = 1
        protected |= core
    return ceiling, protected


def _hard_boundary_cells(zones: np.ndarray) -> np.ndarray:
    boundary = np.zeros(zones.shape, dtype=bool)
    if zones.size == 0:
        return boundary
    vertical = zones[:, 1:] != zones[:, :-1]
    horizontal = zones[1:, :] != zones[:-1, :]
    boundary[:, 1:] |= vertical
    boundary[:, :-1] |= vertical
    boundary[1:, :] |= horizontal
    boundary[:-1, :] |= horizontal
    return boundary


def _apply_ceiling(
    ceiling: np.ndarray,
    reason: np.ndarray,
    mask: np.ndarray,
    max_resolution_m: int,
    label: str,
) -> None:
    update = mask & (ceiling > max_resolution_m)
    ceiling[update] = max_resolution_m
    reason[update] = label


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


def _balance_two_to_one(resolution: np.ndarray, reason: np.ndarray) -> int:
    """Refine only the coarse side until every edge adjacency satisfies 2:1."""

    changed = True
    changed_cells = np.zeros(resolution.shape, dtype=bool)
    while changed:
        changed = False
        for row in range(resolution.shape[0]):
            for col in range(resolution.shape[1]):
                size = int(resolution[row, col])
                if size <= 1:
                    continue
                neighbours: list[int] = []
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
                _refine_block(
                    resolution,
                    reason,
                    top,
                    left,
                    size,
                    "balanced_transition",
                )
                if not np.array_equal(
                    before,
                    resolution[top : top + size, left : left + size],
                ):
                    changed = True
                    changed_cells[top : top + size, left : left + size] = True
    return int(np.count_nonzero(changed_cells))


def _count_cells(
    resolution: np.ndarray,
    active_levels_m: tuple[int, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for size in active_levels_m:
        area = int(np.count_nonzero(resolution == size))
        counts[f"{size}m"] = area // (size * size)
    return counts


def _validate_thresholds(
    thresholds: AdaptiveThresholds,
    active_levels_m: tuple[int, ...],
) -> None:
    expected = set(active_levels_m[1:])
    mappings = (
        thresholds.rmse_by_level_m,
        thresholds.max_abs_residual_by_level_m,
        thresholds.curvature_by_level_m,
        thresholds.detrended_relief_by_level_m,
    )
    for mapping in mappings:
        if not expected.issubset(mapping):
            raise ValueError("Adaptive thresholds must define every active coarsening level")
        values = [mapping[level] for level in expected]
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError("Adaptive thresholds must be finite and non-negative")


def _validate_input_array(
    array: np.ndarray | None,
    *,
    shape: tuple[int, int],
    name: str,
) -> np.ndarray | None:
    if array is None:
        return None
    value = np.asarray(array)
    if value.shape != shape:
        raise ValueError(f"{name} must match the Full 1 m grid shape")
    return value


def _validate_resolution_map(
    resolution: np.ndarray,
    *,
    active_levels_m: tuple[int, ...],
    ceiling: np.ndarray,
    hard_boundary_zone: np.ndarray,
) -> None:
    values = {int(value) for value in np.unique(resolution)}
    if not values.issubset(set(active_levels_m)):
        raise ValueError("Adaptive result contains an inactive resolution level")
    if np.any(resolution > ceiling):
        raise ValueError("Adaptive result violates a protected resolution ceiling")

    vertical_a = resolution[:, 1:]
    vertical_b = resolution[:, :-1]
    horizontal_a = resolution[1:, :]
    horizontal_b = resolution[:-1, :]
    if np.any(np.maximum(vertical_a, vertical_b) > 2 * np.minimum(vertical_a, vertical_b)):
        raise ValueError("Adaptive result violates vertical 2:1 balance")
    if np.any(
        np.maximum(horizontal_a, horizontal_b)
        > 2 * np.minimum(horizontal_a, horizontal_b)
    ):
        raise ValueError("Adaptive result violates horizontal 2:1 balance")

    visited: set[tuple[int, int, int]] = set()
    for row in range(resolution.shape[0]):
        for col in range(resolution.shape[1]):
            size = int(resolution[row, col])
            top = row - row % size
            left = col - col % size
            key = (top, left, size)
            if key in visited:
                continue
            visited.add(key)
            block = resolution[top : top + size, left : left + size]
            if block.shape != (size, size) or not np.all(block == size):
                raise ValueError("Adaptive result contains a partial/misaligned coarse block")
            zones = hard_boundary_zone[top : top + size, left : left + size]
            if np.any(zones != zones.flat[0]):
                raise ValueError("Adaptive coarse block crosses a registered hard boundary")


def build_adaptive_grid(
    full_grid: FullGridProduct,
    *,
    thresholds: AdaptiveThresholds = DEFAULT_ADAPTIVE_THRESHOLDS,
    policy: AdaptiveGridPolicy = DEFAULT_ADAPTIVE_GRID_POLICY,
    hard_boundary_zone: np.ndarray | None = None,
    existing_resolution_ceiling_m: np.ndarray | None = None,
    native_structure_mask: np.ndarray | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> AdaptiveGridProduct:
    """Coarsen Full 1 m to successive power-of-two levels only when safe.

    hard_boundary_zone registers immutable pre-existing boundary positions. A
    coarse cell is never allowed to span two zone IDs. The optional existing
    resolution ceiling expresses the coarsest resolution already permitted at
    each source cell; balancing may refine it further but never make it coarser.
    """

    policy.validate()
    _validate_thresholds(thresholds, policy.active_levels_m)

    def emit(fraction: float, detail: str) -> None:
        if progress_callback is not None:
            progress_callback(fraction, detail)

    emit(0.02, "Adaptive分類: 入力格子と保護条件を検証中")

    elevation = np.asarray(full_grid.elevation_m, dtype=np.float32)
    building = np.asarray(full_grid.building_mask, dtype=bool)
    roads = (
        np.zeros_like(building, dtype=bool)
        if full_grid.road_mask is None
        else np.asarray(full_grid.road_mask, dtype=bool)
    )
    shape = elevation.shape
    if elevation.ndim != 2 or building.shape != shape or roads.shape != shape:
        raise ValueError("Full grid terrain and feature masks must share one 2D shape")
    if not np.isfinite(elevation).all():
        raise ValueError("Adaptive terrain contains non-finite elevations")
    if not math.isclose(full_grid.dx_m, 1.0) or not math.isclose(full_grid.dy_m, 1.0):
        raise ValueError("Adaptive classification requires the canonical Full 1 m source grid")

    zones_value = _validate_input_array(
        hard_boundary_zone,
        shape=shape,
        name="hard_boundary_zone",
    )
    zones = (
        np.zeros(shape, dtype=np.int32)
        if zones_value is None
        else np.asarray(zones_value, dtype=np.int32)
    )
    ceiling_input = _validate_input_array(
        existing_resolution_ceiling_m,
        shape=shape,
        name="existing_resolution_ceiling_m",
    )
    native_input = _validate_input_array(
        native_structure_mask,
        shape=shape,
        name="native_structure_mask",
    )
    native = (
        np.zeros(shape, dtype=bool)
        if native_input is None
        else np.asarray(native_input, dtype=bool)
    )

    max_resolution = max(policy.active_levels_m)
    ceiling = np.full(shape, max_resolution, dtype=np.int16)
    if ceiling_input is not None:
        external = np.asarray(ceiling_input, dtype=np.int16)
        permitted = set(policy.active_levels_m)
        if not {int(value) for value in np.unique(external)}.issubset(permitted):
            raise ValueError("existing resolution ceiling contains an inactive level")
        ceiling = np.minimum(ceiling, external)

    resolution = np.ones(shape, dtype=np.int16)
    reason = np.full(shape, "terrain_pending", dtype="<U32")

    emit(0.10, "Adaptive分類: 建物・道路の保護領域を作成中")
    direct_structure = building | roads | native
    structure_buffer = _metric_feature_buffer(
        direct_structure,
        dx_m=full_grid.dx_m,
        dy_m=full_grid.dy_m,
        distance_m=policy.hard_structure_buffer_m,
    ) & ~direct_structure
    _apply_ceiling(ceiling, reason, structure_buffer, 2, "near_hard_structure")
    _apply_ceiling(ceiling, reason, native, 1, "native_structure")
    _apply_ceiling(ceiling, reason, roads, 1, "road")
    _apply_ceiling(ceiling, reason, building, 1, "building")

    emit(0.25, "Adaptive分類: 地形の段差・尾根・窪地を抽出中")
    terrain_structure = _terrain_structure_mask(
        elevation,
        curvature_threshold_m=policy.terrain_structure_curvature_threshold_m,
        min_relief_m=policy.terrain_structure_min_relief_m,
    )
    terrain_inner = _metric_feature_buffer(
        terrain_structure,
        dx_m=full_grid.dx_m,
        dy_m=full_grid.dy_m,
        distance_m=policy.terrain_structure_inner_buffer_m,
    )
    terrain_outer = _metric_feature_buffer(
        terrain_structure,
        dx_m=full_grid.dx_m,
        dy_m=full_grid.dy_m,
        distance_m=policy.terrain_structure_outer_buffer_m,
    )
    _apply_ceiling(ceiling, reason, terrain_outer, min(4, max_resolution), "terrain_buffer")
    _apply_ceiling(ceiling, reason, terrain_inner, min(2, max_resolution), "terrain_near")
    _apply_ceiling(ceiling, reason, terrain_structure, 1, "terrain_structure")

    emit(0.40, "Adaptive分類: 地形・対象地点の解像度上限を統合中")
    target_limits, target_protected = _target_ceiling(shape, policy)
    target_core = target_limits == 1
    target_mid = target_protected & ~target_core
    _apply_ceiling(
        ceiling,
        reason,
        target_mid,
        policy.target_mid_max_resolution_m,
        "target_mid",
    )
    _apply_ceiling(ceiling, reason, target_core, 1, "target_core")

    hard_boundary_cells = _hard_boundary_cells(zones)
    metrics: dict[str, PlaneFitMetrics] = {}

    # Required direction: begin everywhere at 1 m, then merge complete blocks
    # successively into 2 m, 4 m and 8 m or later configured extension levels.
    candidate_total = sum(
        len(range(0, shape[0] - size + 1, size))
        * len(range(0, shape[1] - size + 1, size))
        for size in policy.active_levels_m[1:]
    )
    candidate_done = 0
    last_progress_at = time.monotonic()
    for size in policy.active_levels_m[1:]:
        child_size = size // 2
        emit(
            0.45 + 0.40 * candidate_done / max(1, candidate_total),
            f"Adaptive分類: {size} m候補ブロックを評価中",
        )
        for row in range(0, shape[0] - size + 1, size):
            for col in range(0, shape[1] - size + 1, size):
                candidate_done += 1
                now = time.monotonic()
                if now - last_progress_at >= 8.0:
                    emit(
                        0.45 + 0.40 * candidate_done / max(1, candidate_total),
                        f"Adaptive分類: {size} m候補 {candidate_done:,}/{candidate_total:,} を評価済み",
                    )
                    last_progress_at = now
                row_slice = slice(row, row + size)
                col_slice = slice(col, col + size)
                current = resolution[row_slice, col_slice]
                if not np.all(current == child_size):
                    continue
                if np.any(ceiling[row_slice, col_slice] < size):
                    continue
                zone_block = zones[row_slice, col_slice]
                if np.any(zone_block != zone_block.flat[0]):
                    continue

                block = elevation[row_slice, col_slice]
                # D8 flow accumulation is diagnostic-only and is not part of
                # the coarsening decision. Computing it for tens of thousands
                # of candidate blocks dominated Adaptive classification time.
                metric = fit_plane_metrics(block, compute_flow_accumulation=False)
                metrics[_block_key(size, row, col)] = metric
                safe = (
                    metric.rmse_m <= thresholds.rmse_by_level_m[size]
                    and metric.max_abs_residual_m
                    <= thresholds.max_abs_residual_by_level_m[size]
                    and metric.curvature_indicator_m
                    <= thresholds.curvature_by_level_m[size]
                    and metric.detrended_relief_m
                    <= thresholds.detrended_relief_by_level_m[size]
                    and not (
                        metric.connectivity_feature_present
                        and metric.detrended_relief_m
                        >= policy.connectivity_relief_threshold_m
                    )
                )
                if safe:
                    resolution[row_slice, col_slice] = size
                    reason[row_slice, col_slice] = "terrain_coarsened"

    emit(0.87, "Adaptive分類: 隣接格子の2:1整合を確認中")
    balanced_cells = _balance_two_to_one(resolution, reason)
    emit(0.94, "Adaptive分類: 解像度マップと境界保持を検証中")
    _validate_resolution_map(
        resolution,
        active_levels_m=policy.active_levels_m,
        ceiling=ceiling,
        hard_boundary_zone=zones,
    )

    counts = _count_cells(resolution, policy.active_levels_m)
    total = int(sum(counts.values()))
    full_cells = int(elevation.size)
    emit(1.0, "Adaptive分類: 完了")
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
        active_levels_m=policy.active_levels_m,
        protection_counts={
            "terrain": int(np.count_nonzero(terrain_outer)),
            "structure": int(np.count_nonzero(direct_structure | structure_buffer)),
            "target": int(np.count_nonzero(target_protected)),
            "hard_boundary": int(np.count_nonzero(hard_boundary_cells)),
            "transition_balance": balanced_cells,
        },
        hard_boundary_preserved=True,
    )
