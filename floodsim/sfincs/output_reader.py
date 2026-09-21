"""Direct Xarray reader for SFINCS regular-grid NetCDF output."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xarray as xr


class SfincsResultError(RuntimeError):
    code = "RESULT_INVALID"
    retryable = False


@dataclass(frozen=True)
class SfincsRegularResult:
    depth_time_m: np.ndarray
    max_depth_m: np.ndarray
    terrain_elevation_m: np.ndarray
    active_mask: np.ndarray
    time_values: tuple[str, ...]
    velocity_u_mps: np.ndarray | None = None
    velocity_v_mps: np.ndarray | None = None
    subgrid_volume_m3: np.ndarray | None = None
    hmax_reconstructed_cells: int = 0
    negative_depth_clipped_values: int = 0
    negative_max_depth_clipped_cells: int = 0
    min_raw_active_depth_m: float = 0.0
    excluded_boundary_cells: int = 0

    @property
    def global_max_depth_m(self) -> float:
        active_values = self.max_depth_m[self.active_mask]
        return float(active_values.max()) if active_values.size else 0.0

    @property
    def flow_vectors_available(self) -> bool:
        return self.velocity_u_mps is not None and self.velocity_v_mps is not None


def _require_dims(dataset: xr.Dataset, name: str, expected: tuple[str, ...]) -> None:
    if name not in dataset.data_vars:
        raise SfincsResultError(f"SFINCS result is missing {name}")
    if dataset[name].dims != expected:
        raise SfincsResultError(f"unexpected SFINCS dimensions for {name}: {dataset[name].dims}")


def read_regular_result(path: str | Path) -> SfincsRegularResult:
    """Read and normalize SFINCS regular-grid result output."""
    result_path = Path(path)
    if not result_path.is_file():
        raise SfincsResultError("SFINCS result file is missing")
    try:
        with xr.open_dataset(result_path) as dataset:
            _require_dims(dataset, "h", ("time", "n", "m"))
            _require_dims(dataset, "hmax", ("timemax", "n", "m"))
            _require_dims(dataset, "zs", ("time", "n", "m"))
            _require_dims(dataset, "zb", ("n", "m"))
            _require_dims(dataset, "msk", ("n", "m"))

            depth = np.asarray(dataset["h"].values, dtype=np.float32)
            hmax_values = np.asarray(dataset["hmax"].values, dtype=np.float32)
            terrain = np.asarray(dataset["zb"].values, dtype=np.float32)
            mask_values = np.asarray(dataset["msk"].values)

            active = mask_values == 1
            boundary = (mask_values == 2) | (mask_values == 3)

            if hmax_values.shape[0] < 1:
                raise SfincsResultError("SFINCS hmax contains no output frame")
            if depth.shape[1:] != active.shape or hmax_values.shape[1:] != active.shape:
                raise SfincsResultError("SFINCS result grid shapes are inconsistent")
            if terrain.shape != active.shape:
                raise SfincsResultError("SFINCS terrain shape is inconsistent")
            if np.any(~np.isfinite(depth[:, active])):
                raise SfincsResultError("active SFINCS depth cells contain non-finite values")
            if np.any(~np.isfinite(terrain[active])):
                raise SfincsResultError("active SFINCS terrain cells contain non-finite values")

            active_hmax = hmax_values[:, active]
            if np.any(np.isinf(active_hmax)):
                raise SfincsResultError("active SFINCS maximum depth contains infinite values")
            finite_active_hmax = active_hmax[np.isfinite(active_hmax)]
            if np.any(finite_active_hmax < 0.0):
                raise SfincsResultError(
                    "active SFINCS maximum depth contains negative finite values"
                )

            active_depth_values = depth[:, active]
            min_raw_active_depth = (
                float(np.min(active_depth_values)) if active_depth_values.size else 0.0
            )
            negative_depth_clipped_values = int(
                np.count_nonzero(active_depth_values < 0.0)
            )
            depth[:, active] = np.maximum(active_depth_values, 0.0)

            finite_hmax = np.isfinite(hmax_values)
            has_hmax = np.any(finite_hmax, axis=0)
            max_depth = np.full(active.shape, np.nan, dtype=np.float32)
            valid_hmax = active & has_hmax
            if np.any(valid_hmax):
                finite_values = np.where(finite_hmax, hmax_values, -np.inf)
                finite_max = np.max(finite_values, axis=0)
                max_depth[valid_hmax] = finite_max[valid_hmax]

            reconstructed_mask = active & ~has_hmax
            reconstructed_cells = int(np.count_nonzero(reconstructed_mask))
            if reconstructed_cells:
                max_depth[reconstructed_mask] = np.max(
                    depth[:, reconstructed_mask],
                    axis=0,
                )
            if np.any(~np.isfinite(max_depth[active])):
                raise SfincsResultError(
                    "active SFINCS maximum depth could not be reconstructed"
                )

            subgrid_volume: np.ndarray | None = None
            if "subgrid_volume" in dataset.data_vars:
                _require_dims(dataset, "subgrid_volume", ("time", face_dim))
                subgrid_volume = np.asarray(
                    dataset["subgrid_volume"].values,
                    dtype=np.float64,
                )
                if subgrid_volume.shape != depth.shape:
                    raise SfincsResultError(
                        "SFINCS quadtree subgrid-volume face/time shape is inconsistent"
                    )
                if np.any(~np.isfinite(subgrid_volume[:, active])):
                    raise SfincsResultError(
                        "active SFINCS quadtree subgrid volume contains non-finite values"
                    )
                if np.any(subgrid_volume[:, active] < 0.0):
                    raise SfincsResultError(
                        "active SFINCS quadtree subgrid volume contains negative values"
                    )
                subgrid_volume[:, ~active] = np.nan

            has_u = "u" in dataset.data_vars
            has_v = "v" in dataset.data_vars
            if has_u != has_v:
                raise SfincsResultError("SFINCS velocity output must contain both u and v")
            velocity_u: np.ndarray | None = None
            velocity_v: np.ndarray | None = None
            if has_u and has_v:
                _require_dims(dataset, "u", ("time", "n", "m"))
                _require_dims(dataset, "v", ("time", "n", "m"))
                velocity_u = np.asarray(dataset["u"].values, dtype=np.float32)
                velocity_v = np.asarray(dataset["v"].values, dtype=np.float32)
                if velocity_u.shape != depth.shape or velocity_v.shape != depth.shape:
                    raise SfincsResultError("SFINCS velocity grid/time shape is inconsistent")
                wet = active[None, :, :] & (depth > 0.0)
                if np.any(~np.isfinite(velocity_u[wet])) or np.any(~np.isfinite(velocity_v[wet])):
                    raise SfincsResultError("wet SFINCS velocity cells contain non-finite values")
                velocity_u = np.where(wet, velocity_u, 0.0).astype(np.float32, copy=False)
                velocity_v = np.where(wet, velocity_v, 0.0).astype(np.float32, copy=False)
                velocity_u[:, ~active] = np.nan
                velocity_v[:, ~active] = np.nan

            negative_max_depth_clipped_cells = 0
            depth[:, ~active] = np.nan
            max_depth[~active] = np.nan
            terrain[~active] = np.nan
            time_values = tuple(str(value) for value in dataset["time"].values)
            excluded_boundary_cells = int(np.count_nonzero(boundary))
    except SfincsResultError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise SfincsResultError("SFINCS NetCDF result is unreadable") from exc

    return SfincsRegularResult(
        depth_time_m=depth,
        max_depth_m=max_depth.astype(np.float32, copy=False),
        terrain_elevation_m=terrain,
        active_mask=active,
        time_values=time_values,
        velocity_u_mps=velocity_u,
        velocity_v_mps=velocity_v,
        subgrid_volume_m3=subgrid_volume,
        hmax_reconstructed_cells=reconstructed_cells,
        negative_depth_clipped_values=negative_depth_clipped_values,
        negative_max_depth_clipped_cells=negative_max_depth_clipped_cells,
        min_raw_active_depth_m=min_raw_active_depth,
        excluded_boundary_cells=excluded_boundary_cells,
    )



@dataclass(frozen=True)
class AdaptiveFaceLayout:
    """Persisted mapping from SFINCS quadtree face order to the source 1 m grid."""

    resolution_m: np.ndarray
    row_index: np.ndarray
    col_index: np.ndarray
    source_overlap_area_m2: np.ndarray
    sfincs_mask: np.ndarray
    source_height_cells: int
    source_width_cells: int

    @property
    def face_count(self) -> int:
        return int(self.resolution_m.size)


@dataclass(frozen=True)
class SfincsQuadtreeResult:
    """Native face-based SFINCS quadtree output without dense raster expansion."""

    depth_time_m: np.ndarray
    max_depth_m: np.ndarray
    terrain_elevation_m: np.ndarray
    active_mask: np.ndarray
    time_values: tuple[str, ...]
    layout: AdaptiveFaceLayout
    velocity_u_mps: np.ndarray | None = None
    velocity_v_mps: np.ndarray | None = None
    hmax_reconstructed_cells: int = 0
    negative_depth_clipped_values: int = 0
    min_raw_active_depth_m: float = 0.0
    excluded_boundary_cells: int = 0

    @property
    def global_max_depth_m(self) -> float:
        active_values = self.max_depth_m[self.active_mask]
        return float(active_values.max()) if active_values.size else 0.0

    @property
    def flow_vectors_available(self) -> bool:
        return self.velocity_u_mps is not None and self.velocity_v_mps is not None


def read_adaptive_face_layout(path: str | Path) -> AdaptiveFaceLayout:
    source = Path(path)
    if not source.is_file():
        raise SfincsResultError("Adaptive face layout file is missing")
    try:
        with np.load(source, allow_pickle=False) as archive:
            resolution = np.asarray(archive["resolution_m"], dtype=np.int16)
            rows = np.asarray(archive["row_index"], dtype=np.int32)
            cols = np.asarray(archive["col_index"], dtype=np.int32)
            overlap = np.asarray(archive["source_overlap_area_m2"], dtype=np.float64)
            mask = np.asarray(archive["sfincs_mask"], dtype=np.uint8)
            height = int(np.asarray(archive["source_height_cells"]).item())
            width = int(np.asarray(archive["source_width_cells"]).item())
    except (KeyError, OSError, ValueError) as exc:
        raise SfincsResultError("Adaptive face layout file is unreadable") from exc

    if resolution.ndim != 1 or resolution.size == 0:
        raise SfincsResultError("Adaptive face layout has invalid resolution data")
    expected_shape = resolution.shape
    if any(values.shape != expected_shape for values in (rows, cols, overlap, mask)):
        raise SfincsResultError("Adaptive face layout arrays have inconsistent shapes")
    if height <= 0 or width <= 0:
        raise SfincsResultError("Adaptive face layout has invalid source dimensions")
    if np.any(resolution <= 0) or np.any(rows < 0) or np.any(cols < 0):
        raise SfincsResultError("Adaptive face layout contains invalid face indices")
    if np.any(overlap < 0):
        raise SfincsResultError("Adaptive face layout contains negative overlap area")

    coverage = np.zeros((height, width), dtype=np.uint8)
    for index, size_value in enumerate(resolution):
        size = int(size_value)
        row0 = int(rows[index]) * size
        col0 = int(cols[index]) * size
        row1 = min(row0 + size, height)
        col1 = min(col0 + size, width)
        if row0 >= height or col0 >= width or row1 <= row0 or col1 <= col0:
            if overlap[index] != 0.0:
                raise SfincsResultError("Adaptive padding face has non-zero source overlap")
            continue
        coverage[row0:row1, col0:col1] += 1
    if np.any(coverage != 1):
        raise SfincsResultError("Adaptive face layout does not cover the source grid exactly once")

    return AdaptiveFaceLayout(
        resolution_m=resolution,
        row_index=rows,
        col_index=cols,
        source_overlap_area_m2=overlap,
        sfincs_mask=mask,
        source_height_cells=height,
        source_width_cells=width,
    )


def read_quadtree_result(
    path: str | Path,
    *,
    layout_path: str | Path,
) -> SfincsQuadtreeResult:
    """Read SFINCS UGRID/quadtree output in its native face representation."""

    result_path = Path(path)
    if not result_path.is_file():
        raise SfincsResultError("SFINCS result file is missing")
    layout = read_adaptive_face_layout(layout_path)
    face_dim = "nmesh2d_face"

    try:
        with xr.open_dataset(result_path) as dataset:
            _require_dims(dataset, "h", ("time", face_dim))
            _require_dims(dataset, "hmax", ("timemax", face_dim))
            _require_dims(dataset, "zs", ("time", face_dim))
            _require_dims(dataset, "zb", (face_dim,))
            _require_dims(dataset, "msk", (face_dim,))

            depth = np.asarray(dataset["h"].values, dtype=np.float32)
            hmax_values = np.asarray(dataset["hmax"].values, dtype=np.float32)
            terrain = np.asarray(dataset["zb"].values, dtype=np.float32)
            mask_values = np.asarray(dataset["msk"].values, dtype=np.uint8)

            if depth.shape[1] != layout.face_count:
                raise SfincsResultError("SFINCS quadtree face count does not match model layout")
            if hmax_values.shape[1] != layout.face_count or terrain.size != layout.face_count:
                raise SfincsResultError("SFINCS quadtree result shapes are inconsistent")
            if mask_values.shape != layout.sfincs_mask.shape:
                raise SfincsResultError("SFINCS quadtree mask shape is inconsistent")
            if not np.array_equal(mask_values, layout.sfincs_mask):
                raise SfincsResultError("SFINCS quadtree face order/mask changed from the model layout")

            active = mask_values == 1
            boundary = (mask_values == 2) | (mask_values == 3)
            if np.any(~np.isfinite(depth[:, active])):
                raise SfincsResultError("active SFINCS quadtree depth faces contain non-finite values")
            if np.any(~np.isfinite(terrain[active])):
                raise SfincsResultError("active SFINCS quadtree terrain faces contain non-finite values")

            active_hmax = hmax_values[:, active]
            if np.any(np.isinf(active_hmax)):
                raise SfincsResultError("active SFINCS quadtree hmax contains infinite values")
            finite_active_hmax = active_hmax[np.isfinite(active_hmax)]
            if np.any(finite_active_hmax < 0.0):
                raise SfincsResultError(
                    "active SFINCS quadtree hmax contains negative finite values"
                )

            active_depth_values = depth[:, active]
            min_raw_active_depth = (
                float(np.min(active_depth_values)) if active_depth_values.size else 0.0
            )
            negative_depth_clipped_values = int(
                np.count_nonzero(active_depth_values < 0.0)
            )
            depth[:, active] = np.maximum(active_depth_values, 0.0)

            finite_hmax = np.isfinite(hmax_values)
            has_hmax = np.any(finite_hmax, axis=0)
            max_depth = np.full(layout.face_count, np.nan, dtype=np.float32)
            valid_hmax = active & has_hmax
            if np.any(valid_hmax):
                finite_values = np.where(finite_hmax, hmax_values, -np.inf)
                finite_max = np.max(finite_values, axis=0)
                max_depth[valid_hmax] = finite_max[valid_hmax]

            reconstructed_mask = active & ~has_hmax
            reconstructed_cells = int(np.count_nonzero(reconstructed_mask))
            if reconstructed_cells:
                max_depth[reconstructed_mask] = np.max(
                    depth[:, reconstructed_mask],
                    axis=0,
                )
            if np.any(~np.isfinite(max_depth[active])):
                raise SfincsResultError(
                    "active SFINCS quadtree maximum depth could not be reconstructed"
                )

            has_u = "u" in dataset.data_vars
            has_v = "v" in dataset.data_vars
            if has_u != has_v:
                raise SfincsResultError("SFINCS quadtree velocity output must contain both u and v")
            velocity_u: np.ndarray | None = None
            velocity_v: np.ndarray | None = None
            if has_u and has_v:
                _require_dims(dataset, "u", ("time", face_dim))
                _require_dims(dataset, "v", ("time", face_dim))
                velocity_u = np.asarray(dataset["u"].values, dtype=np.float32)
                velocity_v = np.asarray(dataset["v"].values, dtype=np.float32)
                if velocity_u.shape != depth.shape or velocity_v.shape != depth.shape:
                    raise SfincsResultError(
                        "SFINCS quadtree velocity face/time shape is inconsistent"
                    )
                wet = active[None, :] & (depth > 0.0)
                if np.any(~np.isfinite(velocity_u[wet])) or np.any(
                    ~np.isfinite(velocity_v[wet])
                ):
                    raise SfincsResultError(
                        "wet SFINCS quadtree velocity faces contain non-finite values"
                    )
                velocity_u = np.where(wet, velocity_u, 0.0).astype(
                    np.float32, copy=False
                )
                velocity_v = np.where(wet, velocity_v, 0.0).astype(
                    np.float32, copy=False
                )
                velocity_u[:, ~active] = np.nan
                velocity_v[:, ~active] = np.nan

            depth[:, ~active] = np.nan
            max_depth[~active] = np.nan
            terrain[~active] = np.nan
            time_values = tuple(str(value) for value in dataset["time"].values)
            excluded_boundary_cells = int(np.count_nonzero(boundary))
    except SfincsResultError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise SfincsResultError("SFINCS quadtree NetCDF result is unreadable") from exc

    return SfincsQuadtreeResult(
        depth_time_m=depth,
        max_depth_m=max_depth,
        terrain_elevation_m=terrain,
        active_mask=active,
        time_values=time_values,
        layout=layout,
        velocity_u_mps=velocity_u,
        velocity_v_mps=velocity_v,
        hmax_reconstructed_cells=reconstructed_cells,
        negative_depth_clipped_values=negative_depth_clipped_values,
        min_raw_active_depth_m=min_raw_active_depth,
        excluded_boundary_cells=excluded_boundary_cells,
    )
