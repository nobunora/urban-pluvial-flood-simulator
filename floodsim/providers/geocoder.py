"""CSIS simple geocoding provider."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass

import requests

from floodsim.providers.common import (
    DEFAULT_NETWORK_POLICY,
    NetworkPolicy,
    ProviderParseError,
    make_session,
    request_with_retry,
)

CSIS_PROVIDER_ID = "csis_simple_geocoding"
CSIS_ENDPOINT = "https://geocode.csis.u-tokyo.ac.jp/cgi-bin/simple_geocode.cgi"
CSIS_ATTRIBUTION_TEXT = "CSISシンプルジオコーディング実験を利用"
CSIS_ATTRIBUTION_URL = "https://geocode.csis.u-tokyo.ac.jp/"
MAX_GEOCODE_CANDIDATES = 10
_WGS84_GEODETICS = frozenset({"wgs1984", "wgs84", "epsg:4326"})


@dataclass(frozen=True)
class GeocodeCandidate:
    title: str
    lon: float
    lat: float
    provider: str = CSIS_PROVIDER_ID
    confidence: int | None = None
    level: int | None = None
    converted: str | None = None


@dataclass(frozen=True)
class GeocodeResult:
    candidates: list[GeocodeCandidate]
    attribution_text: str = CSIS_ATTRIBUTION_TEXT
    attribution_url: str = CSIS_ATTRIBUTION_URL


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if child is element or _local_name(child.tag) != name:
            continue
        text = (child.text or "").strip()
        return text or None
    return None


def _direct_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) != name:
            continue
        text = (child.text or "").strip()
        return text or None
    return None


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _coordinate(value: str | None, name: str, lower: float, upper: float) -> float:
    if value is None:
        raise ProviderParseError(f"CSIS candidate is missing {name}")
    try:
        coordinate = float(value)
    except ValueError as exc:
        raise ProviderParseError(f"CSIS candidate has invalid {name}") from exc
    if not math.isfinite(coordinate) or not lower <= coordinate <= upper:
        raise ProviderParseError(f"CSIS candidate has out-of-range {name}")
    return coordinate


def parse_csis_xml(payload: bytes | str, *, max_candidates: int = MAX_GEOCODE_CANDIDATES) -> GeocodeResult:
    """Parse a CSIS XML response while exposing no raw provider payload."""
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, ValueError, TypeError) as exc:
        raise ProviderParseError("CSIS returned malformed XML") from exc

    geodetic = _direct_text(root, "geodetic")
    if geodetic is None or geodetic.casefold() not in _WGS84_GEODETICS:
        raise ProviderParseError("CSIS returned an unsupported coordinate system")

    confidence = _optional_int(_direct_text(root, "iConf"))
    converted = _direct_text(root, "converted")
    candidates: list[GeocodeCandidate] = []
    for element in root.iter():
        if _local_name(element.tag) != "candidate":
            continue
        title = _child_text(element, "address")
        if not title:
            raise ProviderParseError("CSIS candidate is missing an address")
        candidates.append(
            GeocodeCandidate(
                title=title,
                lon=_coordinate(_child_text(element, "longitude"), "longitude", -180.0, 180.0),
                lat=_coordinate(_child_text(element, "latitude"), "latitude", -90.0, 90.0),
                confidence=confidence,
                level=_optional_int(_child_text(element, "iLvl")),
                converted=converted,
            )
        )
        if len(candidates) >= max_candidates:
            break
    return GeocodeResult(candidates=candidates)


class CsisSimpleGeocoder:
    """Fetch and normalize results from the single approved CSIS endpoint."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        policy: NetworkPolicy = DEFAULT_NETWORK_POLICY,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.policy = policy
        self.session = session or make_session(policy)
        self.sleeper = sleeper

    def search(self, query: str) -> GeocodeResult:
        trimmed = query.strip()
        if not trimmed:
            raise ValueError("query must not be empty")
        params = {"addr": trimmed, "charset": "UTF8", "series": "ADDRESS"}
        if self.sleeper is None:
            response = request_with_retry(self.session, "GET", CSIS_ENDPOINT, policy=self.policy, params=params)
        else:
            response = request_with_retry(
                self.session, "GET", CSIS_ENDPOINT, policy=self.policy, sleeper=self.sleeper, params=params
            )
        return parse_csis_xml(response.content)


CSISGeocoder = CsisSimpleGeocoder
