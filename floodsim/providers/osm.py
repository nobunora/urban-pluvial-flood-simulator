"""OpenStreetMap building/highway acquisition for the PLATEAU fallback path."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, box  # type: ignore[import-untyped]\nfrom shapely.ops import polygonize, unary_union  # type: ignore[import-untyped]

from floodsim.domain.geometry import AnalysisArea
from floodsim.providers.common import (
    DEFAULT_NETWORK_POLICY,
    NetworkPolicy,
    ProviderParseError,
    ProviderProvenance,
    ProviderTimeoutError,
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


def _check_deadline(deadline_monotonic: float | None, operation: str) -> None:
    if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
        raise ProviderTimeoutError(f"{operation} exceeded provider time budget")


@dataclass
class OsmVectors:
    buildings: list[np.ndarray]
    road_lines: list[np.ndarray]
    provenance: ProviderProvenance

    @property
    def road_polygons(self) -> list[np.ndarray]:
        """Match the full-grid vector contract; OSM currently supplies road lines only."""
        return []

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
        "query_revision": "building-relation-v4",
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
        time_budget_s: float | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> OsmVectors:
        if time_budget_s is not None and time_budget_s <= 0:
            raise ValueError("time_budget_s must be positive")
        deadline = None if time_budget_s is None else time.monotonic() + time_budget_s
        if progress_callback is not None:
            progress_callback(0.03, "OSM Overpassへ建物・building:part・道路を問い合わせ中")
        lon1, lat1, lon2, lat2 = local_bbox(area, margin_m)
        bbox = f"{lat1:.8f},{lon1:.8f},{lat2:.8f},{lon2:.8f}"
        query_timeout_s = (
            OVERPASS_QUERY_TIMEOUT_S
            if time_budget_s is None
            else max(1, min(OVERPASS_QUERY_TIMEOUT_S, int(time_budget_s)))
        )
        query = f'''[out:json][timeout:{query_timeout_s}];
(
  way["building"]({bbox});
  way["building:part"]({bbox});
  relation["building"]({bbox});
  relation["building:part"]({bbox});
  way["highway"]({bbox});
);
out geom;'''
        cache_file = _cache_path(Path(cache_dir), area, margin_m)
        if cache_file.exists():
            _check_deadline(deadline, "OSM cache read")
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProviderParseError("cached OSM response is invalid") from exc
            _check_deadline(deadline, "OSM cache parse")
        else:
            if self.sleeper is None:
                response = request_with_retry(
                    self.session,
                    "POST",
                    OVERPASS,
                    policy=self.policy,
                    data={"data": query},
                    deadline_monotonic=deadline,
                )
            else:
                response = request_with_retry(
                    self.session,
                    "POST",
                    OVERPASS,
                    policy=self.policy,
                    sleeper=self.sleeper,
                    data={"data": query},
                    deadline_monotonic=deadline,
                )
            payload = read_json(response, "OSM Overpass")
            _check_deadline(deadline, "OSM response parse")
            if progress_callback is not None:
                progress_callback(0.18, "OSM応答受信完了 / ジオメトリ変換を開始")
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
            raise ProviderParseError("OSM Overpass response has no elements list")
        transformer = Transformer.from_crs("EPSG:4326", local_crs(area), always_xy=True)
        clip = box(-area.width_m / 2.0 - 20.0, -area.height_m / 2.0 - 20.0,
                   area.width_m / 2.0 + 20.0, area.height_m / 2.0 + 20.0)
        buildings: list[np.ndarray] = []
        roads: list[np.ndarray] = []
        elements = payload["elements"]
        total_elements = len(elements)
        callback_step = max(1, total_elements // 20)

        def append_building_geometry(geometry: object) -> None:
            if not isinstance(geometry, list) or len(geometry) < 4:
                return
            try:
                lon = [point["lon"] for point in geometry]
                lat = [point["lat"] for point in geometry]
            except (KeyError, TypeError):
                return
            x, y = transformer.transform(lon, lat)
            polygon = Polygon(np.column_stack((x, y)))
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            clipped = polygon.intersection(clip)
            if clipped.geom_type == "Polygon":
                buildings.append(np.asarray(clipped.exterior.coords, dtype=float))
            elif clipped.geom_type == "MultiPolygon":
                buildings.extend(
                    np.asarray(item.exterior.coords, dtype=float)
                    for item in clipped.geoms
                    if not item.is_empty
                )

        for element_index, element in enumerate(elements):
            if element_index % 128 == 0:
                _check_deadline(deadline, "OSM geometry processing")
            if not isinstance(element, dict):
                continue
            tags = element.get("tags") or {}
            if not isinstance(tags, dict):
                continue

            is_building = "building" in tags or "building:part" in tags
            if is_building:
                if element.get("type") != "relation":
                    append_building_geometry(element.get("geometry") or [])
                else:
                    # Overpass relation members may each be only a fragment of a
                    # multipolygon ring. Assemble all outer/inner linework before
                    # polygonization instead of treating every member as a polygon.
                    role_lines: dict[str, list[LineString]] = {"outer": [], "inner": []}
                    for member in element.get("members") or []:
                        if not isinstance(member, dict):
                            continue
                        role = member.get("role") or "outer"
                        if role not in role_lines:
                            continue
                        geometry = member.get("geometry") or []
                        if not isinstance(geometry, list) or len(geometry) < 2:
                            continue
                        try:
                            lon = [point["lon"] for point in geometry]
                            lat = [point["lat"] for point in geometry]
                        except (KeyError, TypeError):
                            continue
                        x, y = transformer.transform(lon, lat)
                        role_lines[role].append(LineString(np.column_stack((x, y))))

                    outer_polygons = list(polygonize(unary_union(role_lines["outer"])))
                    if outer_polygons:
                        relation_geometry = unary_union(outer_polygons)
                        inner_polygons = list(polygonize(unary_union(role_lines["inner"])))
                        if inner_polygons:
                            relation_geometry = relation_geometry.difference(
                                unary_union(inner_polygons)
                            )
                        clipped = relation_geometry.intersection(clip)
                        if clipped.geom_type == "Polygon":
                            buildings.append(
                                np.asarray(clipped.exterior.coords, dtype=float)
                            )
                        elif clipped.geom_type == "MultiPolygon":
                            buildings.extend(
                                np.asarray(item.exterior.coords, dtype=float)
                                for item in clipped.geoms
                                if not item.is_empty
                            )
            elif "highway" in tags:
                geometry = element.get("geometry") or []
                if isinstance(geometry, list) and len(geometry) >= 2:
                    try:
                        lon = [point["lon"] for point in geometry]
                        lat = [point["lat"] for point in geometry]
                    except (KeyError, TypeError):
                        continue
                    x, y = transformer.transform(lon, lat)
                    line = LineString(np.column_stack((x, y))).intersection(clip)
                    if line.geom_type == "LineString":
                        roads.append(np.asarray(line.coords, dtype=float))
                    elif line.geom_type == "MultiLineString":
                        roads.extend(np.asarray(item.coords, dtype=float) for item in line.geoms)

            processed = element_index + 1
            if progress_callback is not None and (
                processed == total_elements or processed % callback_step == 0
            ):
                progress_callback(
                    0.18 + 0.77 * processed / max(1, total_elements),
                    f"OSM {processed}/{total_elements}要素処理済み / "
                    f"建物{len(buildings)}件・道路{len(roads)}件 / "
                    f"残り{total_elements - processed}要素",
                )
        _check_deadline(deadline, "OSM geometry processing")
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
                "tags": ["building", "building:part", "building relation", "building:part relation", "highway"],
                "building_geometry_detail": "native-full-detail",
                "map_zoom_dependent": False,
                "geometry_simplification": "none",
            },
            acquired_at_utc=acquired_at_utc,
        )
        result = OsmVectors(buildings, roads, provenance)
        _check_deadline(deadline, "OSM acquisition")
        if out_dir is not None:
            self._write_legacy(result, Path(out_dir))
        if progress_callback is not None:
            progress_callback(
                1.0,
                f"OSM取得完了 / 建物{len(buildings)}件・道路{len(roads)}件",
            )
        _check_deadline(deadline, "OSM acquisition")
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
