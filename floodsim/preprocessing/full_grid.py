"""Full 1 m hydraulic grid preparation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from rasterio.features import rasterize  # type: ignore[import-untyped]
from rasterio.transform import from_origin  # type: ignore[import-untyped]
from shapely.geometry import LineString, Polygon  # type: ignore[import-untyped]

from floodsim.domain.geometry import AnalysisArea
from floodsim.preprocessing.roof_rainfall import (
    RoofRainAllocation,
    allocate_roof_rainfall,
)
from floodsim.providers.common import local_crs
from floodsim.providers.gsi_elevation import ElevationProduct

GENERAL_MANNING = 0.030
ROAD_MANNING = 0.020


@dataclass(frozen=True)
class FullGridProduct:
    elevation_m: np.ndarray
    building_mask: np.ndarray
    sfincs_mask: np.ndarray
    manning_n: np.ndarray
    rain_weight: np.ndarray
    roof_allocation: RoofRainAllocation
    width_cells: int
    height_cells: int
    dx_m: float
    dy_m: float
    x0_m: float
    y0_m: float
    crs_wkt: str

    @property
    def cell_count(self) -> int:
        return self.width_cells * self.height_cells


def _cell_count(size_m: float) -> int:
    rounded = round(size_m)
    if rounded <= 0 or not math.isclose(size_m, rounded, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("Full 1 m mode requires integer-metre analysis dimensions")
    return rounded


def _cell_center_elevation(product: ElevationProduct, height: int, width: int) -> np.ndarray:
    z = np.asarray(product.z, dtype=np.float32)
    if z.shape == (height, width):
        out = z.copy()
    elif z.shape == (height + 1, width + 1):
        out = 0.25 * (z[:-1, :-1] + z[1:, :-1] + z[:-1, 1:] + z[1:, 1:])
    else:
        raise ValueError(
            f"unexpected elevation shape {z.shape}; expected {(height, width)} or "
            f"{(height + 1, width + 1)}"
        )
    if not np.isfinite(out).all():
        raise ValueError("Full 1 m terrain contains non-finite elevations")
    return out.astype(np.float32, copy=False)


def _polygon_shapes(items: list[np.ndarray]) -> list[tuple[Polygon, int]]:
    shapes: list[tuple[Polygon, int]] = []
    for coords in items:
        points = np.asarray(coords, dtype=float)
        if points.ndim != 2 or points.shape[0] < 3 or points.shape[1] < 2:
            continue
        polygon = Polygon(points[:, :2])
        if polygon.is_valid and not polygon.is_empty and polygon.area > 0:
            shapes.append((polygon, 1))
    return shapes


def _road_shapes(vectors: Any) -> list[tuple[object, int]]:
    shapes: list[tuple[object, int]] = list(_polygon_shapes(list(vectors.road_polygons)))
    for coords in vectors.road_lines:
        points = np.asarray(coords, dtype=float)
        if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] < 2:
            continue
        line = LineString(points[:, :2])
        if not line.is_empty and line.length > 0:
            shapes.append((line, 1))
    return shapes


def _rasterize_local(
    shapes: list[tuple[object, int]],
    *,
    width: int,
    height: int,
    width_m: float,
    height_m: float,
    all_touched: bool,
) -> np.ndarray:
    if not shapes:
        return np.zeros((height, width), dtype=bool)
    transform = from_origin(-width_m / 2.0, height_m / 2.0, 1.0, 1.0)
    north_to_south = rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,
        default_value=1,
        all_touched=all_touched,
        dtype="uint8",
    )
    return np.flipud(north_to_south).astype(bool)


def build_full_1m_grid(
    area: AnalysisArea,
    elevation: ElevationProduct,
    vectors: Any,
) -> FullGridProduct:
    """Create the exact 1 m hydraulic arrays required by the Phase 3 builder."""
    width = _cell_count(area.width_m)
    height = _cell_count(area.height_m)
    terrain = _cell_center_elevation(elevation, height, width)

    building_mask = _rasterize_local(
        _polygon_shapes(list(vectors.buildings)),
        width=width,
        height=height,
        width_m=area.width_m,
        height_m=area.height_m,
        all_touched=True,
    )
    road_mask = _rasterize_local(
        _road_shapes(vectors),
        width=width,
        height=height,
        width_m=area.width_m,
        height_m=area.height_m,
        all_touched=True,
    )

    manning = np.full((height, width), GENERAL_MANNING, dtype=np.float32)
    manning[road_mask & ~building_mask] = ROAD_MANNING

    sfincs_mask = np.ones((height, width), dtype=np.uint8)
    sfincs_mask[0, :] = 3
    sfincs_mask[-1, :] = 3
    sfincs_mask[:, 0] = 3
    sfincs_mask[:, -1] = 3
    sfincs_mask[building_mask] = 0

    allocation = allocate_roof_rainfall(
        building_mask,
        cell_area_m2=1.0,
        max_distance_cells=5,
        tolerance=1e-9,
    )
    crs = local_crs(area)
    return FullGridProduct(
        elevation_m=terrain,
        building_mask=building_mask,
        sfincs_mask=sfincs_mask,
        manning_n=manning,
        rain_weight=allocation.rain_weight.astype(np.float32),
        roof_allocation=allocation,
        width_cells=width,
        height_cells=height,
        dx_m=1.0,
        dy_m=1.0,
        x0_m=-area.width_m / 2.0,
        y0_m=-area.height_m / 2.0,
        crs_wkt=crs.to_wkt(),
    )
