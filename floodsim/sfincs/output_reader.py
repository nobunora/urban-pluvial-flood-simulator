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
        hmax_reconstructed_cells=reconstructed_cells,
        negative_depth_clipped_values=negative_depth_clipped_values,
        negative_max_depth_clipped_cells=negative_max_depth_clipped_cells,
        min_raw_active_depth_m=min_raw_active_depth,
        excluded_boundary_cells=excluded_boundary_cells,
    )
