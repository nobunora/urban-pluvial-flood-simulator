"""JMA catalog parsing and local runtime loading."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import re
import unicodedata
import zipfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from floodsim.providers.common import ProviderParseError, ProviderUnavailableError

JMA_STATION_SOURCE_URL = "https://www.jma.go.jp/jma/kishou/know/amedas/ame_master.zip"
JMA_EARTH_RADIUS_KM = 6371.0088
CATALOG_SCHEMA_VERSION = "1"
PRECIPITATION_STATION_TYPES = frozenset({"四", "三", "官", "雨"})
_RANK_LABEL_DURATIONS = {
    "日最大10分間降水量の多い方から": 10,
    "日最大10分間降水量(mm)": 10,
    "日最大1時間降水量(10分間隔)の多い方から": 60,
    "日最大1時間降水量(10分間隔)の多い方から(mm)": 60,
    "日最大1時間降水量(mm)": 60,
    "日降水量": 1440,
    "日降水量の多い方から": 1440,
    "日降水量(mm)": 1440,
}
_RANK_VALUE_RE = re.compile(r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<flags>[^\s(]*)")
_DATE_RE = re.compile(r"\((?P<date>\d{4}/\d{1,2}/\d{1,2}(?:\s+\d{1,2}:\d{2})?)\)")


class JmaCatalogError(ProviderParseError):
    """The packaged JMA catalog is missing, corrupt, or inconsistent."""


@dataclass(frozen=True)
class JmaStation:
    station_id: str
    name: str
    prefecture_or_region: str | None
    lon_deg: float
    lat_deg: float
    precipitation_capable: bool
    source_url: str
    catalog_generated_at_utc: str


@dataclass(frozen=True)
class JmaRainfallEvent:
    event_id: str
    station_id: str
    station_name: str
    station_lon_deg: float
    station_lat_deg: float
    duration_minutes: int
    total_precipitation_mm: float
    rank: int | None
    event_date_or_datetime_metadata: str | None
    source_url: str
    catalog_generated_at_utc: str
    data_quality_flags: list[str]
    profile_available: bool = False
    profile_id: str | None = None

    @property
    def intensity_mm_per_h(self) -> float:
        return self.total_precipitation_mm / (self.duration_minutes / 60.0)


@dataclass(frozen=True)
class JmaCatalog:
    stations: tuple[JmaStation, ...]
    events: tuple[JmaRainfallEvent, ...]

    def station(self, station_id: str) -> JmaStation | None:
        return next((station for station in self.stations if station.station_id == station_id), None)

    def event(self, event_id: str) -> JmaRainfallEvent | None:
        return next((event for event in self.events if event.event_id == event_id), None)

    def extremes(self, station_id: str) -> list[JmaRainfallEvent]:
        return sorted((event for event in self.events if event.station_id == station_id), key=_event_sort_key)

    def nearest_stations(self, lon_deg: float, lat_deg: float, limit: int = 5) -> list[tuple[JmaStation, float]]:
        _validate_coordinates(lon_deg, lat_deg)
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        candidates = (
            (station, haversine_distance_km(lon_deg, lat_deg, station.lon_deg, station.lat_deg))
            for station in self.stations
            if station.precipitation_capable
        )
        return sorted(candidates, key=lambda item: (item[1], item[0].station_id))[:limit]


def _event_sort_key(event: JmaRainfallEvent) -> tuple[int, float, str]:
    return (0 if event.rank is not None else 1, float(event.rank) if event.rank is not None else math.inf, event.event_id)


def _validate_coordinates(lon_deg: float, lat_deg: float) -> None:
    if not math.isfinite(lon_deg) or not -180.0 <= lon_deg <= 180.0:
        raise ValueError("longitude must be finite and within -180..180")
    if not math.isfinite(lat_deg) or not -90.0 <= lat_deg <= 90.0:
        raise ValueError("latitude must be finite and within -90..90")


def haversine_distance_km(lon1_deg: float, lat1_deg: float, lon2_deg: float, lat2_deg: float) -> float:
    """Return deterministic great-circle distance in kilometres."""
    _validate_coordinates(lon1_deg, lat1_deg)
    _validate_coordinates(lon2_deg, lat2_deg)
    lon1, lat1, lon2, lat2 = (math.radians(value) for value in (lon1_deg, lat1_deg, lon2_deg, lat2_deg))
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    haversine = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return JMA_EARTH_RADIUS_KM * 2.0 * math.asin(math.sqrt(min(1.0, haversine)))


def _generated_timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat()


def _decode_station_csv(payload: bytes | str) -> str:
    if isinstance(payload, str):
        return payload
    if payload.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                csv_names = sorted(name for name in archive.namelist() if name.lower().endswith(".csv"))
                if len(csv_names) != 1:
                    raise JmaCatalogError("JMA station archive must contain exactly one CSV")
                payload = archive.read(csv_names[0])
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            raise JmaCatalogError("JMA station archive is corrupt") from exc
    for encoding in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise JmaCatalogError("JMA station CSV encoding is unsupported")


def parse_amedas_csv(
    payload: bytes | str,
    *,
    source_url: str = JMA_STATION_SOURCE_URL,
    catalog_generated_at_utc: str | None = None,
) -> list[JmaStation]:
    """Parse the official AMeDAS master CSV and retain rain-capable stations."""
    text = _decode_station_csv(payload)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 11:
        raise JmaCatalogError("JMA station CSV has no verifiable header")
    header = [unicodedata.normalize("NFKC", cell).replace(" ", "") for cell in rows[0]]
    required = ((1, "観測所番号"), (2, "種類"), (3, "観測所名"), (7, "緯度"), (9, "経度"))
    if any(index >= len(header) or label not in header[index] for index, label in required):
        raise JmaCatalogError("JMA station CSV header does not match the official contract")

    timestamp = _generated_timestamp(catalog_generated_at_utc)
    stations: list[JmaStation] = []
    seen: set[str] = set()
    for row in rows[1:]:
        if len(row) < 11 or not row[1].strip() or row[2].strip() not in PRECIPITATION_STATION_TYPES:
            continue
        station_id = row[1].strip()
        if not re.fullmatch(r"\d{5}", station_id):
            raise JmaCatalogError("JMA station identifier is malformed")
        if station_id in seen:
            continue
        name = row[3].strip()
        if not name:
            raise JmaCatalogError("JMA station name is missing")
        try:
            lat_deg = float(row[7]) + float(row[8]) / 60.0
            lon_deg = float(row[9]) + float(row[10]) / 60.0
        except ValueError as exc:
            raise JmaCatalogError("JMA station coordinates are not numeric") from exc
        _validate_coordinates(lon_deg, lat_deg)
        seen.add(station_id)
        stations.append(
            JmaStation(
                station_id=station_id,
                name=name,
                prefecture_or_region=row[0].strip() or None,
                lon_deg=lon_deg,
                lat_deg=lat_deg,
                precipitation_capable=True,
                source_url=source_url,
                catalog_generated_at_utc=timestamp,
            )
        )
    if not stations:
        raise JmaCatalogError("JMA station CSV contains no precipitation-capable stations")
    return stations


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _normalize_rank_label(label: str) -> str:
    return "".join(unicodedata.normalize("NFKC", html.unescape(label)).split())


def _parse_rank_cell(raw: str) -> tuple[float, str | None, list[str]] | None:
    if not raw or raw in {"--", "///", "×", "-"}:
        return None
    match = _RANK_VALUE_RE.match(raw)
    if match is None:
        return None
    try:
        value = float(match.group("value"))
    except ValueError:
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    date_match = _DATE_RE.search(raw)
    date = date_match.group("date") if date_match else None
    flags_text = match.group("flags").strip()
    flags = [flags_text] if flags_text and flags_text not in {"-"} else []
    return value, date, flags


def make_event_id(
    station_id: str,
    duration_minutes: int,
    total_precipitation_mm: float,
    rank: int | None,
    event_date_or_datetime_metadata: str | None,
    source_url: str,
) -> str:
    identity = "|".join(
        (
            station_id,
            str(duration_minutes),
            format(total_precipitation_mm, ".15g"),
            str(rank) if rank is not None else "",
            event_date_or_datetime_metadata or "",
            source_url,
        )
    )
    return "jma-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def parse_jma_ranking_html(
    payload: bytes | str,
    *,
    station_id: str,
    station_name: str,
    station_lon_deg: float,
    station_lat_deg: float,
    source_url: str,
    catalog_generated_at_utc: str | None = None,
) -> list[JmaRainfallEvent]:
    """Parse explicitly mapped JMA rainfall rows and only their top-ten rank cells."""
    _validate_coordinates(station_lon_deg, station_lat_deg)
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    parser = _TableParser()
    try:
        parser.feed(text)
        parser.close()
    except (ValueError, AssertionError) as exc:
        raise JmaCatalogError("JMA ranking HTML could not be parsed") from exc
    if not parser.rows:
        raise JmaCatalogError("JMA ranking page contains no table rows")

    timestamp = _generated_timestamp(catalog_generated_at_utc)
    events: list[JmaRainfallEvent] = []
    for row in parser.rows:
        if len(row) < 2:
            continue
        duration = _RANK_LABEL_DURATIONS.get(_normalize_rank_label(row[0]))
        if duration is None:
            continue
        # JMA ranking pages contain ten ranked value cells followed by a
        # statistics-period column. Never interpret that trailing period as
        # an eleventh rainfall event.
        for rank, cell in enumerate(row[1:11], start=1):
            parsed = _parse_rank_cell(cell)
            if parsed is None:
                continue
            value, event_date, flags = parsed
            events.append(
                JmaRainfallEvent(
                    event_id=make_event_id(station_id, duration, value, rank, event_date, source_url),
                    station_id=station_id,
                    station_name=station_name,
                    station_lon_deg=station_lon_deg,
                    station_lat_deg=station_lat_deg,
                    duration_minutes=duration,
                    total_precipitation_mm=value,
                    rank=rank,
                    event_date_or_datetime_metadata=event_date,
                    source_url=source_url,
                    catalog_generated_at_utc=timestamp,
                    data_quality_flags=flags,
                    profile_available=False,
                    profile_id=None,
                )
            )
    return events


def _read_catalog_payload(path: Path, key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProviderUnavailableError("JMA catalog file is missing") from exc
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise JmaCatalogError("JMA catalog file is corrupt") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get(key), list):
        raise JmaCatalogError(f"JMA catalog does not contain a {key} list")
    if raw.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise JmaCatalogError("JMA catalog schema version is unsupported")
    if not all(isinstance(item, dict) for item in raw[key]):
        raise JmaCatalogError(f"JMA catalog {key} entries must be objects")
    return raw, raw[key]


def _required_string(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise JmaCatalogError(f"JMA catalog field {key} is missing")
    return value.strip()


def _number(item: dict[str, Any], key: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise JmaCatalogError(f"JMA catalog field {key} is not a finite number")
    number = float(value)
    if minimum is not None and number <= minimum:
        raise JmaCatalogError(f"JMA catalog field {key} must be greater than {minimum}")
    if maximum is not None and number > maximum:
        raise JmaCatalogError(f"JMA catalog field {key} is outside its range")
    return number


def _load_catalog(stations_path: Path, events_path: Path) -> JmaCatalog:
    station_root, station_items = _read_catalog_payload(stations_path, "stations")
    event_root, event_items = _read_catalog_payload(events_path, "events")
    station_timestamp = _required_string(station_root, "catalog_generated_at_utc")
    event_timestamp = _required_string(event_root, "catalog_generated_at_utc")

    stations: list[JmaStation] = []
    station_by_id: dict[str, JmaStation] = {}
    for item in station_items:
        station_id = _required_string(item, "station_id")
        if station_id in station_by_id:
            raise JmaCatalogError("JMA station IDs are duplicated")
        if item.get("precipitation_capable") is not True:
            raise JmaCatalogError("JMA catalog contains a non-precipitation station")
        lon = _number(item, "lon_deg", minimum=-180.000001, maximum=180.0)
        lat = _number(item, "lat_deg", minimum=-90.000001, maximum=90.0)
        _validate_coordinates(lon, lat)
        station = JmaStation(
            station_id=station_id,
            name=_required_string(item, "name"),
            prefecture_or_region=item.get("prefecture_or_region") if isinstance(item.get("prefecture_or_region"), str) else None,
            lon_deg=lon,
            lat_deg=lat,
            precipitation_capable=True,
            source_url=_required_string(item, "source_url"),
            catalog_generated_at_utc=_required_string(item, "catalog_generated_at_utc") if item.get("catalog_generated_at_utc") else station_timestamp,
        )
        stations.append(station)
        station_by_id[station_id] = station

    events: list[JmaRainfallEvent] = []
    event_ids: set[str] = set()
    for item in event_items:
        event_id = _required_string(item, "event_id")
        if event_id in event_ids:
            raise JmaCatalogError("JMA event IDs are duplicated")
        event_ids.add(event_id)
        station_id = _required_string(item, "station_id")
        event_station = station_by_id.get(station_id)
        if event_station is None:
            raise JmaCatalogError("JMA event refers to an unknown station")
        station_name = _required_string(item, "station_name")
        station_lon = _number(item, "station_lon_deg", minimum=-180.000001, maximum=180.0)
        station_lat = _number(item, "station_lat_deg", minimum=-90.000001, maximum=90.0)
        _validate_coordinates(station_lon, station_lat)
        if station_name != event_station.name:
            raise JmaCatalogError("JMA event station name does not match station catalog")
        if not math.isclose(station_lon, event_station.lon_deg, rel_tol=0.0, abs_tol=1e-12) or not math.isclose(
            station_lat, event_station.lat_deg, rel_tol=0.0, abs_tol=1e-12
        ):
            raise JmaCatalogError("JMA event station coordinates do not match station catalog")
        duration = item.get("duration_minutes")
        if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
            raise JmaCatalogError("JMA event duration is invalid")
        total = _number(item, "total_precipitation_mm", minimum=0.0)
        rank = item.get("rank")
        if rank is not None and (isinstance(rank, bool) or not isinstance(rank, int) or not 1 <= rank <= 10):
            raise JmaCatalogError("JMA event rank is invalid")
        flags = item.get("data_quality_flags", [])
        if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
            raise JmaCatalogError("JMA event quality flags are invalid")
        profile_available = item.get("profile_available", False)
        if not isinstance(profile_available, bool):
            raise JmaCatalogError("JMA profile availability is invalid")
        profile_id = item.get("profile_id")
        if profile_id is not None and (not isinstance(profile_id, str) or not profile_id.strip()):
            raise JmaCatalogError("JMA profile ID is invalid")
        if profile_available and profile_id is None:
            raise JmaCatalogError("JMA available profile has no profile ID")
        event_metadata = item.get("event_date_or_datetime_metadata")
        if event_metadata is not None and not isinstance(event_metadata, str):
            raise JmaCatalogError("JMA event metadata must be a string or null")
        events.append(
            JmaRainfallEvent(
                event_id=event_id,
                station_id=station_id,
                station_name=station_name,
                station_lon_deg=station_lon,
                station_lat_deg=station_lat,
                duration_minutes=duration,
                total_precipitation_mm=total,
                rank=rank,
                event_date_or_datetime_metadata=event_metadata,
                source_url=_required_string(item, "source_url"),
                catalog_generated_at_utc=_required_string(item, "catalog_generated_at_utc") if item.get("catalog_generated_at_utc") else event_timestamp,
                data_quality_flags=list(flags),
                profile_available=profile_available,
                profile_id=profile_id,
            )
        )
    return JmaCatalog(tuple(stations), tuple(sorted(events, key=_event_sort_key)))


_catalog_cache: dict[tuple[Path, Path, tuple[int, int], tuple[int, int]], JmaCatalog] = {}


def _file_signature(path: Path) -> tuple[int, int]:
    try:
        stat = path.stat()
    except FileNotFoundError as exc:
        raise ProviderUnavailableError("JMA catalog file is missing") from exc
    return stat.st_mtime_ns, stat.st_size


def load_catalog(stations_path: Path | None = None, events_path: Path | None = None) -> JmaCatalog:
    """Load and validate packaged catalogs, caching each unchanged file pair."""
    data_dir = Path(__file__).resolve().parents[2] / "data" / "jma"
    stations = (stations_path or data_dir / "stations.json").resolve()
    events = (events_path or data_dir / "rainfall_extremes.json").resolve()
    key = (stations, events, _file_signature(stations), _file_signature(events))
    if key not in _catalog_cache:
        _catalog_cache[key] = _load_catalog(stations, events)
    return _catalog_cache[key]


class JmaCatalogProvider:
    def __init__(self, stations_path: Path | None = None, events_path: Path | None = None) -> None:
        self.stations_path = stations_path
        self.events_path = events_path

    def load(self) -> JmaCatalog:
        return load_catalog(self.stations_path, self.events_path)


def catalog_payload(
    stations: Iterable[JmaStation], events: Iterable[JmaRainfallEvent], generated_at: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    station_list = [asdict(station) for station in stations]
    event_list = [asdict(event) for event in sorted(events, key=_event_sort_key)]
    return (
        {"schema_version": CATALOG_SCHEMA_VERSION, "catalog_generated_at_utc": generated_at, "stations": station_list},
        {"schema_version": CATALOG_SCHEMA_VERSION, "catalog_generated_at_utc": generated_at, "events": event_list},
    )
