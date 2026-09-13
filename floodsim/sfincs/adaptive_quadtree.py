"""Build the validated Adaptive classifier into the pinned rc3 quadtree geometry.

This module owns the first model-facing Adaptive slice only:

- convert the 1/2/4/8/16/32 m classifier raster into rc3 refinement polygons;
- create the actual quadtree from a 32 m base grid;
- replace the temporary creation CRS with the canonical authority-less local CRS;
- map Full 1 m mask/Manning values to quadtree faces;
- aggregate roof-rain weights by face area while preserving total rainfall mass.

Subgrid creation, Adaptive precipitation forcing, result normalization and API enablement
remain separate later slices.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import geopandas as gpd  # type: ignore[import-untyped]
import numpy as np
import xarray as xr
import xugrid as xu  # type: ignore[import-untyped]
from pyproj import CRS
from rasterio.features import shapes  # type: ignore[import-untyped]
from rasterio.transform import from_origin  # type: ignore[import-untyped]
from shapely.geometry import MultiPolygon, Polygon, shape  # type: ignore[import-untyped]

from floodsim.preprocessing.adaptive_grid import ADAPTIVE_LEVELS_M, AdaptiveGridProduct
from floodsim.preprocessing.full_grid import GENERAL_MANNING, FullGridProduct

_BASE_CELL_M: Final[int] = 32
_TEMPORARY_CREATION_EPSG: Final[int] = 3857
_BOUNDARY_SHRINK_M: Final[float] = 1e-7


class AdaptiveQuadtreeError(RuntimeError):
    """Raised when the classifier cannot be represented safely by the rc3 quadtree."""


@dataclass(frozen=True)
class AdaptiveFaceFields:
    """Full-1 m fields aggregated onto the actual quadtree faces."""

    resolution_m: np.ndarray
    source_overlap_area_m2: np.ndarray
    sfincs_mask: np.ndarray
    manning_n: np.ndarray
    rain_weight: np.ndarray

    @property
    def hydraulic_weighted_area_m2(self) -> float:
        area = self.resolution_m.astype(np.float64) ** 2
        return float(np.sum(self.rain_weight.astype(np.float64) * area))


@dataclass(frozen=True)
class AdaptiveQuadtreeBuild:
    """Diagnostics for the created rc3 quadtree geometry."""

    base_nmax: int
    base_mmax: int
    padded_width_m: float
    padded_height_m: float
    refinement_polygon_count: int
    face_count: int
    face_fields: AdaptiveFaceFields


def _validate_inputs(full_grid: FullGridProduct, adaptive: AdaptiveGridProduct) -> None:
    expected_shape = (full_grid.height_cells, full_grid.width_cells)
    if adaptive.resolution_m.shape != expected_shape:
        raise AdaptiveQuadtreeError("Adaptive resolution raster does not match Full 1 m grid")
    if full_grid.elevation_m.shape != expected_shape:
        raise AdaptiveQuadtreeError("Full 1 m terrain shape is inconsistent")
    if not math.isclose(full_grid.dx_m, 1.0) or not math.isclose(full_grid.dy_m, 1.0):
        raise AdaptiveQuadtreeError("Adaptive quadtree requires the canonical Full 1 m source grid")
    values = set(int(value) for value in np.unique(adaptive.resolution_m))
    if not values.issubset(set(ADAPTIVE_LEVELS_M)):
        raise AdaptiveQuadtreeError("Adaptive resolution raster contains an unsupported level")
    if full_grid.width_cells <= 0 or full_grid.height_cells <= 0:
        raise AdaptiveQuadtreeError("Adaptive quadtree requires a non-empty analysis grid")


def _iter_polygons(geometry: Any) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    return []


def build_refinement_polygons(
    full_grid: FullGridProduct,
    adaptive: AdaptiveGridProduct,
) -> gpd.GeoDataFrame | None:
    """Translate exact classifier target cells to pinned-rc3 refinement polygons.

    rc3 uses polygon/cell *intersection* rather than centre containment. Polygons are
    therefore contracted by an insignificant projected epsilon so a boundary shared
    with a neighbouring coarse cell does not spuriously refine that neighbour.
    """

    _validate_inputs(full_grid, adaptive)
    transform = from_origin(
        full_grid.x0_m,
        full_grid.y0_m + full_grid.height_cells * full_grid.dy_m,
        full_grid.dx_m,
        full_grid.dy_m,
    )
    records: list[dict[str, object]] = []

    for target_size in (16, 8, 4, 2, 1):
        mask = adaptive.resolution_m == target_size
        if not np.any(mask):
            continue
        north_to_south = np.flipud(mask).astype(np.uint8)
        refinement_level = int(round(math.log2(_BASE_CELL_M / target_size)))
        for mapping, value in shapes(north_to_south, mask=north_to_south.astype(bool), transform=transform):
            if int(value) != 1:
                continue
            geometry = shape(mapping).buffer(-_BOUNDARY_SHRINK_M)
            if geometry.is_empty:
                continue
            for polygon in _iter_polygons(geometry):
                if not polygon.is_empty and polygon.area > 0:
                    records.append(
                        {
                            "geometry": polygon,
                            "refinement_level": refinement_level,
                        }
                    )

    if not records:
        return None
    crs = CRS.from_wkt(full_grid.crs_wkt)
    return gpd.GeoDataFrame(records, geometry="geometry", crs=crs)


def _face_layout(component: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    data = component.data
    required = ("level", "n", "m")
    if any(name not in data for name in required):
        raise AdaptiveQuadtreeError("rc3 quadtree is missing level/n/m face indexing")

    levels = np.asarray(data["level"].values, dtype=np.int64)
    rows = np.asarray(data["n"].values, dtype=np.int64) - 1
    cols = np.asarray(data["m"].values, dtype=np.int64) - 1
    if levels.ndim != 1 or rows.shape != levels.shape or cols.shape != levels.shape:
        raise AdaptiveQuadtreeError("rc3 quadtree face indexing has an unexpected shape")
    if np.any(levels < 1) or np.any(levels > 6):
        raise AdaptiveQuadtreeError("rc3 quadtree refinement level is outside the 32 m to 1 m hierarchy")
    resolution = (_BASE_CELL_M // (2 ** (levels - 1))).astype(np.int16)
    return resolution, rows, cols


def aggregate_face_fields(
    component: Any,
    full_grid: FullGridProduct,
    adaptive: AdaptiveGridProduct,
) -> AdaptiveFaceFields:
    """Aggregate Full 1 m hydraulic fields to the actual rc3 quadtree faces."""

    _validate_inputs(full_grid, adaptive)
    resolution, rows, cols = _face_layout(component)
    face_count = len(resolution)
    overlap_area = np.zeros(face_count, dtype=np.float64)
    mask = np.zeros(face_count, dtype=np.uint8)
    manning = np.full(face_count, GENERAL_MANNING, dtype=np.float32)
    rain_weight = np.zeros(face_count, dtype=np.float32)

    full_mask = np.asarray(full_grid.sfincs_mask, dtype=np.uint8)
    full_manning = np.asarray(full_grid.manning_n, dtype=np.float32)
    full_rain = np.asarray(full_grid.rain_weight, dtype=np.float64)
    desired = np.asarray(adaptive.resolution_m, dtype=np.int16)
    source_shapes = {array.shape for array in (full_mask, full_manning, full_rain, desired)}
    if source_shapes != {(full_grid.height_cells, full_grid.width_cells)}:
        raise AdaptiveQuadtreeError("Full 1 m source fields do not share one grid shape")

    for index, size_value in enumerate(resolution):
        size = int(size_value)
        row0 = int(rows[index]) * size
        col0 = int(cols[index]) * size
        row1 = min(row0 + size, full_grid.height_cells)
        col1 = min(col0 + size, full_grid.width_cells)
        if row0 >= full_grid.height_cells or col0 >= full_grid.width_cells or row1 <= row0 or col1 <= col0:
            continue

        target_block = desired[row0:row1, col0:col1]
        if np.any(size > target_block):
            raise AdaptiveQuadtreeError(
                "rc3 quadtree produced a face coarser than the validated Adaptive target"
            )

        block_mask = full_mask[row0:row1, col0:col1]
        block_manning = full_manning[row0:row1, col0:col1]
        block_rain = full_rain[row0:row1, col0:col1]
        source_area = float((row1 - row0) * (col1 - col0))
        face_area = float(size * size)
        overlap_area[index] = source_area

        if np.any(block_mask == 3):
            mask[index] = 3
        elif np.any(block_mask != 0):
            mask[index] = 1

        active = block_mask != 0
        if np.any(active):
            manning[index] = np.float32(np.mean(block_manning[active], dtype=np.float64))
        rain_weight[index] = np.float32(np.sum(block_rain, dtype=np.float64) / face_area)

    fields = AdaptiveFaceFields(
        resolution_m=resolution,
        source_overlap_area_m2=overlap_area,
        sfincs_mask=mask,
        manning_n=manning,
        rain_weight=rain_weight,
    )
    expected_area = float(np.sum(full_grid.rain_weight, dtype=np.float64))
    if not math.isclose(
        fields.hydraulic_weighted_area_m2,
        expected_area,
        rel_tol=0.0,
        abs_tol=max(1e-9, abs(expected_area) * 1e-9),
    ):
        raise AdaptiveQuadtreeError("Adaptive face rain-weight aggregation does not conserve area")
    return fields


def attach_face_fields(component: Any, fields: AdaptiveFaceFields) -> None:
    """Attach SFINCS mask and Manning arrays to the rc3 quadtree component."""

    grid = component.data.grid
    face_dim = grid.face_dimension
    expected_faces = int(component.data.sizes[face_dim])
    if len(fields.sfincs_mask) != expected_faces:
        raise AdaptiveQuadtreeError("Adaptive face field count does not match the quadtree")
    component.data["mask"] = xu.UgridDataArray(
        xr.DataArray(fields.sfincs_mask, dims=[face_dim]),
        grid,
    )
    component.data["manning"] = xu.UgridDataArray(
        xr.DataArray(fields.manning_n, dims=[face_dim]),
        grid,
    )


def create_adaptive_quadtree(
    model: Any,
    full_grid: FullGridProduct,
    adaptive: AdaptiveGridProduct,
) -> AdaptiveQuadtreeBuild:
    """Create the actual pinned-rc3 quadtree and map normalized face fields."""

    _validate_inputs(full_grid, adaptive)
    refinement_polygons = build_refinement_polygons(full_grid, adaptive)
    base_nmax = math.ceil(full_grid.height_cells / _BASE_CELL_M)
    base_mmax = math.ceil(full_grid.width_cells / _BASE_CELL_M)

    component = model.quadtree_grid
    component.create(
        x0=full_grid.x0_m,
        y0=full_grid.y0_m,
        nmax=base_nmax,
        mmax=base_mmax,
        dx=float(_BASE_CELL_M),
        dy=float(_BASE_CELL_M),
        rotation=0.0,
        epsg=_TEMPORARY_CREATION_EPSG,
        refinement_polygons=refinement_polygons,
    )

    crs = CRS.from_wkt(full_grid.crs_wkt)
    component.data.grid.set_crs(crs, allow_override=True)
    model.config.set("epsg", None)
    model.config.set("crsgeo", int(crs.is_geographic))
    if not component.crs.equals(crs) or component.crs.to_epsg() is not None:
        raise AdaptiveQuadtreeError("rc3 quadtree did not retain the canonical authority-less CRS")

    fields = aggregate_face_fields(component, full_grid, adaptive)
    attach_face_fields(component, fields)
    return AdaptiveQuadtreeBuild(
        base_nmax=base_nmax,
        base_mmax=base_mmax,
        padded_width_m=float(base_mmax * _BASE_CELL_M),
        padded_height_m=float(base_nmax * _BASE_CELL_M),
        refinement_polygon_count=0 if refinement_polygons is None else len(refinement_polygons),
        face_count=len(fields.resolution_m),
        face_fields=fields,
    )
