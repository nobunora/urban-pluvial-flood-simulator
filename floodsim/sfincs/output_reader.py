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

    @property
    def global_max_depth_m(self) -> float:
        active_values = self.max_depth_m[self.active_mask]
        return float(active_values.max()) if active_values.size else 0.0


def _require_dims(dataset: xr.Dataset, name: str, expected: tuple[str, ...]) -> None:
    if name not in dataset.data_vars:
        raise SfincsResultError(f"SFINCS result is missing {name}")
    if dataset[name].dims != expected:
        raise SfincsResultError(f"unexpected SFINCS dimensions for {name}: {dataset[name].dims}")


def read_regular_result(path: str | Path) -> SfincsRegularResult:
    """Read the regular-grid result contract proven during Phase 0."""
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
            active = mask_values > 0

            if hmax_values.shape[0] < 1:
                raise SfincsResultError("SFINCS hmax contains no output frame")
            max_depth = np.nanmax(hmax_values, axis=0)
            if depth.shape[1:] != active.shape or max_depth.shape != active.shape:
                raise SfincsResultError("SFINCS result grid shapes are inconsistent")
            if terrain.shape != active.shape:
                raise SfincsResultError("SFINCS terrain shape is inconsistent")
            if np.any(~np.isfinite(depth[:, active])):
                raise SfincsResultError("active SFINCS depth cells contain non-finite values")
            if np.any(~np.isfinite(max_depth[active])):
                raise SfincsResultError("active SFINCS maximum depth contains non-finite values")
            if np.any(~np.isfinite(terrain[active])):
                raise SfincsResultError("active SFINCS terrain cells contain non-finite values")
            if np.any(depth[:, active] < -1e-6) or np.any(max_depth[active] < -1e-6):
                raise SfincsResultError("SFINCS result contains materially negative water depth")

            depth[:, ~active] = np.nan
            max_depth[~active] = np.nan
            terrain[~active] = np.nan
            time_values = tuple(str(value) for value in dataset["time"].values)
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
    )
