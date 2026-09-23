#!/usr/bin/env python3
"""Extract building polygons and road-edge lines from GSI Fundamental Geospatial Data.

The script expects one or more ZIP files downloaded as 基盤地図情報「基本項目」/ALL.
It extracts geometries intersecting a local square window and converts JGD2024
latitude/longitude coordinates to the same local AEQD metric coordinates used by
`gsi_dem1a_to_npz.py`.

This is a compact reference parser, not a complete implementation of every FGD GML
feature type.
"""
from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer

POSLIST_RE = re.compile(rb"<gml:posList>\s*([^<]+?)\s*</gml:posList>", re.DOTALL)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", dest="zips", action="append", required=True,
                    help="GSI basic-item/ALL ZIP; repeat for adjacent areas")
    ap.add_argument("--center-lat", type=float, required=True)
    ap.add_argument("--center-lon", type=float, required=True)
    ap.add_argument("--half-size-m", type=float, default=1000.0)
    ap.add_argument("--buffer-m", type=float, default=100.0)
    ap.add_argument("--out-dir", default="vectors")
    args = ap.parse_args()

    crs_jgd2024 = CRS.from_epsg(6668)
    crs_local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={args.center_lat} +lon_0={args.center_lon} "
        "+ellps=GRS80 +units=m +no_defs"
    )
    to_local = Transformer.from_crs(crs_jgd2024, crs_local, always_xy=True)
    to_ll = Transformer.from_crs(crs_local, crs_jgd2024, always_xy=True)

    r = float(args.half_size_m + args.buffer_m)
    corners_x = np.array([-r, r, r, -r], dtype=float)
    corners_y = np.array([-r, -r, r, r], dtype=float)
    lon_c, lat_c = to_ll.transform(corners_x, corners_y)
    lat_min, lat_max = float(np.min(lat_c)), float(np.max(lat_c))
    lon_min, lon_max = float(np.min(lon_c)), float(np.max(lon_c))

    buildings: list[np.ndarray] = []
    roads: list[np.ndarray] = []

    for path in args.zips:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                is_building = "-BldA-" in name
                is_road = "-RdEdg-" in name
                if not (is_building or is_road):
                    continue

                print(f"scan: {Path(path).name} :: {name}")
                data = archive.read(name)
                target = buildings if is_building else roads

                for match in POSLIST_RE.finditer(data):
                    values = np.fromstring(
                        match.group(1).decode("ascii", errors="ignore"),
                        sep=" ",
                        dtype=np.float64,
                    )
                    if values.size < 4 or values.size % 2:
                        continue

                    coords = values.reshape(-1, 2)
                    lat = coords[:, 0]
                    lon = coords[:, 1]
                    if (
                        float(lat.max()) < lat_min
                        or float(lat.min()) > lat_max
                        or float(lon.max()) < lon_min
                        or float(lon.min()) > lon_max
                    ):
                        continue

                    x, y = to_local.transform(lon, lat)
                    geom = np.column_stack([x, y]).astype(np.float32)
                    target.append(geom)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out / "buildings.npz",
        buildings=np.array(buildings, dtype=object),
    )
    np.savez_compressed(
        out / "basemap_vectors.npz",
        roads=np.array(roads, dtype=object),
    )
    print(f"buildings: {len(buildings)}")
    print(f"road-edge geometries: {len(roads)}")
    print(f"saved under: {out}")


if __name__ == "__main__":
    main()
