#!/usr/bin/env python3
"""One-command acquisition and preprocessing for a flood-simulation area."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.download_gsi_dem import download_dem
from scripts.download_osm_vectors import download_osm_vectors
from scripts.download_plateau_vectors import download_plateau_vectors
from scripts.prepare_inputs import prepare_inputs


def prepare_area(center_lat: float, center_lon: float, half_size_m: float,
                 grid_m: float, out_dir: str | Path, vector_provider: str = "auto",
                 road_half_width: float = 3.0, n_ground: float = 0.030,
                 n_road: float = 0.020) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "cache"
    vectors = out / "vectors"
    dem_path = out / "dem_1m.npz"

    dem_info = download_dem(center_lat, center_lon, half_size_m, grid_m, dem_path, cache)

    vector_info = None
    errors: list[str] = []
    if vector_provider in ("auto", "plateau"):
        try:
            vector_info = download_plateau_vectors(center_lat, center_lon, half_size_m, vectors, cache)
        except Exception as exc:
            errors.append(f"PLATEAU: {exc}")
            if vector_provider == "plateau":
                raise
    if vector_info is None and vector_provider in ("auto", "osm"):
        try:
            vector_info = download_osm_vectors(center_lat, center_lon, half_size_m, vectors, cache)
        except Exception as exc:
            errors.append(f"OSM: {exc}")
            raise RuntimeError("Automatic vector acquisition failed: " + " | ".join(errors)) from exc

    hydraulic = prepare_inputs(dem_path, vectors / "buildings.npz", vectors / "basemap_vectors.npz",
                               out / "hydraulic_inputs", road_half_width, n_ground, n_road)
    manifest = {
        "center_lat": center_lat,
        "center_lon": center_lon,
        "half_size_m": half_size_m,
        "grid_m": grid_m,
        "dem": dem_info,
        "vectors": vector_info,
        "hydraulic": hydraulic,
        "fallback_messages": errors,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--center-lat", type=float, required=True)
    ap.add_argument("--center-lon", type=float, required=True)
    ap.add_argument("--half-size-m", type=float, default=1000.0)
    ap.add_argument("--grid-m", type=float, default=1.0)
    ap.add_argument("--out-dir", default="area")
    ap.add_argument("--vector-provider", choices=("auto", "plateau", "osm"), default="auto")
    ap.add_argument("--road-half-width", type=float, default=3.0)
    ap.add_argument("--n-ground", type=float, default=0.030)
    ap.add_argument("--n-road", type=float, default=0.020)
    args = ap.parse_args()
    result = prepare_area(args.center_lat, args.center_lon, args.half_size_m, args.grid_m,
                          args.out_dir, args.vector_provider, args.road_half_width,
                          args.n_ground, args.n_road)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
