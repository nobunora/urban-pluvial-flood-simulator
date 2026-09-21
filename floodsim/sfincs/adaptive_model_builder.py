"""Build the Phase 4 Adaptive quadtree/subgrid SFINCS model.

This module stops deliberately at the model/engine boundary. It creates a
quadtree + subgrid model that the already-pinned native SFINCS executable can
consume, but it does not enable Adaptive through the public run API. Face-based
result normalization and the Full-vs-Adaptive acceptance benchmark remain
separate gates.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import numpy as np
from pyproj import CRS

from floodsim.domain.rainfall import RainfallTimeSeries
from floodsim.preprocessing.adaptive_grid import AdaptiveGridProduct
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.sfincs.adaptive_quadtree import AdaptiveQuadtreeBuild, create_adaptive_quadtree
from floodsim.sfincs.model_builder import (
    ModelBuildError,
    ModelBuildResult,
    _configure_precipitation,
    _load_sfincs_model,
    _precipitation,
    _raster,
    _sfincs_datetime,
    _sfincs_environment,
    derive_output_interval_seconds,
)
from floodsim.sfincs.quadtree_writer import write_quadtree_grid_compat
from floodsim.storage.run_store import atomic_write_json

ADAPTIVE_SUBGRID_PIXELS: Final[int] = 2
ADAPTIVE_SUBGRID_NRMAX: Final[int] = 2000


def _configure_adaptive_timing(model: Any, rainfall: RainfallTimeSeries) -> int:
    """Apply the same v0.1 timing/output contract as the regular builder."""
    if len(rainfall.elapsed_seconds) < 2:
        raise ModelBuildError("rainfall time series requires start and stop samples")
    duration_seconds = float(rainfall.elapsed_seconds[-1])
    if duration_seconds <= 0:
        raise ModelBuildError("rainfall duration must be positive")

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
    model.config.set("storecumprcp", 1)
    model.config.set("storevel", 1)
    return output_interval


def _cell_counts(build: AdaptiveQuadtreeBuild) -> dict[str, int]:
    counts = Counter(int(value) for value in build.face_fields.resolution_m)
    return {f"{level}m": int(counts.get(level, 0)) for level in (1, 2, 4, 8, 16, 32)}


def _require_written(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ModelBuildError(f"Adaptive model did not write {label}")


class SfincsAdaptiveModelBuilder:
    """Create an Adaptive model without changing the pinned SFINCS binary."""

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
                # Force lazy rc3 settings construction while the host DEBUG
                # collision is hidden, matching the regular production builder.
                _ = model.config.data

            quadtree = create_adaptive_quadtree(model, grid, adaptive)
            model_crs = CRS.from_wkt(grid.crs_wkt)
            if not model.quadtree_grid.crs.equals(model_crs):
                raise ModelBuildError(
                    "Adaptive quadtree CRS does not match the normalized source grid"
                )

            # Preserve the best available 1 m terrain and the existing v0.1
            # Manning field as subgrid source information. Coarse hydraulic
            # cells therefore do not imply coarse source topography.
            elevation = _raster(grid.elevation_m, grid, "elevtn")
            roughness = _raster(grid.manning_n, grid, "manning")
            model.quadtree_subgrid.create(
                [{"elevation": elevation}],
                [{"manning": roughness}],
                nr_subgrid_pixels=ADAPTIVE_SUBGRID_PIXELS,
                nrmax=ADAPTIVE_SUBGRID_NRMAX,
                write_dep_tif=False,
                write_man_tif=False,
                quiet=True,
            )
            if not model.quadtree_subgrid.data.data_vars:
                raise ModelBuildError(
                    "Adaptive subgrid generation produced no variables"
                )

            output_interval = _configure_adaptive_timing(model, rainfall)

            # SFINCS distributed precipitation remains on the normalized 1 m
            # meteorological raster. This retains the mass-conserving roof
            # redistribution exactly instead of re-inventing a face forcing
            # convention. The quadtree face rain weights remain diagnostics for
            # conservation checks and later browser/result metadata.
            _configure_precipitation(
                model,
                _precipitation(rainfall, grid),
                rainfall,
            )

            # Do not call model.write(): pinned rc3's ordinary quadtree writer
            # serializes invalid EPSG:None metadata for the authority-less AEQD
            # CRS. Write only the populated components, using the proven seam.
            quadtree_path = write_quadtree_grid_compat(model.quadtree_grid)
            model.quadtree_subgrid.write()
            model.precipitation.write()
            model.config.write()

            subgrid_path = model.config.get("sbgfile", abs_path=True)
            precip_path = model.config.get("netamprfile", abs_path=True)
            if subgrid_path is None or precip_path is None:
                raise ModelBuildError(
                    "Adaptive model config is missing required input files"
                )
            subgrid_path = Path(subgrid_path)
            precip_path = Path(precip_path)
            config_path = root / "sfincs.inp"

            _require_written(Path(quadtree_path), "quadtree grid")
            _require_written(subgrid_path, "subgrid table")
            _require_written(precip_path, "distributed precipitation")
            _require_written(config_path, "sfincs.inp")
        except ModelBuildError:
            raise
        except Exception as exc:
            raise ModelBuildError(
                "failed to build Adaptive HydroMT-SFINCS model"
            ) from exc

        counts = _cell_counts(quadtree)
        full_equivalent = int(grid.cell_count)
        adaptive_cells = int(quadtree.face_count)
        reduction_ratio = (
            0.0
            if full_equivalent <= 0
            else 1.0 - (float(adaptive_cells) / float(full_equivalent))
        )
        report: dict[str, Any] = {
            "schema_version": "1",
            "grid_type": "quadtree",
            "accuracy_mode": "adaptive",
            "cell_counts": counts,
            "hydraulic_cells": adaptive_cells,
            "full_1m_equivalent_cells": full_equivalent,
            "cell_reduction_ratio": reduction_ratio,
            "refined_parent_count": int(quadtree.refined_parent_count),
            "refinement_polygon_count": int(quadtree.refinement_polygon_count),
            "threshold_config_identity": adaptive.threshold_config_identity,
            "model_crs_wkt": grid.crs_wkt,
            "padded_extent_m": {
                "width": quadtree.padded_width_m,
                "height": quadtree.padded_height_m,
            },
            "subgrid": {
                "source_terrain_resolution_m": 1.0,
                "source_roughness_resolution_m": 1.0,
                "nr_subgrid_pixels": ADAPTIVE_SUBGRID_PIXELS,
                "nrmax": ADAPTIVE_SUBGRID_NRMAX,
                "variables": sorted(
                    str(name) for name in model.quadtree_subgrid.data.data_vars
                ),
            },
            "rainfall_forcing": {
                "mode": "distributed_regular_raster",
                "source_resolution_m": 1.0,
                "roof_redistribution_applied": True,
                "face_weighted_area_m2": (
                    quadtree.face_fields.hydraulic_weighted_area_m2
                ),
            },
            "rainfall_volume_before_weight_area_m2": (
                grid.roof_allocation.meteorological_area_m2
            ),
            "rainfall_volume_after_weight_area_m2": (
                grid.roof_allocation.hydraulic_weighted_area_m2
            ),
            "roof_rain_relative_mass_error": grid.roof_allocation.relative_mass_error,
            "output_interval_seconds": output_interval,
            "velocity_output": {"storevel": 1, "variables": ["u", "v"]},
            "files": {
                "quadtree": Path(quadtree_path).name,
                "subgrid": subgrid_path.name,
                "precipitation": precip_path.name,
                "config": config_path.name,
            },
            "unsupported_physics": {
                "infiltration": False,
                "sewer_drainage": False,
                "water_level_boundary": False,
                "tide": False,
                "wind_waves": False,
                "river_inflow": False,
                "building_interior_storage": False,
            },
            "warnings": [
                "Adaptive remains disabled in the public run API until face-based "
                "result normalization and the Full-vs-Adaptive acceptance benchmark pass."
            ],
        }
        report_path = root / "model_build_report.json"
        atomic_write_json(report_path, report)
        return ModelBuildResult(root, report_path, report)
