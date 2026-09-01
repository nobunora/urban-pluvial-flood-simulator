#!/usr/bin/env python3
"""Compatibility CLI for the application-owned OSM fallback provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from floodsim.providers.common import area_from_square, make_session
from floodsim.providers.osm import OVERPASS, OsmProvider, local_bbox

__all__ = ["OVERPASS", "download_osm_vectors", "local_bbox", "make_session"]


def download_osm_vectors(center_lat: float, center_lon: float, half_size_m: float,
                         out_dir: str | Path, cache_dir: str | Path = ".cache") -> dict:
    area = area_from_square(center_lat, center_lon, half_size_m)
    result = OsmProvider().acquire(area, cache_dir, out_dir, margin_m=30.0)
    return result.legacy_manifest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--half-size-m", type=float, default=1000.0)
    parser.add_argument("--out-dir", default="vectors")
    parser.add_argument("--cache-dir", default=".cache")
    args = parser.parse_args()
    print(json.dumps(download_osm_vectors(args.center_lat, args.center_lon, args.half_size_m,
                                          args.out_dir, args.cache_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
