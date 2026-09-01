"""OpenStreetMap building/highway acquisition for the PLATEAU fallback path."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, box  # type: ignore[import-untyped]

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

OVERPASS = "https://overpass-api.de/api/interpreter"
TERMS_URL = "https://www.openstreetmap.org/copyright"
OVERPASS_QUERY_TIMEOUT_S = 90


@dataclass
class OsmVectors:
    buildings: list[np.ndarray]
    road_lines: list[np.ndarray]
    provenance: ProviderProvenance

    def legacy_manifest(self) -> dict[str, Any]:
        details = self.provenance.source_details
        return {
            "provider": "OpenStreetMap",
            "endpoint": details["endpoint"],
            "building_polygons": len(self.buildings),
            "road_lines": len(self.road_lines),
            "attribution": self.provenance.attribution,
            "warning": self.provenance.warnings[0],
            "terms_url": self.provenance.terms_url,
            "provenance": self.provenance.to_dict(),
        }


def local_bbox(area: AnalysisArea, margin_m: float = 0.0) -> tuple[float, float, float, float]:
    return area_lonlat_bounds(area, margin_m)


def _cache_path(cache_dir: Path, area: AnalysisArea, margin_m: float) -> Path:
    identity = {
        "bounds": [area.bounds.west_deg, area.bounds.south_deg, area.bounds.east_deg, area.bounds.north_deg],
        "center": [area.center.lon_deg, area.center.lat_deg],
        "width_m": area.width_m,
        "height_m": area.height_m,
        "margin_m": margin_m,
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:20]
    return cache_dir / "osm" / f"{digest}.json"


class OsmProvider:
    provider_id = "osm"

    def __init__(self, session=None, policy: NetworkPolicy = DEFAULT_NETWORK_POLICY, sleeper=None):
        self.session = session or make_session(policy)
        self.policy = policy
        self.sleeper = sleeper

    def acquire(
        self,
        area: AnalysisArea,
        cache_dir: str | Path = ".cache",
        out_dir: str | Path | None = None,
        margin_m: float = 30.0,
        acquired_at_utc: str | None = None,
    ) -> OsmVectors:
        lon1, lat1, lon2, lat2 = local_bbox(area, margin_m)
        bbox = f"{lat1:.8f},{lon1:.8f},{lat2:.8f},{lon2:.8f}"
        query = f'''[out:json][timeout:{OVERPASS_QUERY_TIMEOUT_S}];
(
  way["building"]({bbox});
  way["highway"]({bbox});
);
out geom;'''
        cache_file = _cache_path(Path(cache_dir), area, margin_m)
        if cache_file.exists():
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProviderParseError("cached OSM response is invalid") from exc
        else:
            if self.sleeper is None:
                response = request_with_retry(self.session, "POST", OVERPASS,
                                              policy=self.policy, data={"data": query})
            else:
                response = request_with_retry(self.session, "POST", OVERPASS,
                                              policy=self.policy, sleeper=self.sleeper,
                                              data={"data": query})
            payload = read_json(response, "OSM Overpass")
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
            raise ProviderParseError("OSM Overpass response has no elements list")
        transformer = Transformer.from_crs("EPSG:4326", local_crs(area), always_xy=True)
        clip = box(-area.width_m / 2.0 - 20.0, -area.height_m / 2.0 - 20.0,
                   area.width_m / 2.0 + 20.0, area.height_m / 2.0 + 20.0)
        buildings: list[np.ndarray] = []
        roads: list[np.ndarray] = []
        for element in payload["elements"]:
            if not isinstance(element, dict):
                continue
            geometry = element.get("geometry") or []
            if not isinstance(geometry, list) or len(geometry) < 2:
                continue
            try:
                lon = [point["lon"] for point in geometry]
                lat = [point["lat"] for point in geometry]
            except (KeyError, TypeError):
                continue
            x, y = transformer.transform(lon, lat)
            points = np.column_stack((x, y))
            tags = element.get("tags") or {}
            if not isinstance(tags, dict):
                continue
            if "building" in tags and len(points) >= 4:
                polygon = Polygon(points)
                if not polygon.is_valid:
                    polygon = polygon.buffer(0)
                clipped = polygon.intersection(clip)
                if clipped.geom_type == "Polygon":
                    buildings.append(np.asarray(clipped.exterior.coords, dtype=float))
                elif clipped.geom_type == "MultiPolygon":
                    buildings.extend(np.asarray(item.exterior.coords, dtype=float) for item in clipped.geoms)
            elif "highway" in tags:
                line = LineString(points).intersection(clip)
                if line.geom_type == "LineString":
                    roads.append(np.asarray(line.coords, dtype=float))
                elif line.geom_type == "MultiLineString":
                    roads.extend(np.asarray(item.coords, dtype=float) for item in line.geoms)
        if not buildings:
            raise ProviderUnavailableError("OSM fallback returned no building ways for requested area")
        provenance = ProviderProvenance.create(
            "osm",
            "OpenStreetMap Overpass",
            area.bounds,
            "© OpenStreetMap contributors",
            TERMS_URL,
            warnings=["Fallback data; completeness and geometry quality vary by area."],
            source_details={
                "endpoint": OVERPASS,
                "building_polygons": len(buildings),
                "road_lines": len(roads),
                "query_margin_m": margin_m,
                "tags": ["building", "highway"],
            },
            acquired_at_utc=acquired_at_utc,
        )
        result = OsmVectors(buildings, roads, provenance)
        if out_dir is not None:
            self._write_legacy(result, Path(out_dir))
        return result

    @staticmethod
    def _write_legacy(result: OsmVectors, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out / "buildings.npz", buildings=np.asarray(result.buildings, dtype=object))
        np.savez_compressed(out / "basemap_vectors.npz", roads=np.asarray(result.road_lines, dtype=object),
                            road_polygons=np.asarray([], dtype=object), rail=np.asarray([], dtype=object),
                            water=np.asarray([], dtype=object), admin=np.asarray([], dtype=object))
        write_json(out / "vectors_manifest.json", result.legacy_manifest())


OSMProvider = OsmProvider
