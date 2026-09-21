#!/usr/bin/env python3
"""Build and optionally execute a deterministic Adaptive SFINCS smoke model."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from pyproj import CRS

from floodsim.domain.rainfall import RainfallTimeSeries
from floodsim.preprocessing.adaptive_grid import build_adaptive_grid
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.preprocessing.roof_rainfall import allocate_roof_rainfall
from floodsim.sfincs.adaptive_model_builder import SfincsAdaptiveModelBuilder
from floodsim.sfincs.runner import ResolvedEngine, SfincsRunner, sha256_file


def _fixture_grid(size: int = 96) -> FullGridProduct:
    crs = CRS.from_proj4(
        "+proj=aeqd +lat_0=35.0 +lon_0=139.0 +datum=WGS84 +units=m +no_defs"
    )
    yy, xx = np.mgrid[0:size, 0:size]
    terrain = (0.001 * xx + 0.002 * yy).astype(np.float32)
    buildings = np.zeros((size, size), dtype=bool)
    roads = np.zeros((size, size), dtype=bool)
    mask = np.ones((size, size), dtype=np.uint8)
    mask[0, :] = 3
    mask[-1, :] = 3
    mask[:, 0] = 3
    mask[:, -1] = 3
    manning = np.full((size, size), 0.030, dtype=np.float32)
    roof = allocate_roof_rainfall(buildings)
    return FullGridProduct(
        elevation_m=terrain,
        building_mask=buildings,
        sfincs_mask=mask,
        manning_n=manning,
        rain_weight=roof.rain_weight.astype(np.float32),
        roof_allocation=roof,
        width_cells=size,
        height_cells=size,
        dx_m=1.0,
        dy_m=1.0,
        x0_m=0.0,
        y0_m=0.0,
        crs_wkt=crs.to_wkt(),
        road_mask=roads,
    )


def _fixture_rainfall() -> RainfallTimeSeries:
    return RainfallTimeSeries(
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        elapsed_seconds=[0.0, 60.0],
        intensity_mm_per_h=[10.0, 10.0],
        source_metadata={"fixture": "adaptive-sfincs-smoke"},
    )


def _inspect_result(path: Path) -> dict[str, Any]:
    with xr.open_dataset(path) as dataset:
        return {
            "dimensions": {
                str(name): int(size) for name, size in dataset.sizes.items()
            },
            "variables": {
                str(name): list(dataset[name].dims)
                for name in sorted(dataset.data_vars)
            },
        }


def run(out_dir: Path, sfincs_exe: Path | None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    grid = _fixture_grid()
    adaptive = build_adaptive_grid(grid)
    build = SfincsAdaptiveModelBuilder().build(
        out_dir / "model",
        grid,
        adaptive,
        _fixture_rainfall(),
    )

    payload: dict[str, Any] = {
        "build": build.report,
        "execution": {
            "status": "blocked",
            "reason": "No existing SFINCS executable supplied",
        },
    }
    if sfincs_exe is None:
        return payload

    executable = sfincs_exe.resolve()
    if not executable.is_file():
        raise FileNotFoundError(executable)
    engine = ResolvedEngine(
        executable=executable,
        source="explicit-smoke",
        sha256=sha256_file(executable),
    )
    execution = SfincsRunner().run(
        build.model_dir,
        logs_dir=out_dir / "logs",
        engine=engine,
    )
    payload["execution"] = {
        "status": "pass",
        "return_code": execution.return_code,
        "elapsed_seconds": execution.elapsed_seconds,
        "engine_sha256": execution.engine.sha256,
        "result_path": str(execution.result_path),
        "result": _inspect_result(execution.result_path),
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sfincs-exe", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir, args.sfincs_exe), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
