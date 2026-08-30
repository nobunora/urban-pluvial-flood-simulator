#!/usr/bin/env python3
"""Build deterministic Phase 0 HydroMT-SFINCS compatibility fixtures."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

EXPECTED_HYDROMT_SFINCS = "2.0.0rc3"
EXPECTED_SFINCS = "2.4.0 Galibier"


def _load_sfincs_model() -> Any:
    """Import the pinned plugin despite an unrelated DEBUG shell variable."""
    debug = os.environ.get("DEBUG")
    restore_debug = debug is not None and not debug.isdigit()
    if restore_debug:
        os.environ.pop("DEBUG", None)
    try:
        from hydromt_sfincs import SfincsModel
    finally:
        if restore_debug:
            os.environ["DEBUG"] = debug
    return SfincsModel


def _version(name: str) -> str:
    return metadata.version(name)


def dependency_report() -> dict[str, Any]:
    """Return exact package versions used by the spike."""
    packages = [
        "hydromt_sfincs",
        "hydromt",
        "xarray",
        "netCDF4",
        "xugrid",
        "geopandas",
        "rasterio",
        "numpy",
        "scipy",
        "shapely",
        "pyproj",
    ]
    versions = {package: _version(package) for package in packages}
    normalized = versions["hydromt_sfincs"].replace("-", "")
    if normalized != EXPECTED_HYDROMT_SFINCS:
        raise RuntimeError(
            f"Expected hydromt_sfincs {EXPECTED_HYDROMT_SFINCS}, "
            f"found {versions['hydromt_sfincs']}"
        )
    return versions


def _configure(model: Any) -> None:
    model.config.set("tref", "20200101 000000")
    model.config.set("tstart", "20200101 000000")
    model.config.set("tstop", "20200101 000010")
    model.config.set("dthisout", 10)
    model.config.set("dtmapout", 10)
    model.config.set("dtmaxout", 10)
    model.config.set("outputformat", "net")
    model.config.set("coriolis", 0)
    model.config.set("storecumprcp", 0)


def _raster(values: np.ndarray, x: np.ndarray, y: np.ndarray, name: str) -> xr.DataArray:
    data = xr.DataArray(values, dims=("y", "x"), coords={"x": x, "y": y}, name=name)
    data.raster.set_crs(32633)
    data.raster.set_nodata(-9999)
    return data


def _regular_model(root: Path) -> dict[str, Any]:
    SfincsModel = _load_sfincs_model()
    model = SfincsModel(root=root, mode="w+", write_gis=False)
    model.grid.create(x0=0, y0=0, dx=10, dy=10, nmax=8, mmax=8, rotation=0, epsg=32633)
    x = np.arange(5, 80, 10, dtype=float)
    y = np.arange(5, 80, 10, dtype=float)
    z = _raster(np.zeros((8, 8), dtype="float32"), x, y, "elevtn")
    n = _raster(np.full((8, 8), 0.03, dtype="float32"), x, y, "manning")
    model.elevation.create([{"elevation": z}])
    model.mask.create()
    model.mask.data["mask"].values[:] = 1
    model.roughness.create([{"manning": n}])
    _configure(model)
    model.write()
    return {
        "path": str(root),
        "files": sorted(path.name for path in root.iterdir()),
        "shape": [8, 8],
        "grid": "regular",
    }


def _quadtree_model(root: Path) -> dict[str, Any]:
    SfincsModel = _load_sfincs_model()
    import geopandas as gpd
    from shapely.geometry import box

    model = SfincsModel(root=root, mode="w+", write_gis=False)
    refinement = gpd.GeoDataFrame(
        {"refinement_level": [2]}, geometry=[box(20, 20, 60, 60)], crs=32633
    )
    model.quadtree_grid.create(
        x0=0,
        y0=0,
        dx=10,
        dy=10,
        nmax=8,
        mmax=8,
        rotation=0,
        epsg=32633,
        refinement_polygons=refinement,
    )
    model.quadtree_mask.create()
    model.quadtree_mask.data["mask"].values[:] = True
    _configure(model)
    model.write()
    levels, counts = np.unique(
        model.quadtree_grid.data["level"].values, return_counts=True
    )
    return {
        "path": str(root),
        "files": sorted(path.name for path in root.iterdir()),
        "grid": "quadtree",
        "cells": int(len(model.quadtree_grid.data["level"])),
        "levels": {str(int(level)): int(count) for level, count in zip(levels, counts)},
    }


def _subgrid_model(root: Path) -> dict[str, Any]:
    SfincsModel = _load_sfincs_model()
    model = SfincsModel(root=root, mode="w+", write_gis=False)
    model.grid.create(x0=0, y0=0, dx=10, dy=10, nmax=4, mmax=4, rotation=0, epsg=32633)
    model.mask.create()
    model.mask.data["mask"].values[:] = 1
    x = np.arange(2.5, 40, 5, dtype=float)
    y = np.arange(2.5, 40, 5, dtype=float)
    elevation = _raster(
        np.arange(64, dtype="float32").reshape(8, 8) / 100, x, y, "elevtn"
    )
    roughness = _raster(np.full((8, 8), 0.03, dtype="float32"), x, y, "manning")
    model.subgrid.create(
        [{"elevation": elevation}],
        [{"manning": roughness}],
        nr_levels=3,
        nr_subgrid_pixels=2,
        nrmax=16,
    )
    _configure(model)
    model.write()
    return {
        "path": str(root),
        "files": sorted(path.name for path in root.iterdir()),
        "grid": "regular-with-subgrid",
        "source_raster_resolution_m": 5,
        "hydraulic_grid_resolution_m": 10,
        "subgrid_levels": 3,
        "subgrid_variables": sorted(model.subgrid.data.data_vars),
    }


def read_result(path: str | Path, require_zero: bool = True) -> dict[str, Any]:
    """Read a SFINCS NetCDF map without the HydroMT result reader."""
    result_path = Path(path)
    with xr.open_dataset(result_path) as dataset:
        required = {"h", "hmax", "zs", "zb", "msk"}
        missing = sorted(required.difference(dataset.data_vars))
        if missing:
            raise ValueError(f"Missing result variables: {', '.join(missing)}")
        expected_dims = {
            "h": ("time", "n", "m"),
            "hmax": ("timemax", "n", "m"),
            "zs": ("time", "n", "m"),
            "zb": ("n", "m"),
            "msk": ("n", "m"),
        }
        for name, dimensions in expected_dims.items():
            if dataset[name].dims != dimensions:
                raise ValueError(f"Unexpected dimensions for {name}: {dataset[name].dims}")
        finite = np.concatenate(
            [dataset[name].values[np.isfinite(dataset[name].values)] for name in ("h", "hmax")]
        )
        if finite.size == 0 or not np.all(np.isfinite(finite)):
            raise ValueError("Result depth contains no finite values")
        if require_zero and float(np.max(np.abs(finite))) > 1e-8:
            raise ValueError("Zero-rain fixture produced non-zero water")
        return {
            "path": str(result_path),
            "variables": {name: list(dataset[name].dims) for name in required},
            "units": {name: dataset[name].attrs.get("units") for name in required},
            "max_abs_depth_m": float(np.max(np.abs(finite))),
            "no_data_policy": "reject non-finite h/hmax values; msk identifies active cells",
        }


def _run_engine(executable: Path, model: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    completed = subprocess.run(
        [str(executable)], cwd=model["path"], capture_output=True, text=True, timeout=120
    )
    output = (completed.stdout + "\n" + completed.stderr).strip()
    result_path = Path(model["path"]) / "sfincs_map.nc"
    result = read_result(result_path)
    return {
        "returncode": completed.returncode,
        "executable": str(executable),
        "sha256": digest,
        "output_tail": output[-2000:],
        "result": result,
    }


def run(out_dir: str | Path, sfincs_exe: str | Path | None = None) -> dict[str, Any]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    versions = dependency_report()
    regular = _regular_model(root / "regular")
    quadtree = _quadtree_model(root / "quadtree")
    subgrid = _subgrid_model(root / "subgrid")
    execution: dict[str, Any]
    if sfincs_exe is None:
        execution = {"status": "blocked", "reason": "No permitted SFINCS executable supplied"}
    else:
        executable = Path(sfincs_exe).resolve()
        if not executable.is_file():
            raise FileNotFoundError(executable)
        execution = {"status": "pass", **_run_engine(executable, regular)}
    return {
        "hydromt_sfincs": versions,
        "regular_build": regular,
        "quadtree_build": quadtree,
        "subgrid_build": subgrid,
        "execution": execution,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sfincs-exe", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir, args.sfincs_exe), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
