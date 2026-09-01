"""GSI elevation tile acquisition and normalized local DEM products."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError
from pyproj import CRS
from rasterio.transform import from_origin  # type: ignore[import-untyped]
from rasterio.warp import Resampling, reproject  # type: ignore[import-untyped]
from scipy.ndimage import distance_transform_edt  # type: ignore[import-untyped]

from floodsim.domain.geometry import AnalysisArea
from floodsim.providers.common import (
    DEFAULT_NETWORK_POLICY,
    NetworkPolicy,
    ProviderCoverageError,
    ProviderParseError,
    ProviderProvenance,
    area_lonlat_bounds,
    make_session,
    request_with_retry,
    write_json,
)

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


@dataclass
class ElevationProduct:
    z: np.ndarray
    x: np.ndarray
    y: np.ndarray
    source: np.ndarray
    source_names: list[str]
    nearest_filled: int
    provenance: ProviderProvenance

    def write_legacy(self, out: str | Path, area: AnalysisArea, grid_m: float) -> dict:
        output = Path(out)
        output.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            output,
            z=self.z,
            x=self.x,
            y=self.y,
            lat0=np.float64(area.center.lat_deg),
            lon0=np.float64(area.center.lon_deg),
            dx=np.float32(grid_m),
            source=self.source,
            source_names=np.asarray(self.source_names),
            nearest_filled=np.int64(self.nearest_filled),
        )
        manifest = {
            "source": "GSI elevation tiles",
            "center_lat": area.center.lat_deg,
            "center_lon": area.center.lon_deg,
            "half_size_m": area.width_m / 2.0 if area.width_m == area.height_m else None,
            "width_m": area.width_m,
            "height_m": area.height_m,
            "grid_m": grid_m,
            "providers": self.provenance.source_details["provider_counts"],
            "nearest_filled_cells": self.nearest_filled,
            "missing_fraction_before_nearest_fill": self.provenance.source_details["missing_fraction_before_nearest_fill"],
            "attribution": self.provenance.attribution,
            "attribution_url": "https://maps.gsi.go.jp/development/ichiran.html",
            "terms_url": self.provenance.terms_url,
            "tile_url": "https://cyberjapandata.gsi.go.jp/xyz/{layer}/{z}/{x}/{y}.png",
            "provenance": self.provenance.to_dict(),
        }
        write_json(output.with_suffix(".json"), manifest)
        return manifest


def decode_gsi_dem_rgb(rgb: np.ndarray) -> np.ndarray:
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


def _tile_cache_path(cache_dir: Path, layer: str, zoom: int, x: int, y: int) -> Path:
    return cache_dir / "gsi" / layer / str(zoom) / str(x) / f"{y}.png"


def fetch_tile(
    session,
    layer: str,
    zoom: int,
    x: int,
    y: int,
    cache_dir: Path,
    *,
    policy: NetworkPolicy = DEFAULT_NETWORK_POLICY,
    sleeper=None,
) -> np.ndarray | None:
    path = _tile_cache_path(cache_dir, layer, zoom, x, y)
    missing = path.with_suffix(".missing")
    if path.exists():
        try:
            with Image.open(path) as image:
                return decode_gsi_dem_rgb(np.asarray(image.convert("RGB")))
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            raise ProviderParseError(f"invalid cached GSI tile {layer}/{zoom}/{x}/{y}") from exc
    if missing.exists():
        return None
    url = f"https://cyberjapandata.gsi.go.jp/xyz/{layer}/{zoom}/{x}/{y}.png"
    kwargs = {"policy": policy, "accepted_statuses": frozenset({404})}
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    if sleeper is None:
        response = request_with_retry(session, "GET", url, policy=policy, accepted_statuses=frozenset({404}))
    else:
        response = request_with_retry(session, "GET", url, policy=policy, sleeper=sleeper,
                                      accepted_statuses=frozenset({404}))
    if response.status_code == 404:
        missing.parent.mkdir(parents=True, exist_ok=True)
        missing.write_text("404\n", encoding="ascii")
        return None
    if not response.content:
        raise ProviderParseError(f"GSI tile {layer}/{zoom}/{x}/{y} was empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    try:
        with Image.open(path) as image:
            return decode_gsi_dem_rgb(np.asarray(image.convert("RGB")))
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise ProviderParseError(f"invalid GSI tile {layer}/{zoom}/{x}/{y}") from exc


def provider_mosaic(session, layer: str, zoom: int, bounds: tuple[float, float, float, float], cache_dir: Path, *, policy: NetworkPolicy = DEFAULT_NETWORK_POLICY, sleeper=None):
    lon_min, lat_min, lon_max, lat_max = bounds
    x0 = max(0, math.floor(lon_to_tile_x(lon_min, zoom)) - 1)
    x1 = min((1 << zoom) - 1, math.floor(lon_to_tile_x(lon_max, zoom)) + 1)
    y0 = max(0, math.floor(lat_to_tile_y(lat_max, zoom)) - 1)
    y1 = min((1 << zoom) - 1, math.floor(lat_to_tile_y(lat_min, zoom)) + 1)
    mosaic = np.full(((y1 - y0 + 1) * TILE_SIZE, (x1 - x0 + 1) * TILE_SIZE), np.nan, np.float32)
    found = 0
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            tile = fetch_tile(session, layer, zoom, tx, ty, cache_dir, policy=policy, sleeper=sleeper)
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
    return mosaic, from_origin(left, top, pixel_size, pixel_size)


def reproject_provider(mosaic: np.ndarray, src_transform: object, area: AnalysisArea, grid_m: float) -> np.ndarray:
    nx = round(area.width_m / grid_m) + 1
    ny = round(area.height_m / grid_m) + 1
    dst = np.full((ny, nx), np.nan, dtype=np.float32)
    xmin, _, _, ymax = (-area.width_m / 2.0, -area.height_m / 2.0, area.width_m / 2.0, area.height_m / 2.0)
    dst_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={area.center.lat_deg} +lon_0={area.center.lon_deg} +datum=WGS84 +units=m +no_defs"
    )
    dst_transform = from_origin(xmin - grid_m / 2.0, ymax + grid_m / 2.0, grid_m, grid_m)
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


class GsiElevationProvider:
    provider_id = "gsi"

    def __init__(self, session=None, policy: NetworkPolicy = DEFAULT_NETWORK_POLICY, sleeper=None):
        self.session = session or make_session(policy)
        self.policy = policy
        self.sleeper = sleeper

    def acquire(
        self,
        area: AnalysisArea,
        grid_m: float = 1.0,
        cache_dir: str | Path = ".cache",
        providers: Iterable[tuple[str, str, int]] = PROVIDERS,
        max_nearest_fill_fraction: float = 0.02,
        acquired_at_utc: str | None = None,
    ) -> ElevationProduct:
        if grid_m <= 0:
            raise ValueError("grid_m must be positive")
        if not 0 <= max_nearest_fill_fraction <= 1:
            raise ValueError("max_nearest_fill_fraction must be between zero and one")
        cache = Path(cache_dir)
        nx = round(area.width_m / grid_m) + 1
        ny = round(area.height_m / grid_m) + 1
        x = np.linspace(-area.width_m / 2.0, area.width_m / 2.0, nx, dtype=np.float32)
        y = np.linspace(-area.height_m / 2.0, area.height_m / 2.0, ny, dtype=np.float32)
        z = np.full((ny, nx), np.nan, dtype=np.float32)
        source_id = np.zeros((ny, nx), dtype=np.uint8)
        provider_names: list[str] = []
        counts: dict[str, int] = {}
        bounds = area_lonlat_bounds(area, 2.0 * grid_m)
        for index, (name, layer, zoom) in enumerate(providers, start=1):
            provider_names.append(name)
            packed = provider_mosaic(self.session, layer, zoom, bounds, cache, policy=self.policy, sleeper=self.sleeper)
            if packed is None:
                counts[name] = 0
                continue
            sampled = reproject_provider(packed[0], packed[1], area, grid_m)
            take = ~np.isfinite(z) & np.isfinite(sampled)
            z[take] = sampled[take]
            source_id[take] = index
            counts[name] = int(take.sum())
            if np.isfinite(z).all():
                break
        missing = ~np.isfinite(z)
        missing_fraction = float(missing.mean())
        nearest_filled = 0
        if np.any(missing):
            if missing_fraction > max_nearest_fill_fraction:
                raise ProviderCoverageError(
                    f"Elevation coverage incomplete: {missing_fraction:.2%} remains after GSI fallbacks"
                )
            if not np.isfinite(z).any():
                raise ProviderCoverageError("No GSI elevation data found for requested area")
            _, nearest = distance_transform_edt(missing, return_indices=True)
            z[missing] = z[nearest[0][missing], nearest[1][missing]]
            nearest_filled = int(missing.sum())
        provenance = ProviderProvenance.create(
            "gsi",
            "Geospatial Information Authority of Japan elevation tiles",
            area.bounds,
            "地理院タイル（標高タイル）を加工して作成",
            "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html",
            source_details={
                "provider_counts": counts,
                "nearest_filled_cells": nearest_filled,
                "missing_fraction_before_nearest_fill": missing_fraction,
                "grid_m": grid_m,
                "source_names": provider_names,
                "row_orientation": "south_to_north after normalization",
            },
            acquired_at_utc=acquired_at_utc,
        )
        return ElevationProduct(z, x, y, source_id, provider_names, nearest_filled, provenance)


GSIProvider = GsiElevationProvider
