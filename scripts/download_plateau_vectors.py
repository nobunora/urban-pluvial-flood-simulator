#!/usr/bin/env python3
"""Download PLATEAU CityGML for a bounding box and extract hydraulic vectors.

Buildings are extracted from LOD0 footprints/roof edges when available. Roads are
extracted as surface polygons where possible and as lines otherwise. Coordinates in
PLATEAU EPSG:6697 are stored as latitude, longitude, elevation; they are converted to
local WGS84 AEQD x/y for the solver preprocessing pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import requests
from pyproj import CRS, Transformer
from requests.adapters import HTTPAdapter
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box
from shapely.ops import unary_union
from urllib3.util.retry import Retry

API_BASE = "https://api.plateauview.mlit.go.jp"


class PlateauUnavailable(RuntimeError):
    pass


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, connect=3, read=3, backoff_factor=0.5,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": "urban-pluvial-flood-simulator/auto-inputs"})
    return s


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _dimension(data: bytes) -> int:
    head = data[:20000].decode("utf-8", errors="ignore")
    if 'srsDimension="2"' in head:
        return 2
    return 3


def _parse_poslist(text: str | None, dim: int, transformer: Transformer) -> np.ndarray | None:
    if not text:
        return None
    vals = np.fromstring(text, sep=" ", dtype=np.float64)
    if vals.size < dim * 2 or vals.size % dim:
        return None
    pts = vals.reshape(-1, dim)
    lat = pts[:, 0]
    lon = pts[:, 1]
    x, y = transformer.transform(lon, lat)
    return np.column_stack((x, y))


def _ring_from_container(container: ET.Element, dim: int, transformer: Transformer) -> np.ndarray | None:
    for e in container.iter():
        if _local(e.tag) == "posList":
            return _parse_poslist(e.text, dim, transformer)
    return None


def _polygon_from_element(poly: ET.Element, dim: int, transformer: Transformer) -> Polygon | None:
    shell = None
    holes: list[np.ndarray] = []
    for child in poly:
        name = _local(child.tag)
        if name == "exterior":
            shell = _ring_from_container(child, dim, transformer)
        elif name == "interior":
            ring = _ring_from_container(child, dim, transformer)
            if ring is not None and len(ring) >= 4:
                holes.append(ring)
    if shell is None or len(shell) < 4:
        return None
    p = Polygon(shell, holes)
    if not p.is_valid:
        p = p.buffer(0)
    return p if not p.is_empty else None


def _polygons_under(parent: ET.Element, dim: int, transformer: Transformer) -> list[Polygon]:
    out: list[Polygon] = []
    for e in parent.iter():
        if _local(e.tag) == "Polygon":
            p = _polygon_from_element(e, dim, transformer)
            if p is not None:
                out.append(p)
    return out


def _find_named_descendants(parent: ET.Element, names: tuple[str, ...]) -> list[ET.Element]:
    return [e for e in parent.iter() if _local(e.tag) in names]


def _geometry_exteriors(geom) -> list[np.ndarray]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [np.asarray(geom.exterior.coords, dtype=np.float64)]
    if isinstance(geom, MultiPolygon):
        return [np.asarray(g.exterior.coords, dtype=np.float64) for g in geom.geoms if not g.is_empty]
    if isinstance(geom, GeometryCollection):
        out: list[np.ndarray] = []
        for g in geom.geoms:
            out.extend(_geometry_exteriors(g))
        return out
    return []


def extract_citygml(data: bytes, center_lat: float, center_lon: float,
                    half_size_m: float, margin_m: float = 30.0) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    """Return building polygons, road lines, and road polygons in local x/y."""
    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lon} +datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs(CRS.from_epsg(6668), local_crs, always_xy=True)
    clip = box(-half_size_m - margin_m, -half_size_m - margin_m,
               half_size_m + margin_m, half_size_m + margin_m)
    dim = _dimension(data)
    buildings: list[np.ndarray] = []
    road_lines: list[np.ndarray] = []
    road_polygons: list[np.ndarray] = []

    for _, elem in ET.iterparse(io.BytesIO(data), events=("end",)):
        kind = _local(elem.tag)
        if kind == "Building":
            surfaces: list[Polygon] = []
            for preferred in (("lod0FootPrint",), ("lod0RoofEdge",), ("GroundSurface",)):
                groups = _find_named_descendants(elem, preferred)
                if groups:
                    for group in groups:
                        surfaces.extend(_polygons_under(group, dim, transformer))
                    if surfaces:
                        break
            if not surfaces:
                surfaces = _polygons_under(elem, dim, transformer)
            if surfaces:
                geom = unary_union(surfaces).intersection(clip)
                buildings.extend(_geometry_exteriors(geom))
            elem.clear()

        elif kind == "Road":
            surfaces = []
            for e in elem.iter():
                if _local(e.tag) == "Polygon":
                    p = _polygon_from_element(e, dim, transformer)
                    if p is not None:
                        surfaces.append(p)
            if surfaces:
                geom = unary_union(surfaces).intersection(clip)
                road_polygons.extend(_geometry_exteriors(geom))
            else:
                for e in elem.iter():
                    if _local(e.tag) == "posList":
                        a = _parse_poslist(e.text, dim, transformer)
                        if a is None or len(a) < 2:
                            continue
                        line = LineString(a).intersection(clip)
                        if line.is_empty:
                            continue
                        if line.geom_type == "LineString":
                            road_lines.append(np.asarray(line.coords, dtype=np.float64))
                        elif line.geom_type == "MultiLineString":
                            road_lines.extend(np.asarray(g.coords, dtype=np.float64) for g in line.geoms)
            elem.clear()
    return buildings, road_lines, road_polygons


def _normalize_cities(payload) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("cities"), list):
        return payload["cities"]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict) and "cityCode" in payload:
        return [payload]
    return []


def _bbox(center_lat: float, center_lon: float, half_size_m: float) -> tuple[float, float, float, float]:
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


def _download(session: requests.Session, url: str, cache_dir: Path) -> bytes:
    name = url.rsplit("/", 1)[-1].split("?", 1)[0] or "citygml.gml"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    path = cache_dir / "plateau" / f"{digest}_{name}"
    if path.exists():
        return path.read_bytes()
    r = session.get(url, timeout=90)
    r.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r.content


def download_plateau_vectors(center_lat: float, center_lon: float, half_size_m: float,
                             out_dir: str | Path, cache_dir: str | Path = ".cache") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(cache_dir)
    lon1, lat1, lon2, lat2 = _bbox(center_lat, center_lon, half_size_m + 50.0)
    condition = f"r:{lon1:.9f},{lat1:.9f},{lon2:.9f},{lat2:.9f}"
    url = f"{API_BASE}/datacatalog/citygml/{condition}"
    session = make_session()
    r = session.get(url, params={"types": "bldg,tran"}, timeout=60)
    if r.status_code == 404:
        raise PlateauUnavailable("PLATEAU has no CityGML dataset for this area")
    r.raise_for_status()
    cities = _normalize_cities(r.json())
    if not cities:
        raise PlateauUnavailable("PLATEAU API returned no cities for this area")

    b_urls: list[str] = []
    t_urls: list[str] = []
    city_meta = []
    for city in cities:
        files = city.get("files") or {}
        b_urls.extend(x["url"] for x in files.get("bldg", []) if isinstance(x, dict) and x.get("url"))
        t_urls.extend(x["url"] for x in files.get("tran", []) if isinstance(x, dict) and x.get("url"))
        city_meta.append({k: city.get(k) for k in ("cityCode", "cityName", "year", "spec")})
    b_urls = list(dict.fromkeys(b_urls))
    t_urls = list(dict.fromkeys(t_urls))
    if not b_urls:
        raise PlateauUnavailable("PLATEAU dataset exists, but no building CityGML files overlap the area")

    buildings: list[np.ndarray] = []
    roads: list[np.ndarray] = []
    road_polygons: list[np.ndarray] = []
    for file_url in b_urls:
        b, _, _ = extract_citygml(_download(session, file_url, cache), center_lat, center_lon, half_size_m)
        buildings.extend(b)
    for file_url in t_urls:
        _, lines, polys = extract_citygml(_download(session, file_url, cache), center_lat, center_lon, half_size_m)
        roads.extend(lines)
        road_polygons.extend(polys)

    if not buildings:
        raise PlateauUnavailable("PLATEAU building files downloaded but no usable footprints were parsed")

    np.savez_compressed(out / "buildings.npz", buildings=np.asarray(buildings, dtype=object))
    np.savez_compressed(
        out / "basemap_vectors.npz",
        roads=np.asarray(roads, dtype=object),
        road_polygons=np.asarray(road_polygons, dtype=object),
        rail=np.asarray([], dtype=object),
        water=np.asarray([], dtype=object),
        admin=np.asarray([], dtype=object),
    )
    manifest = {
        "provider": "PLATEAU",
        "api": url,
        "cities": city_meta,
        "building_files": len(b_urls),
        "transportation_files": len(t_urls),
        "building_polygons": len(buildings),
        "road_lines": len(roads),
        "road_polygons": len(road_polygons),
        "attribution": "Project PLATEAU, Ministry of Land, Infrastructure, Transport and Tourism",
    }
    (out / "vectors_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--center-lat", type=float, required=True)
    ap.add_argument("--center-lon", type=float, required=True)
    ap.add_argument("--half-size-m", type=float, default=1000.0)
    ap.add_argument("--out-dir", default="vectors")
    ap.add_argument("--cache-dir", default=".cache")
    args = ap.parse_args()
    info = download_plateau_vectors(args.center_lat, args.center_lon, args.half_size_m,
                                    args.out_dir, args.cache_dir)
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
