#!/usr/bin/env python3
"""Compatibility CLI for the application-owned GSI elevation provider."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path

from floodsim.providers.common import area_from_square
from floodsim.providers.gsi_elevation import (
    PROVIDERS,
    GsiElevationProvider,
    decode_gsi_dem_rgb,
    fetch_tile,
    lat_to_tile_y,
    lon_to_tile_x,
    provider_mosaic,
    reproject_provider,
)

__all__ = [
    "PROVIDERS",
    "decode_gsi_dem_rgb",
    "download_dem",
    "fetch_tile",
    "lat_to_tile_y",
    "lon_to_tile_x",
    "provider_mosaic",
    "reproject_provider",
    "target_lonlat_bounds",
]


def target_lonlat_bounds(center_lat: float, center_lon: float, half_size_m: float):
    from floodsim.providers.common import area_lonlat_bounds_from_center

    return area_lonlat_bounds_from_center(center_lat, center_lon, half_size_m)


def download_dem(center_lat: float, center_lon: float, half_size_m: float = 1000.0,
                 grid_m: float = 1.0, out: str | Path = "dem_1m.npz",
                 cache_dir: str | Path = ".cache", providers: Iterable[tuple[str, str, int]] = PROVIDERS,
                 max_nearest_fill_fraction: float = 0.02) -> dict:
    area = area_from_square(center_lat, center_lon, half_size_m)
    product = GsiElevationProvider().acquire(
        area, grid_m, cache_dir, providers, max_nearest_fill_fraction=max_nearest_fill_fraction
    )
    return product.write_legacy(out, area, grid_m)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--half-size-m", type=float, default=1000.0)
    parser.add_argument("--grid-m", type=float, default=1.0)
    parser.add_argument("--out", default="dem_1m.npz")
    parser.add_argument("--cache-dir", default=".cache")
    parser.add_argument("--max-nearest-fill-fraction", type=float, default=0.02)
    args = parser.parse_args()
    info = download_dem(args.center_lat, args.center_lon, args.half_size_m, args.grid_m,
                        args.out, args.cache_dir,
                        max_nearest_fill_fraction=args.max_nearest_fill_fraction)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
