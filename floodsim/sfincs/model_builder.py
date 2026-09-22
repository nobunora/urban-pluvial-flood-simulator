"""HydroMT-SFINCS adapter for the Phase 3 Full 1 m model."""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from pyproj import CRS

from floodsim.domain.rainfall import RainfallTimeSeries
from floodsim.preprocessing.adaptive_grid import AdaptiveGridProduct
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.sfincs.adaptive_quadtree import create_adaptive_quadtree
from floodsim.sfincs.quadtree_writer import write_quadtree_grid_compat
from floodsim.storage.run_store import atomic_write_json

EXPECTED_HYDROMT_SFINCS = "2.0.0rc3"


class ModelBuildError(RuntimeError):
    code = "MODEL_BUILD_FAILED"


@dataclass(frozen=True)
class ModelBuildResult:
    model_dir: Path
    report_path: Path
    report: dict[str, Any]
    adaptive_layout_path: Path | None = None


@contextmanager
def _sfincs_environment() -> Iterator[None]:
    """Hide host variables that collide with lazy rc3 settings loading."""
    debug_values = {
        key: value for key, value in os.environ.items() if key.casefold() == "debug"
    }
    for key in debug_values:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        os.environ.update(debug_values)


def _load_sfincs_model() -> Any:
    try:
        from hydromt_sfincs import SfincsModel  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - environment dependent
        raise ModelBuildError("HydroMT-SFINCS 2.0.0rc3 is unavailable") from exc
    return SfincsModel


def _sfincs_datetime(value: datetime) -> datetime:
    """Return the timezone-naive UTC datetime expected by rc3 NetCDF writers."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


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
    start = _sfincs_datetime(rainfall.start_time)
    times = [
        start + timedelta(seconds=float(value)) for value in rainfall.elapsed_seconds
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
    model.config.set("netamprfile", "sfincs_netampr.nc")
    model.config.set("precipfile", None)
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
        try:
            with _sfincs_environment():
                SfincsModel = _load_sfincs_model()
                model = SfincsModel(root=root, mode="w+", write_gis=False)
                # rc3 defers BaseSettings construction until config data is first
                # accessed, so initialize it while the generic host DEBUG is hidden.
                _ = model.config.data
            # rc3's regular-grid create() requires an integer EPSG during
            # initialization. The normalized providers deliberately use a local
            # AEQD CRS, which has no EPSG code. Initialize with a valid temporary
            # EPSG, then replace every rc3 CRS owner with the canonical AEQD CRS.
            # SfincsGrid.crs checks the instance `epsg` attribute before the
            # Dataset CRS, so clearing only config.epsg leaves the temporary 4326
            # active. Keep config, grid.epsg and crsgeo synchronized explicitly.
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
            model.grid.epsg = None
            model.config.set("epsg", None)
            model.config.set("crsgeo", int(crs.is_geographic))
            if not model.grid.crs.equals(crs):
                raise ModelBuildError(
                    "HydroMT-SFINCS did not retain the normalized model CRS"
                )

            elevation = _raster(grid.elevation_m, grid, "elevtn")
            roughness = _raster(grid.manning_n, grid, "manning")
            model.elevation.create([{"elevation": elevation}])
            model.mask.create()
            model.mask.data["mask"].values[:] = grid.sfincs_mask
            model.roughness.create([{"manning": roughness}])

            duration_seconds = float(rainfall.elapsed_seconds[-1])
            output_interval = derive_output_interval_seconds(duration_seconds)
            start = _sfincs_datetime(rainfall.start_time)
            stop = start + timedelta(seconds=duration_seconds)
            stamp = "%Y%m%d %H%M%S"
            model.config.set("tref", start.strftime(stamp))
            model.config.set("tstart", start.strftime(stamp))
            model.config.set("tstop", stop.strftime(stamp))
            model.config.set("dtmapout", output_interval)
            model.config.set("dtmaxout", duration_seconds)
            model.config.set("dthisout", output_interval)
            model.config.set("outputformat", "net")
            model.config.set("coriolis", 0)
            model.config.set("alpha", 0.75)
            model.config.set("storecumprcp", 0)
            model.config.set("storevel", 1)

            _configure_precipitation(model, _precipitation(rainfall, grid), rainfall)
            model.write()
        except ModelBuildError:
            raise
        except Exception as exc:
            raise ModelBuildError(
                "failed to build Full 1 m HydroMT-SFINCS model"
            ) from exc

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
            "maximum_output_interval_seconds": duration_seconds,
            "cumulative_precipitation_output": False,
            "velocity_output": {"storevel": 1, "variables": ["u", "v"]},
            "numerics": {"alpha": 0.75},
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


ADAPTIVE_SUBGRID_PIXELS = 8
ADAPTIVE_SUBGRID_LEVELS = 10


class AdaptiveSfincsModelBuilder:
    """Build the Phase 4 quadtree + subgrid hydraulic model.

    The classifier decides hydraulic face size, while the original Full 1 m
    terrain and Manning rasters remain the source for HydroMT-SFINCS subgrid
    generation. Rainfall also remains on the canonical 1 m allocation raster,
    preserving the roof-runoff redistribution field independently of quadtree
    face size.
    """

    def __init__(
        self,
        *,
        subgrid_pixels: int = ADAPTIVE_SUBGRID_PIXELS,
        subgrid_levels: int = ADAPTIVE_SUBGRID_LEVELS,
        cache_root: str | Path | None = None,
    ) -> None:
        if subgrid_pixels < 1:
            raise ValueError("subgrid_pixels must be positive")
        if subgrid_levels < 2:
            raise ValueError("subgrid_levels must be at least two")
        self.subgrid_pixels = int(subgrid_pixels)
        self.subgrid_levels = int(subgrid_levels)
        self.cache_root = Path(cache_root) if cache_root is not None else None

    def _subgrid_cache_key(
        self,
        grid: FullGridProduct,
        adaptive: AdaptiveGridProduct,
    ) -> str:
        digest = hashlib.sha256()
        # This key is the identity of the rainfall-independent Adaptive
        # hydraulic model. Geometry belongs in the key even when raster values
        # happen to be byte-identical: quadtree/subgrid coordinates and the
        # face layout depend on the grid origin and transform.
        digest.update(b"adaptive-static-model-v3-source-1m")
        digest.update(str(self.subgrid_pixels).encode())
        digest.update(str(self.subgrid_levels).encode())
        digest.update(grid.crs_wkt.encode("utf-8"))
        for value in (
            grid.width_cells,
            grid.height_cells,
            grid.dx_m,
            grid.dy_m,
            grid.x0_m,
            grid.y0_m,
        ):
            digest.update(repr(value).encode("ascii"))
            digest.update(b"\\0")
        for values in (
            grid.elevation_m,
            grid.manning_n,
            grid.sfincs_mask,
            adaptive.resolution_m,
        ):
            array = np.ascontiguousarray(values)
            digest.update(str(array.shape).encode())
            digest.update(array.dtype.str.encode())
            digest.update(memoryview(array).cast("B"))
        return digest.hexdigest()[:32]

    def build(
        self,
        model_dir: str | Path,
        grid: FullGridProduct,
        adaptive: AdaptiveGridProduct,
        rainfall: RainfallTimeSeries,
    ) -> ModelBuildResult:
        root = Path(model_dir)
        root.mkdir(parents=True, exist_ok=True)
        try:
            with _sfincs_environment():
                SfincsModel = _load_sfincs_model()
                model = SfincsModel(root=root, mode="w+", write_gis=False)
                _ = model.config.data

            quadtree = create_adaptive_quadtree(model, grid, adaptive)

            elevation = _raster(grid.elevation_m, grid, "elevtn")
            roughness = _raster(grid.manning_n, grid, "manning")
            component = getattr(model, "quadtree_subgrid", None)
            if component is None or not hasattr(component, "create"):
                raise ModelBuildError(
                    "HydroMT-SFINCS quadtree subgrid component is incompatible"
                )
            subgrid_cache_hit = False
            cached_subgrid: Path | None = None
            if self.cache_root is not None:
                cache_key = self._subgrid_cache_key(grid, adaptive)
                cached_subgrid = self.cache_root / cache_key / "sfincs_subgrid.nc"
            target_subgrid = root / "sfincs_subgrid.nc"
            if cached_subgrid is not None and cached_subgrid.is_file():
                shutil.copy2(cached_subgrid, target_subgrid)
                model.config.set("sbgfile", target_subgrid.name)
                subgrid_cache_hit = True
            else:
                component.create(
                    elevation_list=[{"elevation": elevation}],
                    roughness_list=[{"manning": roughness}],
                    nr_levels=self.subgrid_levels,
                    nr_subgrid_pixels=self.subgrid_pixels,
                    write_dep_tif=False,
                    write_man_tif=False,
                    quiet=True,
                )
                if not getattr(component.data, "data_vars", None):
                    raise ModelBuildError("Adaptive subgrid generation produced no data")

            duration_seconds = float(rainfall.elapsed_seconds[-1])
            output_interval = derive_output_interval_seconds(duration_seconds)
            start = _sfincs_datetime(rainfall.start_time)
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
            # Match the accepted Full-1 m CFL factor. Leaving Adaptive at the
            # SFINCS default alpha=0.5 unnecessarily shortens every stable
            # timestep versus the Full-1 m model (which explicitly uses 0.75).
            model.config.set("alpha", 0.75)
            model.config.set("storecumprcp", 1)
            model.config.set("storevel", 1)
            # SFINCS suppresses h/hmax on subgrid runs unless this is enabled.
            model.config.set("storehsubgrid", 1)
            # Needed for the Adaptive Full-vs-Adaptive volume validation gate.
            model.config.set("storezvolume", 1)
            # SFINCS reverts a one-level quadtree to regular n/m map output by
            # default. Keep the Adaptive result contract face-native even for
            # open-area benchmarks that need only one quadtree level.
            model.config.set("regular_output_on_mesh", 1)

            # Keep the already mass-conserving 1 m roof-allocation raster as
            # SFINCS distributed precipitation forcing. The meteorological field
            # is uniform; only roof-runoff redistribution varies spatially.
            _configure_precipitation(model, _precipitation(rainfall, grid), rainfall)

            # rc3's normal quadtree writer serializes EPSG=None for the local
            # authority-less AEQD CRS. Use the narrow compatibility writer for
            # the grid, then let upstream components write subgrid/meteo files.
            write_quadtree_grid_compat(model.quadtree_grid, filename="sfincs.nc")
            if not subgrid_cache_hit:
                component.write(filename="sfincs_subgrid.nc")
                if cached_subgrid is not None:
                    cached_subgrid.parent.mkdir(parents=True, exist_ok=True)
                    temp_cache = cached_subgrid.with_suffix(".tmp")
                    shutil.copy2(target_subgrid, temp_cache)
                    os.replace(temp_cache, cached_subgrid)
            model.precipitation.write(filename="sfincs_netampr.nc")
            model.config.write()

            face_rows = (
                np.asarray(model.quadtree_grid.data["n"].values, dtype=np.int32) - 1
            )
            face_cols = (
                np.asarray(model.quadtree_grid.data["m"].values, dtype=np.int32) - 1
            )
            layout_path = root / "adaptive_face_layout.npz"
            np.savez_compressed(
                layout_path,
                resolution_m=quadtree.face_fields.resolution_m.astype(
                    np.int16, copy=False
                ),
                row_index=face_rows,
                col_index=face_cols,
                source_overlap_area_m2=quadtree.face_fields.source_overlap_area_m2,
                sfincs_mask=quadtree.face_fields.sfincs_mask.astype(
                    np.uint8, copy=False
                ),
                source_height_cells=np.int32(grid.height_cells),
                source_width_cells=np.int32(grid.width_cells),
            )
        except ModelBuildError:
            raise
        except Exception as exc:
            raise ModelBuildError(
                "failed to build Adaptive HydroMT-SFINCS quadtree/subgrid model"
            ) from exc

        if subgrid_cache_hit:
            with xr.open_dataset(root / "sfincs_subgrid.nc") as cached_dataset:
                subgrid_variables = sorted(str(name) for name in cached_dataset.data_vars)
        else:
            subgrid_variables = sorted(str(name) for name in component.data.data_vars)

        level_counts = {
            f"{size}m": int(np.count_nonzero(quadtree.face_fields.resolution_m == size))
            for size in (1, 2, 4, 8, 16, 32)
            if np.any(quadtree.face_fields.resolution_m == size)
        }
        active_faces = int(np.count_nonzero(quadtree.face_fields.sfincs_mask))
        outflow_faces = int(np.count_nonzero(quadtree.face_fields.sfincs_mask == 3))
        report = {
            "schema_version": "1",
            "grid_type": "quadtree",
            "cell_counts": level_counts,
            "total_hydraulic_cells": quadtree.face_count,
            "full_1m_equivalent_cells": adaptive.full_1m_equivalent_cells,
            "reduction_ratio": quadtree.face_count / adaptive.full_1m_equivalent_cells,
            "classifier_reduction_ratio": adaptive.reduction_ratio,
            "threshold_identity": adaptive.threshold_identity,
            "classifier_diagnostics": dict(adaptive.diagnostics),
            "model_crs_wkt": grid.crs_wkt,
            "quadtree_base_resolution_m": 32.0,
            "quadtree_padded_width_m": quadtree.padded_width_m,
            "quadtree_padded_height_m": quadtree.padded_height_m,
            "active_cells": active_faces,
            "outflow_boundary_cells": outflow_faces,
            "blocked_building_source_cells": int(np.count_nonzero(grid.building_mask)),
            "roughness": {"general": 0.030, "road": 0.020},
            "subgrid": {
                "cache_hit": subgrid_cache_hit,
                "source_terrain_resolution_m": 1.0,
                "source_roughness_resolution_m": 1.0,
                "pixels_per_hydraulic_cell": self.subgrid_pixels,
                "effective_coarsest_subpixel_m": max(adaptive.active_levels_m) / self.subgrid_pixels,
                "hypsometric_levels": self.subgrid_levels,
                "variables": subgrid_variables,
            },
            "rainfall_forcing": {
                "grid_resolution_m": 1.0,
                "spatial_mode": "uniform_meteorology_with_roof_allocation_weights",
                "weighted_area_m2": quadtree.face_fields.hydraulic_weighted_area_m2,
            },
            "rainfall_volume_before_weight_area_m2": grid.roof_allocation.meteorological_area_m2,
            "rainfall_volume_after_weight_area_m2": grid.roof_allocation.hydraulic_weighted_area_m2,
            "roof_rain_relative_mass_error": grid.roof_allocation.relative_mass_error,
            "output_interval_seconds": output_interval,
            "depth_output": {"storehsubgrid": 1, "variables": ["h", "hmax"]},
            "volume_output": {"storezvolume": 1, "variable": "subgrid_volume"},
            "velocity_output": {"storevel": 1, "variables": ["u", "v"]},
            "mesh_output": {
                "regular_output_on_mesh": 1,
                "face_dimension": "nmesh2d_face",
            },
            "adaptive_face_layout": "adaptive_face_layout.npz",
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
        return ModelBuildResult(root, report_path, report, layout_path)
