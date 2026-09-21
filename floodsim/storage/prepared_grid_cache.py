"""Versioned prepared Full 1 m input cache for fast reruns."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from floodsim.domain.geometry import AnalysisArea
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.preprocessing.roof_rainfall import RoofRainAllocation
from floodsim.storage.run_store import atomic_write_json

PREPARED_GRID_CACHE_SCHEMA = "1"
PREPARED_GRID_REVISION = "full1m-preprocess-v4-adaptive-constraints"


@dataclass(frozen=True)
class PreparedGridEntry:
    key: str
    grid: FullGridProduct
    metadata: dict[str, Any]


class PreparedGridCache:
    """Persist rainfall-independent Full 1 m grid inputs by exact area identity."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root) / "prepared_full1m"

    @staticmethod
    def identity(area: AnalysisArea) -> dict[str, Any]:
        return {
            "schema": PREPARED_GRID_CACHE_SCHEMA,
            "revision": PREPARED_GRID_REVISION,
            "grid_mode": "full_1m",
            "grid_resolution_m": 1.0,
            "analysis_area": area.model_dump(mode="json"),
        }

    @classmethod
    def key_for(cls, area: AnalysisArea) -> str:
        payload = json.dumps(
            cls.identity(area),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:24]

    def _entry_dir(self, area: AnalysisArea) -> Path:
        return self.root / self.key_for(area)

    def load(self, area: AnalysisArea) -> PreparedGridEntry | None:
        entry_dir = self._entry_dir(area)
        arrays_path = entry_dir / "grid.npz"
        metadata_path = entry_dir / "metadata.json"
        if not arrays_path.is_file() or not metadata_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("identity") != self.identity(area):
                return None
            roof = metadata["roof_allocation"]
            with np.load(arrays_path, allow_pickle=False) as archive:
                elevation = np.asarray(archive["elevation_m"], dtype=np.float32)
                building = np.asarray(archive["building_mask"], dtype=bool)
                sfincs_mask = np.asarray(archive["sfincs_mask"], dtype=np.uint8)
                manning = np.asarray(archive["manning_n"], dtype=np.float32)
                rain_weight = np.asarray(archive["rain_weight"], dtype=np.float32)
                road = np.asarray(archive["road_mask"], dtype=bool)
                has_hard_boundary = bool(np.asarray(archive["has_adaptive_hard_boundary_zone"]).item())
                hard_boundary = np.asarray(
                    archive["adaptive_hard_boundary_zone"], dtype=np.int32
                )
                has_resolution_ceiling = bool(
                    np.asarray(archive["has_adaptive_resolution_ceiling_m"]).item()
                )
                resolution_ceiling = np.asarray(
                    archive["adaptive_resolution_ceiling_m"], dtype=np.int16
                )
                has_native_structure = bool(
                    np.asarray(archive["has_native_structure_mask"]).item()
                )
                native_structure = np.asarray(
                    archive["native_structure_mask"], dtype=bool
                )
                width = int(np.asarray(archive["width_cells"]).item())
                height = int(np.asarray(archive["height_cells"]).item())
                dx = float(np.asarray(archive["dx_m"]).item())
                dy = float(np.asarray(archive["dy_m"]).item())
                x0 = float(np.asarray(archive["x0_m"]).item())
                y0 = float(np.asarray(archive["y0_m"]).item())
                crs_wkt = str(np.asarray(archive["crs_wkt"]).item())
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

        expected = (height, width)
        arrays = (
            elevation,
            building,
            sfincs_mask,
            manning,
            rain_weight,
            road,
            hard_boundary,
            resolution_ceiling,
            native_structure,
        )
        if any(array.shape != expected for array in arrays):
            return None

        allocation = RoofRainAllocation(
            rain_weight=rain_weight.astype(np.float64, copy=False),
            meteorological_area_m2=float(roof["meteorological_area_m2"]),
            hydraulic_weighted_area_m2=float(roof["hydraulic_weighted_area_m2"]),
            relative_mass_error=float(roof["relative_mass_error"]),
            building_components=int(roof["building_components"]),
            redistributed_roof_cells=int(roof["redistributed_roof_cells"]),
        )
        grid = FullGridProduct(
            elevation_m=elevation,
            building_mask=building,
            sfincs_mask=sfincs_mask,
            manning_n=manning,
            rain_weight=rain_weight,
            roof_allocation=allocation,
            width_cells=width,
            height_cells=height,
            dx_m=dx,
            dy_m=dy,
            x0_m=x0,
            y0_m=y0,
            crs_wkt=crs_wkt,
            road_mask=road,
            adaptive_hard_boundary_zone=hard_boundary if has_hard_boundary else None,
            adaptive_resolution_ceiling_m=(
                resolution_ceiling if has_resolution_ceiling else None
            ),
            native_structure_mask=native_structure if has_native_structure else None,
        )
        return PreparedGridEntry(self.key_for(area), grid, metadata)

    def save(
        self,
        area: AnalysisArea,
        grid: FullGridProduct,
        *,
        metadata: dict[str, Any],
    ) -> PreparedGridEntry:
        entry_dir = self._entry_dir(area)
        entry_dir.mkdir(parents=True, exist_ok=True)
        arrays_path = entry_dir / "grid.npz"

        fd, temp_name = tempfile.mkstemp(prefix=".grid.", suffix=".tmp", dir=entry_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                np.savez_compressed(
                    handle,
                    elevation_m=grid.elevation_m,
                    building_mask=grid.building_mask,
                    sfincs_mask=grid.sfincs_mask,
                    manning_n=grid.manning_n,
                    rain_weight=grid.rain_weight,
                    road_mask=(
                        grid.road_mask
                        if grid.road_mask is not None
                        else np.zeros(grid.elevation_m.shape, dtype=bool)
                    ),
                    has_adaptive_hard_boundary_zone=np.uint8(
                        grid.adaptive_hard_boundary_zone is not None
                    ),
                    adaptive_hard_boundary_zone=(
                        grid.adaptive_hard_boundary_zone
                        if grid.adaptive_hard_boundary_zone is not None
                        else np.zeros(grid.elevation_m.shape, dtype=np.int32)
                    ),
                    has_adaptive_resolution_ceiling_m=np.uint8(
                        grid.adaptive_resolution_ceiling_m is not None
                    ),
                    adaptive_resolution_ceiling_m=(
                        grid.adaptive_resolution_ceiling_m
                        if grid.adaptive_resolution_ceiling_m is not None
                        else np.zeros(grid.elevation_m.shape, dtype=np.int16)
                    ),
                    has_native_structure_mask=np.uint8(
                        grid.native_structure_mask is not None
                    ),
                    native_structure_mask=(
                        grid.native_structure_mask
                        if grid.native_structure_mask is not None
                        else np.zeros(grid.elevation_m.shape, dtype=bool)
                    ),
                    width_cells=np.int64(grid.width_cells),
                    height_cells=np.int64(grid.height_cells),
                    dx_m=np.float64(grid.dx_m),
                    dy_m=np.float64(grid.dy_m),
                    x0_m=np.float64(grid.x0_m),
                    y0_m=np.float64(grid.y0_m),
                    crs_wkt=np.asarray(grid.crs_wkt),
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, arrays_path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

        payload = dict(metadata)
        payload["identity"] = self.identity(area)
        payload["roof_allocation"] = {
            "meteorological_area_m2": grid.roof_allocation.meteorological_area_m2,
            "hydraulic_weighted_area_m2": grid.roof_allocation.hydraulic_weighted_area_m2,
            "relative_mass_error": grid.roof_allocation.relative_mass_error,
            "building_components": grid.roof_allocation.building_components,
            "redistributed_roof_cells": grid.roof_allocation.redistributed_roof_cells,
        }
        atomic_write_json(entry_dir / "metadata.json", payload)
        return PreparedGridEntry(self.key_for(area), grid, payload)
