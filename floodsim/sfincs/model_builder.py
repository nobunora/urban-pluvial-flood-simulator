"""HydroMT-SFINCS adapter for the Phase 3 Full 1 m model."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from pyproj import CRS

from floodsim.domain.rainfall import RainfallTimeSeries
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.storage.run_store import atomic_write_json

EXPECTED_HYDROMT_SFINCS = "2.0.0rc3"


class ModelBuildError(RuntimeError):
    code = "MODEL_BUILD_FAILED"


@dataclass(frozen=True)
class ModelBuildResult:
    model_dir: Path
    report_path: Path
    report: dict[str, Any]


def _load_sfincs_model() -> Any:
    debug = os.environ.get("DEBUG")
    restore_debug = debug is not None and not debug.isdigit()
    if restore_debug:
        os.environ.pop("DEBUG", None)
    try:
        from hydromt_sfincs import SfincsModel
    except Exception as exc:  # pragma: no cover - environment dependent
        raise ModelBuildError("HydroMT-SFINCS 2.0.0rc3 is unavailable") from exc
    finally:
        if restore_debug:
            os.environ["DEBUG"] = debug
    return SfincsModel


def _raster(values: np.ndarray, grid: FullGridProduct, name: str) -> xr.DataArray:
    x = grid.x0_m + 0.5 + np.arange(grid.width_cells, dtype=float)
    y = grid.y0_m + 0.5 + np.arange(grid.height_cells, dtype=float)
    data = xr.DataArray(values, dims=("y", "x"), coords={"x": x, "y": y}, name=name)
    data.raster.set_crs(CRS.from_wkt(grid.crs_wkt))
    data.raster.set_nodata(-9999)
    return data


def _precipitation(
    rainfall: RainfallTimeSeries,
    grid: FullGridProduct,
) -> xr.DataArray:
    if len(rainfall.elapsed_seconds) < 2:
        raise ModelBuildError("rainfall time series requires start and stop samples")
    times = [
        rainfall.start_time + timedelta(seconds=float(value))
        for value in rainfall.elapsed_seconds
    ]
    rates = np.asarray(rainfall.intensity_mm_per_h, dtype=np.float32)
    values = rates[:, None, None] * grid.rain_weight[None, :, :]
    x = grid.x0_m + 0.5 + np.arange(grid.width_cells, dtype=float)
    y = grid.y0_m + 0.5 + np.arange(grid.height_cells, dtype=float)
    data = xr.DataArray(
        values,
        dims=("time", "y", "x"),
        coords={"time": times, "x": x, "y": y},
        name="precip_2d",
        attrs={"units": "mm/hr"},
    )
    data.raster.set_crs(CRS.from_wkt(grid.crs_wkt))
    data.raster.set_nodata(-9999)
    return data


def _configure_precipitation(
    model: Any,
    precip: xr.DataArray,
    rainfall: RainfallTimeSeries,
) -> None:
    """Set already-normalized gridded rainfall without re-entering DataCatalog."""
    component = getattr(model, "precipitation", None)
    if component is None or not hasattr(component, "set"):
        raise ModelBuildError("HydroMT-SFINCS precipitation component is incompatible")
    component.set(precip, name="precip_2d")
    interval = float(rainfall.elapsed_seconds[1] - rainfall.elapsed_seconds[0])
    if interval <= 0:
        raise ModelBuildError("rainfall forcing interval must be positive")
    model.config.set("dtwnd", min(1800.0, interval))


def derive_output_interval_seconds(duration_seconds: float) -> int:
    """Return a whole-minute output interval bounded by the v0.1 contract."""
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    raw = max(60.0, duration_seconds / 119.0)
    minutes = int(np.ceil(raw / 60.0))
    return min(900, max(60, minutes * 60))


class SfincsModelBuilder:
    """Build only the regular Full 1 m v0.1 hydraulic model."""

    def build(
        self,
        model_dir: str | Path,
        grid: FullGridProduct,
        rainfall: RainfallTimeSeries,
    ) -> ModelBuildResult:
        root = Path(model_dir)
        root.mkdir(parents=True, exist_ok=True)
        SfincsModel = _load_sfincs_model()
        model = SfincsModel(root=root, mode="w+", write_gis=False)
        try:
            # rc3's regular-grid create() requires an integer EPSG during
            # initialization. The normalized providers deliberately use a local
            # AEQD CRS, which has no EPSG code. Initialize with a valid temporary
            # EPSG, immediately replace the Dataset CRS with the canonical AEQD
            # WKT, then clear the config EPSG. With epsg=None, rc3's grid.crs
            # property uses the Dataset CRS and SFINCS itself does not require a
            # persisted EPSG code for the hydraulic calculation.
            model.grid.create(
                x0=grid.x0_m,
                y0=grid.y0_m,
                dx=1.0,
                dy=1.0,
                nmax=grid.height_cells,
                mmax=grid.width_cells,
                rotation=0,
                epsg=4326,
            )
            crs = CRS.from_wkt(grid.crs_wkt)
            model.grid.data.raster.set_crs(crs)
            model.config.set("epsg", None)
            if not model.grid.crs.equals(crs):
                raise ModelBuildError("HydroMT-SFINCS did not retain the normalized model CRS")

            elevation = _raster(grid.elevation_m, grid, "elevtn")
            roughness = _raster(grid.manning_n, grid, "manning")
            model.elevation.create([{"elevation": elevation}])
            model.mask.create()
            model.mask.data["mask"].values[:] = grid.sfincs_mask
            model.roughness.create([{"manning": roughness}])

            duration_seconds = float(rainfall.elapsed_seconds[-1])
            output_interval = derive_output_interval_seconds(duration_seconds)
            start = rainfall.start_time
            stop = start + timedelta(seconds=duration_seconds)
            stamp = "%Y%m%d %H%M%S"
            model.config.set("tref", start.strftime(stamp))
            model.config.set("tstart", start.strftime(stamp))
            model.config.set("tstop", stop.strftime(stamp))
            model.config.set("dtmapout", output_interval)
            model.config.set("dtmaxout", output_interval)
            model.config.set("dthisout", output_interval)
            model.config.set("outputformat", "net")
            model.config.set("coriolis", 0)
            model.config.set("storecumprcp", 1)

            _configure_precipitation(model, _precipitation(rainfall, grid), rainfall)
            model.write()
        except ModelBuildError:
            raise
        except Exception as exc:
            raise ModelBuildError("failed to build Full 1 m HydroMT-SFINCS model") from exc

        report = {
            "schema_version": "1",
            "grid_type": "regular",
            "grid_resolution_m": 1.0,
            "cell_counts": {"1m": grid.cell_count},
            "model_crs_wkt": grid.crs_wkt,
            "active_cells": int(np.count_nonzero(grid.sfincs_mask)),
            "blocked_building_cells": int(np.count_nonzero(grid.building_mask)),
            "outflow_boundary_cells": int(np.count_nonzero(grid.sfincs_mask == 3)),
            "roughness": {"general": 0.030, "road": 0.020},
            "rainfall_volume_before_weight_area_m2": grid.roof_allocation.meteorological_area_m2,
            "rainfall_volume_after_weight_area_m2": grid.roof_allocation.hydraulic_weighted_area_m2,
            "roof_rain_relative_mass_error": grid.roof_allocation.relative_mass_error,
            "output_interval_seconds": output_interval,
            "unsupported_physics": {
                "infiltration": False,
                "sewer_drainage": False,
                "water_level_boundary": False,
                "tide": False,
                "wind_waves": False,
                "river_inflow": False,
                "building_interior_storage": False,
            },
            "warnings": [],
        }
        report_path = root / "model_build_report.json"
        atomic_write_json(report_path, report)
        return ModelBuildResult(root, report_path, report)
