"""Shared provider contracts, local coordinate helpers, and network policy."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pyproj import CRS, Transformer

from floodsim.domain.geometry import AnalysisArea, GeoBounds

NETWORK_USER_AGENT = "urban-pluvial-flood-simulator/0.1"
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class NetworkPolicy:
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 60.0
    max_attempts: int = 3
    backoff_seconds: tuple[float, ...] = (1.0, 2.0)
    retryable_status_codes: frozenset[int] = RETRYABLE_STATUS_CODES
    user_agent: str = NETWORK_USER_AGENT

    @property
    def timeout(self) -> tuple[float, float]:
        return self.connect_timeout_s, self.read_timeout_s


DEFAULT_NETWORK_POLICY = NetworkPolicy()


class ProviderError(RuntimeError):
    """Base class for expected provider failures."""

    code = "PROVIDER_ERROR"
    retryable = False


class ProviderUnavailableError(ProviderError):
    code = "PROVIDER_UNAVAILABLE"


class ProviderRequestError(ProviderError):
    code = "PROVIDER_REQUEST_FAILED"
    retryable = True


class ProviderParseError(ProviderError):
    code = "PROVIDER_PARSE_FAILED"


class ProviderCoverageError(ProviderError):
    code = "PROVIDER_COVERAGE_INCOMPLETE"


@dataclass(frozen=True)
class ProviderProvenance:
    provider_id: str
    provider_name: str
    requested_bounds: dict[str, float]
    acquired_at_utc: str
    attribution: str
    terms_url: str
    warnings: list[str] = field(default_factory=list)
    source_details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        provider_id: str,
        provider_name: str,
        bounds: GeoBounds,
        attribution: str,
        terms_url: str,
        *,
        warnings: list[str] | None = None,
        source_details: Mapping[str, Any] | None = None,
        acquired_at_utc: str | None = None,
    ) -> ProviderProvenance:
        timestamp = acquired_at_utc or datetime.now(timezone.utc).isoformat()
        return cls(
            provider_id=provider_id,
            provider_name=provider_name,
            requested_bounds={
                "west_deg": bounds.west_deg,
                "south_deg": bounds.south_deg,
                "east_deg": bounds.east_deg,
                "north_deg": bounds.north_deg,
            },
            acquired_at_utc=timestamp,
            attribution=attribution,
            terms_url=terms_url,
            warnings=list(warnings or []),
            source_details=dict(source_details or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable structure without machine-specific paths."""
        return asdict(self)


def make_session(policy: NetworkPolicy = DEFAULT_NETWORK_POLICY) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": policy.user_agent})
    return session


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    policy: NetworkPolicy = DEFAULT_NETWORK_POLICY,
    sleeper: Callable[[float], None] = time.sleep,
    accepted_statuses: frozenset[int] = frozenset(),
    **kwargs: Any,
) -> requests.Response:
    """Request with the single Phase 2A retry policy.

    A test can pass a no-op sleeper; production defaults retain the prescribed
    one- and two-second backoff between attempts.
    """
    kwargs.setdefault("timeout", policy.timeout)
    last_error: BaseException | None = None
    for attempt in range(policy.max_attempts):
        try:
            response = session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            last_error = exc
            if attempt + 1 >= policy.max_attempts:
                raise ProviderRequestError(f"{method} {url} failed after retries") from exc
            if attempt < len(policy.backoff_seconds):
                sleeper(policy.backoff_seconds[attempt])
            continue
        if response.status_code in accepted_statuses:
            return response
        if response.status_code in policy.retryable_status_codes and attempt + 1 < policy.max_attempts:
            if attempt < len(policy.backoff_seconds):
                sleeper(policy.backoff_seconds[attempt])
            continue
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderRequestError(f"{method} {url} returned HTTP {response.status_code}")
        return response
    raise ProviderRequestError(f"{method} {url} failed after retries") from last_error


def read_json(response: requests.Response, source: str) -> Any:
    try:
        return response.json()
    except (ValueError, TypeError) as exc:
        raise ProviderParseError(f"{source} returned invalid JSON") from exc


def local_crs(area: AnalysisArea) -> CRS:
    return CRS.from_proj4(
        f"+proj=aeqd +lat_0={area.center.lat_deg} +lon_0={area.center.lon_deg} "
        "+datum=WGS84 +units=m +no_defs"
    )


def local_extent(area: AnalysisArea, margin_m: float = 0.0) -> tuple[float, float, float, float]:
    if margin_m < 0:
        raise ValueError("margin_m must not be negative")
    return (
        -area.width_m / 2.0 - margin_m,
        -area.height_m / 2.0 - margin_m,
        area.width_m / 2.0 + margin_m,
        area.height_m / 2.0 + margin_m,
    )


def area_lonlat_bounds(area: AnalysisArea, margin_m: float = 0.0) -> tuple[float, float, float, float]:
    """Convert the rectangular local extent to a WGS84 bounding box."""
    to_ll = Transformer.from_crs(local_crs(area), CRS.from_epsg(4326), always_xy=True)
    xmin, ymin, xmax, ymax = local_extent(area, margin_m)
    points = [to_ll.transform(x, y) for x, y in ((xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax))]
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return min(lons), min(lats), max(lons), max(lats)


def area_from_square(center_lat: float, center_lon: float, half_size_m: float) -> AnalysisArea:
    if half_size_m <= 0:
        raise ValueError("half_size_m must be positive")
    west, south, east, north = area_lonlat_bounds_from_center(center_lat, center_lon, half_size_m)
    from floodsim.domain.geometry import LonLat

    return AnalysisArea(
        mode="preset_square" if half_size_m in {250, 500, 1000, 2000} else "rectangle",
        bounds=GeoBounds(west_deg=west, south_deg=south, east_deg=east, north_deg=north),
        center=LonLat(lon_deg=center_lon, lat_deg=center_lat),
        width_m=2.0 * half_size_m,
        height_m=2.0 * half_size_m,
        area_m2=4.0 * half_size_m * half_size_m,
    )


def area_lonlat_bounds_from_center(center_lat: float, center_lon: float, half_size_m: float) -> tuple[float, float, float, float]:
    from floodsim.domain.geometry import LonLat

    area = AnalysisArea.model_construct(
        mode="rectangle",
        bounds=GeoBounds.model_construct(west_deg=-180.0, south_deg=-90.0, east_deg=180.0, north_deg=90.0),
        center=LonLat(lon_deg=center_lon, lat_deg=center_lat),
        width_m=2.0 * half_size_m,
        height_m=2.0 * half_size_m,
        area_m2=4.0 * half_size_m * half_size_m,
    )
    return area_lonlat_bounds(area)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
