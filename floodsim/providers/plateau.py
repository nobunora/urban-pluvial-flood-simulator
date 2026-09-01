"""PLATEAU CityGML acquisition and hydraulic vector normalization."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import (  # type: ignore[import-untyped]
    GeometryCollection,
    LineString,
    MultiPolygon,
    Polygon,
    box,
)
from shapely.ops import unary_union  # type: ignore[import-untyped]

from floodsim.domain.geometry import AnalysisArea
from floodsim.providers.common import (
    DEFAULT_NETWORK_POLICY,
    NetworkPolicy,
    ProviderParseError,
    ProviderProvenance,
    ProviderUnavailableError,
    area_lonlat_bounds,
    local_crs,
    make_session,
    read_json,
    request_with_retry,
    write_json,
)

API_BASE = "https://api.plateauview.mlit.go.jp"
TERMS_URL = "https://www.mlit.go.jp/plateau/site-policy/"


@dataclass
class PlateauVectors:
    buildings: list[np.ndarray]
    road_lines: list[np.ndarray]
    road_polygons: list[np.ndarray]
    provenance: ProviderProvenance

    def legacy_manifest(self) -> dict[str, Any]:
        details = self.provenance.source_details
        return {
            "provider": "PLATEAU",
            "api": details["api_url"],
            "cities": details["cities"],
            "building_files": details["building_files"],
            "transportation_files": details["transportation_files"],
            "building_polygons": len(self.buildings),
            "road_lines": len(self.road_lines),
            "road_polygons": len(self.road_polygons),
            "attribution": self.provenance.attribution,
            "license": "Dataset terms are provided by the upstream PLATEAU response/site policy.",
            "license_url": self.provenance.terms_url,
            "provenance": self.provenance.to_dict(),
        }


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _dimension(data: bytes) -> int:
    head = data[:20000].decode("utf-8", errors="ignore")
    return 2 if 'srsDimension="2"' in head else 3


def _parse_poslist(text: str | None, dim: int, transformer: Transformer) -> np.ndarray | None:
    if not text:
        return None
    values = np.fromstring(text, sep=" ", dtype=np.float64)
    if values.size < dim * 2 or values.size % dim:
        return None
    points = values.reshape(-1, dim)
    lat = points[:, 0]
    lon = points[:, 1]
    x, y = transformer.transform(lon, lat)
    return np.column_stack((x, y))


def _ring_from_container(container: ET.Element, dim: int, transformer: Transformer) -> np.ndarray | None:
    for element in container.iter():
        if _local(element.tag) == "posList":
            return _parse_poslist(element.text, dim, transformer)
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
    polygon = Polygon(shell, holes)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    return polygon if not polygon.is_empty else None


def _polygons_under(parent: ET.Element, dim: int, transformer: Transformer) -> list[Polygon]:
    polygons: list[Polygon] = []
    for element in parent.iter():
        if _local(element.tag) == "Polygon":
            polygon = _polygon_from_element(element, dim, transformer)
            if polygon is not None:
                polygons.append(polygon)
    return polygons


def _find_named_descendants(parent: ET.Element, names: tuple[str, ...]) -> list[ET.Element]:
    return [element for element in parent.iter() if _local(element.tag) in names]


def _geometry_exteriors(geometry) -> list[np.ndarray]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [np.asarray(geometry.exterior.coords, dtype=np.float64)]
    if isinstance(geometry, MultiPolygon):
        return [np.asarray(item.exterior.coords, dtype=np.float64) for item in geometry.geoms if not item.is_empty]
    if isinstance(geometry, GeometryCollection):
        result: list[np.ndarray] = []
        for item in geometry.geoms:
            result.extend(_geometry_exteriors(item))
        return result
    return []


def extract_citygml(data: bytes, area: AnalysisArea, margin_m: float = 30.0) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    """Extract buildings, road lines, and road polygons in local x/y."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ProviderParseError("PLATEAU CityGML XML is invalid") from exc
    transformer = Transformer.from_crs(CRS.from_epsg(6697), local_crs(area), always_xy=True)
    xmin, ymin, xmax, ymax = (-area.width_m / 2.0 - margin_m, -area.height_m / 2.0 - margin_m,
                              area.width_m / 2.0 + margin_m, area.height_m / 2.0 + margin_m)
    clip = box(xmin, ymin, xmax, ymax)
    dim = _dimension(data)
    buildings: list[np.ndarray] = []
    road_lines: list[np.ndarray] = []
    road_polygons: list[np.ndarray] = []
    for element in root.iter():
        kind = _local(element.tag)
        if kind == "Building":
            surfaces: list[Polygon] = []
            for preferred in (("lod0FootPrint",), ("lod0RoofEdge",), ("GroundSurface",)):
                groups = _find_named_descendants(element, preferred)
                for group in groups:
                    surfaces.extend(_polygons_under(group, dim, transformer))
                if surfaces:
                    break
            if not surfaces:
                surfaces = _polygons_under(element, dim, transformer)
            if surfaces:
                buildings.extend(_geometry_exteriors(unary_union(surfaces).intersection(clip)))
        elif kind == "Road":
            surfaces = []
            for child in element.iter():
                if _local(child.tag) == "Polygon":
                    polygon = _polygon_from_element(child, dim, transformer)
                    if polygon is not None:
                        surfaces.append(polygon)
            if surfaces:
                road_polygons.extend(_geometry_exteriors(unary_union(surfaces).intersection(clip)))
            else:
                for child in element.iter():
                    if _local(child.tag) != "posList":
                        continue
                    points = _parse_poslist(child.text, dim, transformer)
                    if points is None or len(points) < 2:
                        continue
                    line = LineString(points).intersection(clip)
                    if line.geom_type == "LineString":
                        road_lines.append(np.asarray(line.coords, dtype=np.float64))
                    elif line.geom_type == "MultiLineString":
                        road_lines.extend(np.asarray(item.coords, dtype=np.float64) for item in line.geoms)
    return buildings, road_lines, road_polygons


def _normalize_cities(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("cities"), list):
        return [item for item in payload["cities"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and "cityCode" in payload:
        return [payload]
    return []


def _download(session, url: str, cache_dir: Path, *, policy: NetworkPolicy, sleeper=None) -> bytes:
    name = url.rsplit("/", 1)[-1].split("?", 1)[0] or "citygml.gml"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    path = cache_dir / "plateau" / f"{digest}_{name}"
    if path.exists():
        data = path.read_bytes()
        if not data:
            raise ProviderParseError("cached PLATEAU CityGML is empty")
        return data
    if sleeper is None:
        response = request_with_retry(session, "GET", url, policy=policy)
    else:
        response = request_with_retry(session, "GET", url, policy=policy, sleeper=sleeper)
    if not response.content:
        raise ProviderParseError("PLATEAU CityGML response is empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return response.content


class PlateauProvider:
    provider_id = "plateau"

    def __init__(self, session=None, policy: NetworkPolicy = DEFAULT_NETWORK_POLICY, sleeper=None):
        self.session = session or make_session(policy)
        self.policy = policy
        self.sleeper = sleeper

    def acquire(
        self,
        area: AnalysisArea,
        cache_dir: str | Path = ".cache",
        out_dir: str | Path | None = None,
        margin_m: float = 50.0,
        acquired_at_utc: str | None = None,
    ) -> PlateauVectors:
        lon1, lat1, lon2, lat2 = area_lonlat_bounds(area, margin_m)
        condition = f"r:{lon1:.9f},{lat1:.9f},{lon2:.9f},{lat2:.9f}"
        url = f"{API_BASE}/datacatalog/citygml/{condition}"
        if self.sleeper is None:
            response = request_with_retry(
                self.session, "GET", url, policy=self.policy,
                params={"types": "bldg,tran"}, accepted_statuses=frozenset({404}),
            )
        else:
            response = request_with_retry(
                self.session, "GET", url, policy=self.policy, sleeper=self.sleeper,
                params={"types": "bldg,tran"}, accepted_statuses=frozenset({404}),
            )
        if response.status_code == 404:
            raise ProviderUnavailableError("PLATEAU has no CityGML dataset for this area")
        cities = _normalize_cities(read_json(response, "PLATEAU catalog"))
        if not cities:
            raise ProviderUnavailableError("PLATEAU API returned no cities for this area")
        building_urls: list[str] = []
        transport_urls: list[str] = []
        city_meta: list[dict[str, Any]] = []
        for city in cities:
            files = city.get("files") or {}
            building_urls.extend(item["url"] for item in files.get("bldg", []) if isinstance(item, dict) and item.get("url"))
            transport_urls.extend(item["url"] for item in files.get("tran", []) if isinstance(item, dict) and item.get("url"))
            city_meta.append({key: city.get(key) for key in ("cityCode", "cityName", "year", "spec")})
        building_urls = list(dict.fromkeys(building_urls))
        transport_urls = list(dict.fromkeys(transport_urls))
        if not building_urls:
            raise ProviderUnavailableError("PLATEAU dataset has no building CityGML files for this area")
        buildings: list[np.ndarray] = []
        roads: list[np.ndarray] = []
        road_polygons: list[np.ndarray] = []
        cache = Path(cache_dir)
        for file_url in building_urls:
            parsed_buildings, _, _ = extract_citygml(self._download(file_url, cache), area, margin_m)
            buildings.extend(parsed_buildings)
        for file_url in transport_urls:
            _, parsed_lines, parsed_polygons = extract_citygml(self._download(file_url, cache), area, margin_m)
            roads.extend(parsed_lines)
            road_polygons.extend(parsed_polygons)
        if not buildings:
            raise ProviderUnavailableError("PLATEAU building files downloaded but no usable footprints were parsed")
        provenance = ProviderProvenance.create(
            "plateau",
            "Project PLATEAU 3D city model",
            area.bounds,
            "Project PLATEAU 3D都市モデル（各地方公共団体）を加工して作成",
            TERMS_URL,
            source_details={
                "api_url": url,
                "cities": city_meta,
                "building_files": len(building_urls),
                "transportation_files": len(transport_urls),
                "building_polygons": len(buildings),
                "road_lines": len(roads),
                "road_polygons": len(road_polygons),
                "feature_types": ["bldg", "tran"],
                "axis_order": "CityGML latitude longitude elevation parsed as lat/lon",
                "margin_m": margin_m,
            },
            acquired_at_utc=acquired_at_utc,
        )
        result = PlateauVectors(buildings, roads, road_polygons, provenance)
        if out_dir is not None:
            self._write_legacy(result, Path(out_dir))
        return result

    def _download(self, url: str, cache_dir: Path) -> bytes:
        return _download(self.session, url, cache_dir, policy=self.policy, sleeper=self.sleeper)

    @staticmethod
    def _write_legacy(result: PlateauVectors, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out / "buildings.npz", buildings=np.asarray(result.buildings, dtype=object))
        np.savez_compressed(out / "basemap_vectors.npz", roads=np.asarray(result.road_lines, dtype=object),
                            road_polygons=np.asarray(result.road_polygons, dtype=object),
                            rail=np.asarray([], dtype=object), water=np.asarray([], dtype=object),
                            admin=np.asarray([], dtype=object))
        write_json(out / "vectors_manifest.json", result.legacy_manifest())


PLATEAUProvider = PlateauProvider
