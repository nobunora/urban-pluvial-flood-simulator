#!/usr/bin/env python3
"""Fallback vector downloader using the public OpenStreetMap Overpass API.

This is intentionally a fallback: PLATEAU is preferred because its building geometry
is an official Japanese 3D city-model dataset. OSM completeness varies by area.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import requests
from pyproj import CRS, Transformer
from requests.adapters import HTTPAdapter
from shapely.geometry import LineString, Polygon, box
from urllib3.util.retry import Retry

OVERPASS = "https://overpass-api.de/api/interpreter"


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, connect=3, read=3, backoff_factor=1.0,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["POST"]))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": "urban-pluvial-flood-simulator/auto-inputs"})
    return s


def local_bbox(center_lat: float, center_lon: float, half_size_m: float):
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lon} +datum=WGS84 +units=m +no_defs"
    )
    to_ll = Transformer.from_crs(local, CRS.from_epsg(4326), always_xy=True)
    pts = [to_ll.transform(x, y) for x, y in
           ((-half_size_m, -half_size_m), (-half_size_m, half_size_m),
            (half_size_m, -half_size_m), (half_size_m, half_size_m))]
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    return min(lons), min(lats), max(lons), max(lats)


def download_osm_vectors(center_lat: float, center_lon: float, half_size_m: float,
                         out_dir: str | Path, cache_dir: str | Path = ".cache") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    lon1, lat1, lon2, lat2 = local_bbox(center_lat, center_lon, half_size_m + 30.0)
    bbox = f"{lat1:.8f},{lon1:.8f},{lat2:.8f},{lon2:.8f}"
    query = f"""[out:json][timeout:90];
(
  way[\"building\"]({bbox});
  way[\"highway\"]({bbox});
);
out geom;"""
    key = f"osm_{center_lat:.5f}_{center_lon:.5f}_{int(half_size_m)}.json".replace("-", "m")
    cache_file = cache / "osm" / key
    if cache_file.exists():
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        s = make_session()
        r = s.post(OVERPASS, data={"data": query}, timeout=120)
        r.raise_for_status()
        payload = r.json()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lon} +datum=WGS84 +units=m +no_defs"
    )
    tr = Transformer.from_crs(CRS.from_epsg(4326), local, always_xy=True)
    clip = box(-half_size_m - 20, -half_size_m - 20, half_size_m + 20, half_size_m + 20)
    buildings: list[np.ndarray] = []
    roads: list[np.ndarray] = []

    for elem in payload.get("elements", []):
        geom = elem.get("geometry") or []
        if len(geom) < 2:
            continue
        lon = [p["lon"] for p in geom]
        lat = [p["lat"] for p in geom]
        x, y = tr.transform(lon, lat)
        a = np.column_stack((x, y))
        tags = elem.get("tags") or {}
        if "building" in tags and len(a) >= 4:
            p = Polygon(a)
            if not p.is_valid:
                p = p.buffer(0)
            p = p.intersection(clip)
            if p.is_empty:
                continue
            if p.geom_type == "Polygon":
                buildings.append(np.asarray(p.exterior.coords, float))
            elif p.geom_type == "MultiPolygon":
                buildings.extend(np.asarray(g.exterior.coords, float) for g in p.geoms)
        elif "highway" in tags:
            line = LineString(a).intersection(clip)
            if line.is_empty:
                continue
            if line.geom_type == "LineString":
                roads.append(np.asarray(line.coords, float))
            elif line.geom_type == "MultiLineString":
                roads.extend(np.asarray(g.coords, float) for g in line.geoms)

    if not buildings:
        raise RuntimeError("OSM fallback returned no building ways for requested area")
    np.savez_compressed(out / "buildings.npz", buildings=np.asarray(buildings, dtype=object))
    np.savez_compressed(out / "basemap_vectors.npz",
                        roads=np.asarray(roads, dtype=object),
                        road_polygons=np.asarray([], dtype=object),
                        rail=np.asarray([], dtype=object),
                        water=np.asarray([], dtype=object),
                        admin=np.asarray([], dtype=object))
    manifest = {
        "provider": "OpenStreetMap",
        "endpoint": OVERPASS,
        "building_polygons": len(buildings),
        "road_lines": len(roads),
        "attribution": "© OpenStreetMap contributors",
        "warning": "Fallback data; completeness and geometry quality vary by area.",
    }
    (out / "vectors_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--center-lat", type=float, required=True)
    ap.add_argument("--center-lon", type=float, required=True)
    ap.add_argument("--half-size-m", type=float, default=1000.0)
    ap.add_argument("--out-dir", default="vectors")
    ap.add_argument("--cache-dir", default=".cache")
    args = ap.parse_args()
    print(json.dumps(download_osm_vectors(args.center_lat, args.center_lon, args.half_size_m,
                                          args.out_dir, args.cache_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
