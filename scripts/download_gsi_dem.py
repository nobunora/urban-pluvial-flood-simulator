#!/usr/bin/env python3
"""Download GSI elevation PNG tiles and build the solver's local metric DEM grid.

The downloader prefers DEM1A and fills NoData cells with the best available lower
resolution GSI elevation model (DEM5A -> DEM5B -> DEM5C -> DEM10B). No GSI account
is required because it uses the public GSI tile service.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import requests
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from requests.adapters import HTTPAdapter
from scipy.ndimage import distance_transform_edt
from urllib3.util.retry import Retry

WEB_MERCATOR_RADIUS = 6378137.0
WEB_MERCATOR_HALF_WORLD = math.pi * WEB_MERCATOR_RADIUS
TILE_SIZE = 256

PROVIDERS = (
    ("DEM1A", "dem1a_png", 17),
    ("DEM5A", "dem5a_png", 15),
    ("DEM5B", "dem5b_png", 15),
    ("DEM5C", "dem5c_png", 15),
    ("DEM10B", "dem_png", 14),
)


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, connect=3, read=3, backoff_factor=0.5,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["GET"]))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "urban-pluvial-flood-simulator/auto-inputs"})
    return session


def decode_gsi_dem_rgb(rgb: np.ndarray) -> np.ndarray:
    """Decode a GSI PNG elevation tile to metres; NoData becomes NaN."""
    a = np.asarray(rgb, dtype=np.uint32)
    if a.ndim != 3 or a.shape[2] < 3:
        raise ValueError("GSI DEM PNG must have at least RGB channels")
    code = (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]
    out = np.empty(code.shape, dtype=np.float32)
    nodata = code == (1 << 23)
    positive = code < (1 << 23)
    out[positive] = code[positive].astype(np.float64) * 0.01
    negative = ~(positive | nodata)
    out[negative] = (code[negative].astype(np.int64) - (1 << 24)) * 0.01
    out[nodata] = np.nan
    return out


def lon_to_tile_x(lon: float, zoom: int) -> float:
    return (lon + 180.0) / 360.0 * (1 << zoom)


def lat_to_tile_y(lat: float, zoom: int) -> float:
    lat = min(85.05112878, max(-85.05112878, lat))
    phi = math.radians(lat)
    return (1.0 - math.asinh(math.tan(phi)) / math.pi) * 0.5 * (1 << zoom)


def target_lonlat_bounds(center_lat: float, center_lon: float, half_size_m: float) -> tuple[float, float, float, float]:
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lon} +datum=WGS84 +units=m +no_defs"
    )
    to_ll = Transformer.from_crs(local, CRS.from_epsg(4326), always_xy=True)
    pts = [(-half_size_m, -half_size_m), (-half_size_m, half_size_m),
           (half_size_m, -half_size_m), (half_size_m, half_size_m)]
    ll = [to_ll.transform(x, y) for x, y in pts]
    lons = [p[0] for p in ll]
    lats = [p[1] for p in ll]
    return min(lons), min(lats), max(lons), max(lats)


def _tile_cache_path(cache_dir: Path, layer: str, zoom: int, x: int, y: int) -> Path:
    return cache_dir / "gsi" / layer / str(zoom) / str(x) / f"{y}.png"


def fetch_tile(session: requests.Session, layer: str, zoom: int, x: int, y: int,
               cache_dir: Path, timeout: float = 30.0) -> np.ndarray | None:
    path = _tile_cache_path(cache_dir, layer, zoom, x, y)
    missing = path.with_suffix(".missing")
    if path.exists():
        with Image.open(path) as im:
            return decode_gsi_dem_rgb(np.asarray(im.convert("RGB")))
    if missing.exists():
        return None

    url = f"https://cyberjapandata.gsi.go.jp/xyz/{layer}/{zoom}/{x}/{y}.png"
    response = session.get(url, timeout=timeout)
    if response.status_code == 404:
        missing.parent.mkdir(parents=True, exist_ok=True)
        missing.write_text("404\n", encoding="ascii")
        return None
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    with Image.open(path) as im:
        return decode_gsi_dem_rgb(np.asarray(im.convert("RGB")))


def provider_mosaic(session: requests.Session, layer: str, zoom: int,
                    bounds: tuple[float, float, float, float], cache_dir: Path) -> tuple[np.ndarray, object] | None:
    lon_min, lat_min, lon_max, lat_max = bounds
    x0 = max(0, int(math.floor(lon_to_tile_x(lon_min, zoom))) - 1)
    x1 = min((1 << zoom) - 1, int(math.floor(lon_to_tile_x(lon_max, zoom))) + 1)
    y0 = max(0, int(math.floor(lat_to_tile_y(lat_max, zoom))) - 1)
    y1 = min((1 << zoom) - 1, int(math.floor(lat_to_tile_y(lat_min, zoom))) + 1)

    mosaic = np.full(((y1 - y0 + 1) * TILE_SIZE, (x1 - x0 + 1) * TILE_SIZE), np.nan, np.float32)
    found = 0
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            tile = fetch_tile(session, layer, zoom, tx, ty, cache_dir)
            if tile is None:
                continue
            found += 1
            r = (ty - y0) * TILE_SIZE
            c = (tx - x0) * TILE_SIZE
            mosaic[r:r + TILE_SIZE, c:c + TILE_SIZE] = tile
    if found == 0:
        return None

    world_tiles = 1 << zoom
    tile_span = 2.0 * WEB_MERCATOR_HALF_WORLD / world_tiles
    pixel_size = tile_span / TILE_SIZE
    left = -WEB_MERCATOR_HALF_WORLD + x0 * tile_span
    top = WEB_MERCATOR_HALF_WORLD - y0 * tile_span
    transform = from_origin(left, top, pixel_size, pixel_size)
    return mosaic, transform


def reproject_provider(mosaic: np.ndarray, src_transform: object, center_lat: float,
                       center_lon: float, half_size_m: float, grid_m: float) -> np.ndarray:
    n = int(round((2.0 * half_size_m) / grid_m)) + 1
    dst = np.full((n, n), np.nan, dtype=np.float32)
    dst_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lon} +datum=WGS84 +units=m +no_defs"
    )
    dst_transform = from_origin(-half_size_m - grid_m / 2.0,
                                half_size_m + grid_m / 2.0, grid_m, grid_m)
    reproject(
        source=mosaic,
        destination=dst,
        src_transform=src_transform,
        src_crs="EPSG:3857",
        src_nodata=np.nan,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
        init_dest_nodata=True,
        num_threads=2,
    )
    return np.flipud(dst)


def download_dem(center_lat: float, center_lon: float, half_size_m: float = 1000.0,
                 grid_m: float = 1.0, out: str | Path = "dem_1m.npz",
                 cache_dir: str | Path = ".cache", providers: Iterable[tuple[str, str, int]] = PROVIDERS,
                 max_nearest_fill_fraction: float = 0.02) -> dict:
    if half_size_m <= 0 or grid_m <= 0:
        raise ValueError("half_size_m and grid_m must be positive")
    cache = Path(cache_dir)
    bounds = target_lonlat_bounds(center_lat, center_lon, half_size_m + 2 * grid_m)
    n = int(round((2.0 * half_size_m) / grid_m)) + 1
    x = np.linspace(-half_size_m, half_size_m, n, dtype=np.float32)
    y = np.linspace(-half_size_m, half_size_m, n, dtype=np.float32)
    z = np.full((n, n), np.nan, dtype=np.float32)
    source_id = np.zeros((n, n), dtype=np.uint8)
    provider_names: list[str] = []
    counts: dict[str, int] = {}

    session = make_session()
    for idx, (name, layer, zoom) in enumerate(providers, start=1):
        provider_names.append(name)
        packed = provider_mosaic(session, layer, zoom, bounds, cache)
        if packed is None:
            counts[name] = 0
            continue
        sampled = reproject_provider(packed[0], packed[1], center_lat, center_lon, half_size_m, grid_m)
        take = ~np.isfinite(z) & np.isfinite(sampled)
        z[take] = sampled[take]
        source_id[take] = idx
        counts[name] = int(take.sum())
        if np.isfinite(z).all():
            break

    missing = ~np.isfinite(z)
    missing_fraction = float(missing.mean())
    nearest_filled = 0
    if np.any(missing):
        if missing_fraction > max_nearest_fill_fraction:
            raise RuntimeError(
                f"Elevation coverage incomplete: {missing_fraction:.2%} remains after GSI fallbacks. "
                "Increase the allowed fill fraction only after checking the area."
            )
        if not np.isfinite(z).any():
            raise RuntimeError("No GSI elevation data found for requested area")
        _, nearest = distance_transform_edt(missing, return_indices=True)
        z[missing] = z[nearest[0][missing], nearest[1][missing]]
        nearest_filled = int(missing.sum())

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out, z=z, x=x, y=y, lat0=np.float64(center_lat), lon0=np.float64(center_lon),
        dx=np.float32(grid_m), source=source_id,
        source_names=np.asarray(provider_names), nearest_filled=np.int64(nearest_filled),
    )
    manifest = {
        "source": "GSI elevation tiles",
        "center_lat": center_lat,
        "center_lon": center_lon,
        "half_size_m": half_size_m,
        "grid_m": grid_m,
        "providers": counts,
        "nearest_filled_cells": nearest_filled,
        "missing_fraction_before_nearest_fill": missing_fraction,
        "attribution": "地理院タイル（標高タイル）を加工して作成",
        "attribution_url": "https://maps.gsi.go.jp/development/ichiran.html",
        "terms_url": "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html",
        "tile_url": "https://cyberjapandata.gsi.go.jp/xyz/{layer}/{z}/{x}/{y}.png",
    }
    out.with_suffix(".json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--center-lat", type=float, required=True)
    ap.add_argument("--center-lon", type=float, required=True)
    ap.add_argument("--half-size-m", type=float, default=1000.0)
    ap.add_argument("--grid-m", type=float, default=1.0)
    ap.add_argument("--out", default="dem_1m.npz")
    ap.add_argument("--cache-dir", default=".cache")
    ap.add_argument("--max-nearest-fill-fraction", type=float, default=0.02)
    args = ap.parse_args()
    info = download_dem(args.center_lat, args.center_lon, args.half_size_m, args.grid_m,
                        args.out, args.cache_dir,
                        max_nearest_fill_fraction=args.max_nearest_fill_fraction)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
