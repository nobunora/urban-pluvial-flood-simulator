"""Build the packaged JMA station and historical rainfall catalogs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from floodsim.providers.common import DEFAULT_NETWORK_POLICY, make_session, request_with_retry
from floodsim.providers.jma import (
    catalog_payload,
    JMA_STATION_SOURCE_URL,
    JmaRainfallEvent,
    parse_amedas_csv,
    parse_jma_ranking_html,
)

DEFAULT_RANKING_SOURCES = (
    (
        "44173",
        "大島北ノ山",
        "https://www.data.jma.go.jp/stats/etrn/view/rank_a.php?block_no=1467&day=&month=&prec_no=44&view=a2&year=",
    ),
    (
        "44132",
        "東京",
        "https://www.data.jma.go.jp/stats/etrn/view/rank_s.php?prec_no=44&block_no=47662&year=&month=&day=&view=a2",
    ),
)
REQUIRED_RAINFALL_DURATIONS = frozenset({10, 60, 1440})


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_official_jma_url(url: str, *, label: str) -> str:
    """Accept only HTTPS URLs hosted by JMA itself.

    The Phase 2B maintenance generator is intentionally restricted to official
    JMA sources. Snapshot mode may read bytes locally, but the recorded source
    URL must still identify an official JMA origin.
    """
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} URL is malformed") from exc

    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme.casefold() != "https" or not host:
        raise ValueError(f"{label} URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} URL must not contain credentials")
    if port not in (None, 443):
        raise ValueError(f"{label} URL must use the standard HTTPS port")
    if host != "jma.go.jp" and not host.endswith(".jma.go.jp"):
        raise ValueError(f"{label} URL must use an official jma.go.jp host")
    return url


def _fetch(url: str):
    _require_official_jma_url(url, label="source")
    session = make_session(DEFAULT_NETWORK_POLICY)
    return request_with_retry(session, "GET", url, policy=DEFAULT_NETWORK_POLICY)


def _parse_source_spec(spec: str) -> tuple[str, str, str]:
    parts = spec.split("|", 2)
    if len(parts) != 3 or any(not part.strip() for part in parts):
        raise ValueError("ranking source must be STATION_ID|STATION_NAME|URL")
    url = _require_official_jma_url(parts[2].strip(), label="ranking source")
    return parts[0].strip(), parts[1].strip(), url


def _parse_snapshot_spec(spec: str) -> tuple[str, str, str, Path]:
    parts = spec.split("|", 3)
    if len(parts) != 4 or any(not part.strip() for part in parts):
        raise ValueError("ranking input must be STATION_ID|STATION_NAME|HTTPS_URL|PATH")
    station_id, station_name, source_url = _parse_source_spec("|".join(parts[:3]))
    return station_id, station_name, source_url, Path(parts[3].strip())


def _read_snapshot(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError(f"snapshot input cannot be read: {path}") from exc


def build_catalog(
    *,
    station_payload: bytes,
    station_source_url: str,
    ranking_payloads: list[tuple[str, str, str, bytes]],
    generated_at_utc: str,
    station_limit: int | None = None,
) -> tuple[dict, dict]:
    """Build deterministic catalogs from official JMA sources only."""
    _require_official_jma_url(station_source_url, label="station source")
    stations = parse_amedas_csv(
        station_payload,
        source_url=station_source_url,
        catalog_generated_at_utc=generated_at_utc,
    )
    if station_limit is not None:
        if station_limit <= 0:
            raise ValueError("station_limit must be positive")
        stations = stations[:station_limit]

    station_by_id = {station.station_id: station for station in stations}
    events: list[JmaRainfallEvent] = []
    for station_id, station_name, source_url, payload in ranking_payloads:
        _require_official_jma_url(source_url, label="ranking source")
        station = station_by_id.get(station_id)
        if station is None:
            raise ValueError(f"ranking station {station_id} is not in the AMeDAS catalog")
        if station.name != station_name:
            raise ValueError(
                f"ranking station name {station_name!r} does not match AMeDAS name {station.name!r} for {station_id}"
            )
        parsed_events = parse_jma_ranking_html(
            payload,
            station_id=station_id,
            station_name=station_name,
            station_lon_deg=station.lon_deg,
            station_lat_deg=station.lat_deg,
            source_url=source_url,
            catalog_generated_at_utc=generated_at_utc,
        )
        if not parsed_events:
            raise ValueError(f"ranking source {source_url} has no recognized required rainfall rows")

        parsed_durations = {event.duration_minutes for event in parsed_events}
        missing_durations = REQUIRED_RAINFALL_DURATIONS - parsed_durations
        if missing_durations:
            missing = ", ".join(str(duration) for duration in sorted(missing_durations))
            raise ValueError(
                f"ranking source {source_url} is missing required rainfall durations: {missing} minutes"
            )
        events.extend(parsed_events)

    if not events:
        raise ValueError("no JMA rainfall events were parsed")
    return catalog_payload(stations, events, generated_at_utc)


def _write_catalog(output_dir: Path, stations: dict, events: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (("stations.json", stations), ("rainfall_extremes.json", events)):
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/jma"))
    parser.add_argument("--station-url", default=JMA_STATION_SOURCE_URL)
    parser.add_argument(
        "--station-input",
        type=Path,
        help="local station CSV/ZIP snapshot; omit to fetch the official station archive",
    )
    parser.add_argument(
        "--ranking-input",
        action="append",
        help="STATION_ID|STATION_NAME|HTTPS_URL|PATH; may be repeated",
    )
    parser.add_argument(
        "--ranking-source",
        action="append",
        help="STATION_ID|STATION_NAME|HTTPS_URL; may be repeated",
    )
    parser.add_argument("--station-limit", type=int, help="focused test limit; omit for the full station catalog")
    parser.add_argument("--generated-at-utc", default=None)
    args = parser.parse_args()

    if args.ranking_input and args.ranking_source:
        parser.error("--ranking-input and --ranking-source cannot be combined")

    station_source_url = _require_official_jma_url(args.station_url, label="station source")
    generated_at = args.generated_at_utc or _now_utc()
    station_payload = _read_snapshot(args.station_input) if args.station_input else _fetch(station_source_url).content
    if args.ranking_input:
        ranking_payloads = [
            (station_id, station_name, url, _read_snapshot(path))
            for station_id, station_name, url, path in (_parse_snapshot_spec(spec) for spec in args.ranking_input)
        ]
    else:
        source_specs = (
            [_parse_source_spec(spec) for spec in args.ranking_source]
            if args.ranking_source
            else list(DEFAULT_RANKING_SOURCES)
        )
        ranking_payloads = [
            (station_id, station_name, url, _fetch(url).content)
            for station_id, station_name, url in source_specs
        ]

    stations, events = build_catalog(
        station_payload=station_payload,
        station_source_url=station_source_url,
        ranking_payloads=ranking_payloads,
        generated_at_utc=generated_at,
        station_limit=args.station_limit,
    )
    _write_catalog(args.output_dir, stations, events)


if __name__ == "__main__":
    main()
