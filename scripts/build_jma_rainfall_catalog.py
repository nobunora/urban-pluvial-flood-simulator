"""Build the packaged JMA station and historical rainfall catalogs."""

from __future__ import annotations

import argparse
import json
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
        "https://www.data.jma.go.jp/stats/etrn/view/rank_a.php?block_no=47662&day=&month=&prec_no=44&view=np0&year=",
    ),
)


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


def build_catalog(
    *,
    station_payload: bytes,
    station_source_url: str,
    ranking_payloads: list[tuple[str, str, str, bytes]],
    generated_at_utc: str,
    station_limit: int | None = None,
) -> tuple[dict, dict]:
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
        "--ranking-source",
        action="append",
        help="STATION_ID|STATION_NAME|HTTPS_URL; may be repeated",
    )
    parser.add_argument("--station-limit", type=int, help="focused test limit; omit for the full station catalog")
    parser.add_argument("--generated-at-utc", default=None)
    args = parser.parse_args()

    generated_at = args.generated_at_utc or _now_utc()
    station_response = _fetch(args.station_url)
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
        station_payload=station_response.content,
        station_source_url=args.station_url,
        ranking_payloads=ranking_payloads,
        generated_at_utc=generated_at,
        station_limit=args.station_limit,
    )
    _write_catalog(args.output_dir, stations, events)


if __name__ == "__main__":
    main()
