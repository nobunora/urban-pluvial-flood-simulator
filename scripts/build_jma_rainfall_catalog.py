"""Build the packaged JMA station and historical rainfall catalogs."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from floodsim.providers.common import (
    DEFAULT_NETWORK_POLICY,
    make_session,
    request_with_retry,
)
from floodsim.providers.jma import (
    JMA_STATION_SOURCE_URL,
    JmaRainfallEvent,
    catalog_payload,
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
DEFAULT_EVENT_DURATIONS: Mapping[str, frozenset[int]] = {
    "44173": frozenset({10, 1440}),
    "44132": frozenset({60}),
}
DEFAULT_EVENT_MAX_RANK = 2


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch(url: str):
    session = make_session(DEFAULT_NETWORK_POLICY)
    return request_with_retry(session, "GET", url, policy=DEFAULT_NETWORK_POLICY)


def _parse_source_spec(spec: str) -> tuple[str, str, str]:
    parts = spec.split("|", 2)
    if len(parts) != 3 or any(not part.strip() for part in parts):
        raise ValueError("ranking source must be STATION_ID|STATION_NAME|URL")
    url = parts[2].strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("ranking source URL must be HTTPS")
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
    allowed_durations_by_station: Mapping[str, frozenset[int]] | None = None,
    max_rank: int | None = None,
) -> tuple[dict, dict]:
    if max_rank is not None and max_rank <= 0:
        raise ValueError("max_rank must be positive")
    stations = parse_amedas_csv(
        station_payload,
        source_url=station_source_url,
        catalog_generated_at_utc=generated_at_utc,
    )
    if station_limit is not None:
        if station_limit <= 0:
            raise ValueError("station_limit must be positive")
        stations = stations[:station_limit]
    station_ids = {station.station_id for station in stations}
    events: list[JmaRainfallEvent] = []
    for station_id, station_name, source_url, payload in ranking_payloads:
        if station_id not in station_ids:
            raise ValueError(f"ranking station {station_id} is not in the AMeDAS catalog")
        parsed_events = parse_jma_ranking_html(
            payload,
            station_id=station_id,
            station_name=station_name,
            source_url=source_url,
            catalog_generated_at_utc=generated_at_utc,
        )
        if not parsed_events:
            raise ValueError(f"ranking source {source_url} has no recognized required rainfall rows")
        if allowed_durations_by_station is not None:
            if station_id not in allowed_durations_by_station:
                raise ValueError(f"no duration selection is configured for ranking station {station_id}")
            parsed_events = [
                event
                for event in parsed_events
                if event.duration_minutes in allowed_durations_by_station[station_id]
            ]
        if max_rank is not None:
            parsed_events = [
                event for event in parsed_events if event.rank is None or event.rank <= max_rank
            ]
        if not parsed_events:
            raise ValueError(f"ranking source {source_url} has no events after deterministic selection")
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
        help="local station CSV snapshot; omit to fetch the official station archive",
    )
    ranking_inputs = parser.add_mutually_exclusive_group()
    ranking_inputs.add_argument(
        "--ranking-input",
        action="append",
        help="STATION_ID|STATION_NAME|HTTPS_URL|PATH; may be repeated",
    )
    parser.add_argument(
        "--default-selection",
        action="store_true",
        help="apply the documented packaged-catalog duration and rank selection",
    )
    parser.add_argument(
        "--ranking-source",
        action="append",
        help="STATION_ID|STATION_NAME|HTTPS_URL; may be repeated",
    )
    parser.add_argument("--station-limit", type=int, help="focused test limit; omit for the full station catalog")
    parser.add_argument("--generated-at-utc", default=None)
    args = parser.parse_args()

    generated_at = args.generated_at_utc or _now_utc()
    station_payload = _read_snapshot(args.station_input) if args.station_input else _fetch(args.station_url).content
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
    use_default_selection = args.default_selection or (
        not args.ranking_source and not args.ranking_input
    )
    stations, events = build_catalog(
        station_payload=station_payload,
        station_source_url=args.station_url,
        ranking_payloads=ranking_payloads,
        generated_at_utc=generated_at,
        station_limit=args.station_limit,
        allowed_durations_by_station=DEFAULT_EVENT_DURATIONS if use_default_selection else None,
        max_rank=DEFAULT_EVENT_MAX_RANK if use_default_selection else None,
    )
    _write_catalog(args.output_dir, stations, events)


if __name__ == "__main__":
    main()
