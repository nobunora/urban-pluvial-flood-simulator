"""Deterministic Full-vs-Adaptive hydraulic benchmark fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import numpy as np
from pyproj import CRS

from floodsim.domain.rainfall import RainfallTimeSeries
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.preprocessing.roof_rainfall import allocate_roof_rainfall

BenchmarkKind = Literal["open_area", "urban_obstacle", "road_channel"]


@dataclass(frozen=True)
class AdaptiveBenchmarkFixture:
    name: str
    benchmark_class: str
    grid: FullGridProduct
    rainfall: RainfallTimeSeries
    important_flow_path: str | None


def build_adaptive_benchmark_fixture(
    kind: BenchmarkKind,
    *,
    size: int = 64,
) -> AdaptiveBenchmarkFixture:
    if size < 32 or size % 32 != 0:
        raise ValueError("benchmark size must be a multiple of 32 and at least 32")

    yy, xx = np.indices((size, size), dtype=np.float32)
    terrain = (0.0002 * xx + 0.0001 * yy).astype(np.float32)
    building = np.zeros((size, size), dtype=bool)
    road = np.zeros((size, size), dtype=bool)
    important_flow_path: str | None = None
    benchmark_class = "open_area"

    if kind == "urban_obstacle":
        half = max(4, size // 10)
        center = size // 2
        building[
            center - half : center + half,
            center - half : center + half,
        ] = True
        benchmark_class = "urban"
    elif kind == "road_channel":
        center = size // 2
        road[:, center - 1 : center + 2] = True
        terrain[:, center - 1 : center + 2] -= np.float32(0.08)
        important_flow_path = "north-south depressed road corridor"
        benchmark_class = "road_channel"
    elif kind != "open_area":
        raise ValueError(f"unsupported benchmark kind: {kind}")

    mask = np.ones((size, size), dtype=np.uint8)
    mask[0, :] = 3
    mask[-1, :] = 3
    mask[:, 0] = 3
    mask[:, -1] = 3
    mask[building] = 0

    manning = np.full((size, size), 0.030, dtype=np.float32)
    manning[road] = 0.020
    roof = allocate_roof_rainfall(building)
    crs = CRS.from_proj4(
        "+proj=aeqd +lat_0=35.0 +lon_0=139.0 +datum=WGS84 +units=m +no_defs"
    )
    grid = FullGridProduct(
        elevation_m=terrain,
        building_mask=building,
        road_mask=road,
        sfincs_mask=mask,
        manning_n=manning,
        rain_weight=roof.rain_weight.astype(np.float32),
        roof_allocation=roof,
        width_cells=size,
        height_cells=size,
        dx_m=1.0,
        dy_m=1.0,
        x0_m=-size / 2.0,
        y0_m=-size / 2.0,
        crs_wkt=crs.to_wkt(),
    )
    rainfall_metadata: dict[str, object] = {
        "fixture": f"adaptive-validation-{kind}",
        "intensity_mm_per_h": 120.0,
        "duration_seconds": 1800.0,
    }
    rainfall = RainfallTimeSeries(
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        elapsed_seconds=[0.0, 1800.0],
        intensity_mm_per_h=[120.0, 120.0],
        source_metadata=rainfall_metadata,
    )
    return AdaptiveBenchmarkFixture(
        name=kind,
        benchmark_class=benchmark_class,
        grid=grid,
        rainfall=rainfall,
        important_flow_path=important_flow_path,
    )
