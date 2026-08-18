#!/usr/bin/env python3
"""Convert GSI Fundamental Geospatial Data DEM1A ZIP/GML files to a local metric grid.

The script reads only XML tiles overlapping the requested output window, projects the
JGD2024 latitude/longitude grid to a local azimuthal-equidistant CRS, resamples to a
regular metric grid, and optionally blends source-file seams.

Example
-------
python scripts/gsi_dem1a_to_npz.py \
    --zip FG-GML-XXXXXX-DEM1A-YYYYMMDD.zip \
    --center-lat 35.000000 --center-lon 135.000000 \
    --half-size-m 1000 --grid-m 1 \
    --out dem_1m.npz

Pass --zip multiple times when the requested window crosses download-file boundaries.
ZIP order is priority order: values from the first source win on exact overlaps.
"""
from __future__ import annotations

import argparse
import math
import re
import zipfile
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer
from scipy.ndimage import distance_transform_edt, map_coordinates

LOWER_RE = re.compile(r"<gml:lowerCorner>([^<]+)")
UPPER_RE = re.compile(r"<gml:upperCorner>([^<]+)")
HIGH_RE = re.compile(r"<gml:high>(\d+)\s+(\d+)")
START_RE = re.compile(r"<gml:startPoint>(\d+)\s+(\d+)")


def _header_bounds(header: str) -> tuple[float, float, float, float] | None:
    lo = LOWER_RE.search(header)
    hi = UPPER_RE.search(header)
    if not lo or not hi:
        return None
    lat1, lon1 = map(float, lo.group(1).split())
    lat2, lon2 = map(float, hi.group(1).split())
    return lat1, lon1, lat2, lon2


def parse_dem_gml(data: bytes) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Parse one GSI DEM1A JPGIS(GML) file.

    GSI documents the DEM tuple sequence as NW -> E, then toward S.  `startPoint`
    allows leading cells with no value to be omitted.  Missing elevations are kept
    as NaN.
    """
    text = data.decode("utf-8", errors="strict")
    bounds = _header_bounds(text)
    if bounds is None:
        raise ValueError("GML envelope not found")

    mh = HIGH_RE.search(text)
    if not mh:
        raise ValueError("gml:high not found")
    nx = int(mh.group(1)) + 1
    ny = int(mh.group(2)) + 1

    ms = START_RE.search(text)
    sx, sy = (0, 0) if not ms else (int(ms.group(1)), int(ms.group(2)))
    start_flat = sy * nx + sx

    begin = text.index("<gml:tupleList>") + len("<gml:tupleList>")
    end = text.index("</gml:tupleList>", begin)
    lines = text[begin:end].strip().splitlines()

    values = np.fromiter(
        (float(line.rsplit(",", 1)[1]) for line in lines if line.strip()),
        dtype=np.float32,
        count=len(lines),
    )
    values[np.abs(values) >= 9000.0] = np.nan

    flat = np.full(nx * ny, np.nan, dtype=np.float32)
    stop = min(start_flat + len(values), len(flat))
    flat[start_flat:stop] = values[: stop - start_flat]
    return flat.reshape(ny, nx), bounds


def seam_blend(z: np.ndarray, source: np.ndarray, width_cells: int) -> np.ndarray:
    """Blend lower-priority source boundaries using linear edge extrapolation.

    Source id 1 is the highest-priority reference.  For each subsequent source,
    boundary corrections are estimated from the adjacent higher-priority terrain and
    propagated inward with a cosine taper.  This is deliberately conservative and is
    intended only to remove artificial source seams, not to smooth real terrain.
    """
    if width_cells <= 0:
        return z

    out = z.astype(np.float64, copy=True)
    nr, nc = out.shape
    max_source = int(source.max())

    for sid in range(2, max_source + 1):
        corr_sum = np.zeros_like(out)
        corr_count = np.zeros_like(out, dtype=np.uint8)

        # (dr, dc): from source cell toward a higher-priority reference cell.
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r0 = max(0, -dr)
            r1 = min(nr, nr - dr)
            c0 = max(0, -dc)
            c1 = min(nc, nc - dc)

            rr = slice(r0, r1)
            cc = slice(c0, c1)
            rn = slice(r0 + dr, r1 + dr)
            cn = slice(c0 + dc, c1 + dc)

            s_here = source[rr, cc]
            s_ref = source[rn, cn]
            mask = (s_here == sid) & (s_ref > 0) & (s_ref < sid)
            if not np.any(mask):
                continue

            target = out[rn, cn].copy()

            # If a second reference cell exists behind the first, use first-order
            # continuation: z_target = 2*z_edge - z_inner.
            r2a, r2b = r0 + 2 * dr, r1 + 2 * dr
            c2a, c2b = c0 + 2 * dc, c1 + 2 * dc
            if 0 <= r2a and r2b <= nr and 0 <= c2a and c2b <= nc:
                r2 = slice(r2a, r2b)
                c2 = slice(c2a, c2b)
                same_ref = source[r2, c2] == s_ref
                extrap = 2.0 * out[rn, cn] - out[r2, c2]
                target = np.where(same_ref, extrap, target)

            local_corr = target - out[rr, cc]
            cs = corr_sum[rr, cc]
            ct = corr_count[rr, cc]
            cs[mask] += local_corr[mask]
            ct[mask] += 1

        boundary = corr_count > 0
        if not np.any(boundary):
            continue

        boundary_corr = np.zeros_like(out)
        boundary_corr[boundary] = corr_sum[boundary] / corr_count[boundary]

        distance, nearest = distance_transform_edt(~boundary, return_indices=True)
        mask = (source == sid) & (distance <= width_cells)
        if not np.any(mask):
            continue

        d = distance[mask]
        w = 0.5 * (1.0 + np.cos(np.pi * d / max(width_cells, 1)))
        nearest_corr = boundary_corr[nearest[0][mask], nearest[1][mask]]
        out[mask] += w * nearest_corr

    return out.astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", dest="zips", action="append", required=True,
                    help="GSI DEM1A ZIP; repeat for adjacent download files")
    ap.add_argument("--center-lat", type=float, required=True)
    ap.add_argument("--center-lon", type=float, required=True)
    ap.add_argument("--half-size-m", type=float, default=1000.0)
    ap.add_argument("--grid-m", type=float, default=1.0)
    ap.add_argument("--blend-width-m", type=float, default=20.0,
                    help="cosine taper width for source seams; 0 disables")
    ap.add_argument("--out", default="dem_1m.npz")
    args = ap.parse_args()

    half = float(args.half_size_m)
    dx = float(args.grid_m)
    if half <= 0 or dx <= 0:
        raise ValueError("half-size-m and grid-m must be positive")

    # JGD2024 geographic coordinates use GRS80.  A local AEQD grid gives metric x/y
    # without embedding any location-specific projected-zone assumption.
    crs_jgd2024 = CRS.from_epsg(6668)
    crs_local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={args.center_lat} +lon_0={args.center_lon} "
        "+ellps=GRS80 +units=m +no_defs"
    )
    to_ll = Transformer.from_crs(crs_local, crs_jgd2024, always_xy=True)

    n = int(round((2.0 * half) / dx)) + 1
    x = np.linspace(-half, half, n, dtype=np.float64)
    y = np.linspace(-half, half, n, dtype=np.float64)  # south -> north
    X, Y = np.meshgrid(x, y)
    lon, lat = to_ll.transform(X, Y)

    lat_min, lat_max = float(lat.min()), float(lat.max())
    lon_min, lon_max = float(lon.min()), float(lon.max())

    z = np.full((n, n), np.nan, dtype=np.float32)
    source = np.zeros((n, n), dtype=np.uint16)

    used_tiles = 0
    for source_id, zip_path in enumerate(args.zips, start=1):
        with zipfile.ZipFile(zip_path) as archive:
            for name in archive.namelist():
                if not name.lower().endswith((".xml", ".gml")):
                    continue

                with archive.open(name) as f:
                    header = f.read(4096).decode("utf-8", errors="ignore")
                bounds = _header_bounds(header)
                if bounds is None:
                    continue
                la1, lo1, la2, lo2 = bounds
                if la2 < lat_min or la1 > lat_max or lo2 < lon_min or lo1 > lon_max:
                    continue

                tile, (la1, lo1, la2, lo2) = parse_dem_gml(archive.read(name))
                ny, nx = tile.shape
                mask = (lat >= la1) & (lat <= la2) & (lon >= lo1) & (lon <= lo2)
                if not np.any(mask):
                    continue

                row = (la2 - lat[mask]) / (la2 - la1) * (ny - 1)
                col = (lon[mask] - lo1) / (lo2 - lo1) * (nx - 1)
                sample = map_coordinates(
                    tile, [row, col], order=1, mode="nearest", prefilter=False
                ).astype(np.float32)

                rr, cc = np.where(mask)
                # First ZIP has priority.  Later sources fill only holes.
                take = (source[rr, cc] == 0) & np.isfinite(sample)
                z[rr[take], cc[take]] = sample[take]
                source[rr[take], cc[take]] = source_id
                used_tiles += 1
                print(f"use: source={source_id} {name}")

    if not np.isfinite(z).any():
        raise RuntimeError("No DEM1A tile overlapped the requested window")

    missing = ~np.isfinite(z)
    if np.any(missing):
        # Fill only residual edge/sliver gaps by nearest valid sample.  A large missing
        # fraction usually means an adjacent DEM ZIP was not supplied.
        frac = float(missing.mean())
        print(f"warning: missing DEM fraction={frac:.6f}; nearest-fill applied")
        _, nearest = distance_transform_edt(missing, return_indices=True)
        z[missing] = z[nearest[0][missing], nearest[1][missing]]
        source[missing] = source[nearest[0][missing], nearest[1][missing]]

    blend_cells = int(round(args.blend_width_m / dx))
    z_blended = seam_blend(z, source, blend_cells)

    out = Path(args.out)
    np.savez_compressed(
        out,
        z=z_blended,
        z_raw=z,
        source=source,
        x=x.astype(np.float32),
        y=y.astype(np.float32),
        lat0=np.float64(args.center_lat),
        lon0=np.float64(args.center_lon),
        dx=np.float32(dx),
    )
    print(f"saved: {out}")
    print(f"grid: {n} x {n}, dx={dx:g} m, XML tiles used={used_tiles}")
    print(f"elevation range: {float(np.nanmin(z_blended)):.3f} .. {float(np.nanmax(z_blended)):.3f} m")


if __name__ == "__main__":
    main()
