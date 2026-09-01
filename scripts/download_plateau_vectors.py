#!/usr/bin/env python3
"""Compatibility CLI for the application-owned PLATEAU vector provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from floodsim.providers.common import area_from_square
from floodsim.providers.plateau import PlateauProvider


class PlateauUnavailable(RuntimeError):
    """Retained for callers of the former script-level exception."""


def extract_citygml(data: bytes, center_lat: float, center_lon: float,
                    half_size_m: float, margin_m: float = 30.0):
    from floodsim.providers.plateau import extract_citygml as provider_extract_citygml

    return provider_extract_citygml(data, area_from_square(center_lat, center_lon, half_size_m), margin_m)


def download_plateau_vectors(center_lat: float, center_lon: float, half_size_m: float,
                             out_dir: str | Path, cache_dir: str | Path = ".cache") -> dict:
    area = area_from_square(center_lat, center_lon, half_size_m)
    try:
        result = PlateauProvider().acquire(area, cache_dir, out_dir, margin_m=50.0)
    except Exception as exc:
        # Preserve the legacy exception boundary while the provider itself keeps
        # expected failures typed and never catches programming errors.
        from floodsim.providers.common import ProviderError

        if isinstance(exc, ProviderError):
            raise PlateauUnavailable(str(exc)) from exc
        raise
    return result.legacy_manifest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lon", type=float, required=True)
    parser.add_argument("--half-size-m", type=float, default=1000.0)
    parser.add_argument("--out-dir", default="vectors")
    parser.add_argument("--cache-dir", default=".cache")
    args = parser.parse_args()
    info = download_plateau_vectors(args.center_lat, args.center_lon, args.half_size_m,
                                    args.out_dir, args.cache_dir)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
