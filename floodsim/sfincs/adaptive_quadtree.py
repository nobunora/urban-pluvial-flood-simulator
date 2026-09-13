"""Build the validated Adaptive classifier into the pinned rc3 quadtree geometry.

This module owns the first model-facing Adaptive slice only:

- retain polygonized classifier geometry for diagnostics;
- create the actual quadtree from a 32 m base with pinned-rc3 staged refinement;
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
from shapely.geometry import (  # type: ignore[import-untyped]
    MultiPolygon,
    Polygon,
    shape,
)

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
    refined_parent_count: int = 0


def _validate_inputs(full_grid: FullGridProduct, adaptive: AdaptiveGridProduct) -> None:
    expected_shape = (full_grid.height_cells, full_grid.width_cells)
    if adaptive.resolution_m.shape != expected_shape:
        raise AdaptiveQuadtreeError("Adaptive resolution raster does not match Full 1 m grid")
    if full_grid.elevation_m.shape != expected_shape:
        raise AdaptiveQuadtreeError("Full 1 m terrain shape is inconsistent")
    if not math.isclose(full_grid.dx_m, 1.0) or not math.isclose(full_grid.dy_m, 1.0):
        raise AdaptiveQuadtreeError("Adaptive quadtree requires the canonical Full 1 m source grid")
    values = {int(value) for value in np.unique(adaptive.resolution_m)}
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
    """Polygonize exact classifier targets for diagnostics and audit output.

    The pinned rc3 ``refine_in_polygon`` implementation restarts at level zero
    for every polygon. With several target levels this can reference a level
    whose cells were completely consumed by an earlier polygon. The production
    quadtree therefore uses the staged cell refinement path below instead of
    passing these polygons back into rc3. Keeping the polygonization here makes
    the classifier geometry independently inspectable.
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
        refinement_level = round(math.log2(_BASE_CELL_M / target_size))
        for mapping, value in shapes(
            north_to_south,
            mask=north_to_south.astype(bool),
            transform=transform,
        ):
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


def _load_rc3_quadtree_grid_class() -> Any:
    try:
        from hydromt_sfincs.components.quadtree.quadtree_builder import (  # type: ignore[import-untyped]
            QuadtreeGrid,
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        raise AdaptiveQuadtreeError("pinned rc3 quadtree builder is unavailable") from exc
    return QuadtreeGrid


def _normalize_empty_leading_levels(builder: Any) -> int:
    """Rebase the rc3 hierarchy after all globally coarser levels disappear.

    rc3's ``refine_cells`` asks the immediately coarser level for 2:1-neighbor
    candidates whenever ``ilev > 0``. If the entire domain has already been
    refined past that level, rc3's binary search receives an empty array and
    raises ``IndexError`` even though no coarser neighbor can exist. The
    quadtree is physically unchanged if the first populated level is promoted
    to level zero while ``dx/dy`` and ``nmax/mmax`` are scaled by the matching
    power of two. ``n/m`` indices and all cell coordinates remain identical.
    """

    levels = np.asarray(builder.level, dtype=np.int64)
    if levels.size == 0:
        raise AdaptiveQuadtreeError("rc3 staged quadtree contains no cells")
    leading = int(levels.min())
    if leading <= 0:
        return 0

    factor = 2**leading
    builder.dx = float(builder.dx) / factor
    builder.dy = float(builder.dy) / factor
    builder.nmax = int(builder.nmax) * factor
    builder.mmax = int(builder.mmax) * factor
    builder.level = levels - leading
    builder.nr_refinement_levels = int(builder.nr_refinement_levels) - leading
    if builder.nr_refinement_levels <= 0:
        raise AdaptiveQuadtreeError("rc3 staged quadtree lost its refinement hierarchy")
    builder.reorder()
    builder.find_first_cells_in_level()
    builder.compute_cell_center_coordinates()
    return leading


def _level_for_physical_size(builder: Any, size_m: int) -> int | None:
    """Return the current rc3 level corresponding to one physical cell size."""

    base_dx = float(builder.dx)
    base_dy = float(builder.dy)
    if not math.isclose(base_dx, base_dy, rel_tol=0.0, abs_tol=1e-12):
        raise AdaptiveQuadtreeError("Adaptive rc3 quadtree requires square cells")
    if size_m > base_dx + 1e-12:
        return None
    ratio = base_dx / float(size_m)
    ilev = round(math.log2(ratio))
    if ilev < 0 or not math.isclose(ratio, float(2**ilev), rel_tol=0.0, abs_tol=1e-12):
        raise AdaptiveQuadtreeError("rc3 staged base is not aligned to the Adaptive hierarchy")
    return ilev


def _cells_needing_refinement(
    builder: Any,
    *,
    ilev: int,
    size_m: int,
    full_grid: FullGridProduct,
    adaptive: AdaptiveGridProduct,
) -> np.ndarray:
    """Return existing rc3 cells at ``ilev`` that are coarser than source targets."""

    desired = np.asarray(adaptive.resolution_m, dtype=np.int16)
    indices = np.flatnonzero(np.asarray(builder.level, dtype=np.int64) == ilev)
    if indices.size == 0:
        return np.empty(0, dtype=np.int64)

    selected: list[int] = []
    for raw_index in indices:
        index = int(raw_index)
        row0 = int(builder.n[index]) * size_m
        col0 = int(builder.m[index]) * size_m
        row1 = min(row0 + size_m, full_grid.height_cells)
        col1 = min(col0 + size_m, full_grid.width_cells)
        if row0 >= full_grid.height_cells or col0 >= full_grid.width_cells:
            continue
        if row1 <= row0 or col1 <= col0:
            continue
        if np.any(desired[row0:row1, col0:col1] < size_m):
            selected.append(index)
    return np.asarray(selected, dtype=np.int64)


def _assert_contiguous_populated_levels(builder: Any) -> None:
    """Reject an internal level gap that would violate rc3's 2:1 topology contract."""

    levels = np.asarray(builder.level, dtype=np.int64)
    if levels.size == 0:
        raise AdaptiveQuadtreeError("rc3 staged quadtree contains no cells")
    present = {int(value) for value in np.unique(levels)}
    expected = set(range(int(levels.max()) + 1))
    if present != expected:
        raise AdaptiveQuadtreeError("rc3 staged refinement produced an internal empty level")


def _build_staged_rc3_quadtree(
    full_grid: FullGridProduct,
    adaptive: AdaptiveGridProduct,
    *,
    base_nmax: int,
    base_mmax: int,
) -> tuple[Any, int]:
    """Build through rc3 internals while preserving its adjacent-level contract.

    Production never calls rc3 ``refine_in_polygon``. Each physical parent size
    is refined monotonically. Whenever all globally coarser cells disappear,
    the hierarchy is rebased to the first populated level before the next
    ``refine_cells`` call. This is a geometry-preserving equivalence transform
    that prevents rc3 from searching an empty immediately-coarser level.
    """

    QuadtreeGrid = _load_rc3_quadtree_grid_class()
    builder = QuadtreeGrid()
    builder.build(
        full_grid.x0_m,
        full_grid.y0_m,
        base_nmax,
        base_mmax,
        float(_BASE_CELL_M),
        float(_BASE_CELL_M),
        0.0,
        CRS.from_epsg(_TEMPORARY_CREATION_EPSG),
        None,
        elevation_list=[],
        bathymetry_database=None,
    )

    refined_parent_count = 0
    for parent_size in (32, 16, 8, 4, 2):
        while True:
            _normalize_empty_leading_levels(builder)
            ilev = _level_for_physical_size(builder, parent_size)
            if ilev is None or ilev >= int(builder.nr_refinement_levels):
                break
            levels = np.asarray(builder.level, dtype=np.int64)
            if ilev > 0 and not np.any(levels == ilev - 1):
                raise AdaptiveQuadtreeError(
                    "rc3 staged refinement encountered a non-contiguous coarser level"
                )
            indices = _cells_needing_refinement(
                builder,
                ilev=ilev,
                size_m=parent_size,
                full_grid=full_grid,
                adaptive=adaptive,
            )
            if indices.size == 0:
                break
            before_cells = int(builder.nr_cells)
            builder.refine_cells(indices, ilev)
            refined_parent_count += int(indices.size)
            if int(builder.nr_cells) <= before_cells:
                raise AdaptiveQuadtreeError("rc3 staged refinement made no forward progress")

    _normalize_empty_leading_levels(builder)
    _assert_contiguous_populated_levels(builder)
    builder.nr_refinement_levels = int(np.max(builder.level)) + 1
    builder.reorder()
    builder.find_first_cells_in_level()
    builder.compute_cell_center_coordinates()
    builder.initialize_data_arrays()
    builder.get_neighbors()
    builder.get_uv_points()
    builder.to_xugrid()
    if builder.data is None:
        raise AdaptiveQuadtreeError("rc3 staged builder did not produce a UGRID Dataset")
    return builder, refined_parent_count


def _install_builder_dataset(model: Any, component: Any, builder: Any) -> None:
    """Install staged rc3 builder output using rc3 create() post-processing semantics."""

    overlay = getattr(component, "_overlay", None)
    if overlay is not None and hasattr(overlay, "invalidate"):
        overlay.invalidate()
    quadtree_mask = getattr(model, "quadtree_mask", None)
    if quadtree_mask is not None and hasattr(quadtree_mask, "clear_overlay"):
        quadtree_mask.clear_overlay()

    model._grid_type = "quadtree"
    dataset = xu.UgridDataset(builder.data.ugrid.to_dataset())
    dataset.grid.set_crs(CRS.from_epsg(_TEMPORARY_CREATION_EPSG), allow_override=True)
    component._data = dataset


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
    if np.any(levels < 1):
        raise AdaptiveQuadtreeError("rc3 quadtree refinement level is invalid")

    try:
        base_dx = float(data.attrs["dx"])
        base_dy = float(data.attrs["dy"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AdaptiveQuadtreeError("rc3 quadtree is missing valid base spacing") from exc
    if not math.isclose(base_dx, base_dy, rel_tol=0.0, abs_tol=1e-12):
        raise AdaptiveQuadtreeError("rc3 quadtree base spacing is not square")

    resolution_float = base_dx / (2.0 ** (levels - 1))
    resolution = np.rint(resolution_float).astype(np.int16)
    if not np.allclose(resolution_float, resolution, rtol=0.0, atol=1e-12):
        raise AdaptiveQuadtreeError("rc3 quadtree face resolution is not integral metres")
    if not {int(value) for value in np.unique(resolution)}.issubset(set(ADAPTIVE_LEVELS_M)):
        raise AdaptiveQuadtreeError("rc3 quadtree face resolution is outside the Adaptive hierarchy")
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
    diagnostic_polygons = build_refinement_polygons(full_grid, adaptive)
    base_nmax = math.ceil(full_grid.height_cells / _BASE_CELL_M)
    base_mmax = math.ceil(full_grid.width_cells / _BASE_CELL_M)

    component = model.quadtree_grid
    builder, refined_parent_count = _build_staged_rc3_quadtree(
        full_grid,
        adaptive,
        base_nmax=base_nmax,
        base_mmax=base_mmax,
    )
    _install_builder_dataset(model, component, builder)

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
        refinement_polygon_count=0 if diagnostic_polygons is None else len(diagnostic_polygons),
        face_count=len(fields.resolution_m),
        face_fields=fields,
        refined_parent_count=refined_parent_count,
    )