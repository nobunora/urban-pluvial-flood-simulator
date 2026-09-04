from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

from floodsim.api.app import app
from floodsim.domain.rainfall import historical_uniform_intensity
from floodsim.providers.common import DEFAULT_NETWORK_POLICY, ProviderParseError, ProviderRequestError
from floodsim.providers.geocoder import CsisSimpleGeocoder, parse_csis_xml
from floodsim.providers.jma import (
    JmaCatalogError,
    JmaCatalogProvider,
    JmaRainfallEvent,
    JmaStation,
    catalog_payload,
    haversine_distance_km,
    load_catalog,
    make_event_id,
    parse_amedas_csv,
    parse_jma_ranking_html,
)
from scripts.build_jma_rainfall_catalog import DEFAULT_RANKING_SOURCES, build_catalog

FIXTURES = Path(__file__).parent / "fixtures" / "phase2b"
JMA_DATA = Path(__file__).parents[1] / "data" / "jma"
GENERATED_AT = "2026-09-03T00:00:00+00:00"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_csis_one_candidate_and_attribution() -> None:
    result = parse_csis_xml(fixture("csis_one.xml"))
    assert result.candidates[0].title.startswith("東京都")
    assert result.candidates[0].confidence == 3
    assert result.attribution_text == "CSISシンプルジオコーディング実験を利用"
    assert result.attribution_url == "https://geocode.csis.u-tokyo.ac.jp/"


def test_csis_multiple_preserves_order_and_zero_is_valid() -> None:
    multiple = parse_csis_xml(fixture("csis_multiple.xml"))
    assert [candidate.title for candidate in multiple.candidates] == ["一番目", "二番目"]
    assert parse_csis_xml(fixture("csis_zero.xml")).candidates == []


def test_csis_candidate_count_is_capped() -> None:
    payload = "".join(
        (
            "<results><geodetic>wgs1984</geodetic>",
            "".join(
                f"<candidate><address>候補{i}</address><longitude>139</longitude><latitude>35</latitude></candidate>"
                for i in range(12)
            ),
            "</results>",
        )
    )
    assert len(parse_csis_xml(payload).candidates) == 10


def test_csis_rejects_malformed_metadata_and_coordinates() -> None:
    with pytest.raises(ProviderParseError):
        parse_csis_xml(b"<results>")
    with pytest.raises(ProviderParseError):
        parse_csis_xml(fixture("csis_one.xml").replace(b"wgs1984", b"unknown"))
    with pytest.raises(ProviderParseError):
        parse_csis_xml(fixture("csis_one.xml").replace(b"139.753632", b"181"))


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code


class FakeSession:
    def __init__(self, response: FakeResponse | BaseException) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def test_csis_provider_uses_approved_params_and_transport_error() -> None:
    session = FakeSession(FakeResponse(fixture("csis_one.xml")))
    result = CsisSimpleGeocoder(session=session, sleeper=lambda _: None).search("  東京駅  ")
    assert result.candidates
    assert session.calls[0][2]["params"] == {"addr": "東京駅", "charset": "UTF8", "series": "ADDRESS"}
    with pytest.raises(ProviderRequestError):
        CsisSimpleGeocoder(
            session=FakeSession(requests.ConnectionError("transport")), sleeper=lambda _: None
        ).search("駅")


def test_csis_default_session_uses_shared_user_agent() -> None:
    geocoder = CsisSimpleGeocoder()
    assert geocoder.session.headers["User-Agent"] == DEFAULT_NETWORK_POLICY.user_agent


def test_amedas_fixture_parses_only_precipitation_stations() -> None:
    stations = parse_amedas_csv(fixture("jma_amedas.csv"), catalog_generated_at_utc=GENERATED_AT)
    assert [station.station_id for station in stations] == ["44132", "44173"]
    assert stations[0].lat_deg == pytest.approx(35.6916666667)
    assert stations[0].lon_deg == pytest.approx(139.75)


def test_jma_rank_rows_map_only_explicit_durations_and_keep_flags() -> None:
    events = parse_jma_ranking_html(
        fixture("jma_rank.html"),
        station_id="44173",
        station_name="大島北ノ山",
        station_lon_deg=139.36,
        station_lat_deg=34.781666666666666,
        source_url="https://www.data.jma.go.jp/example",
        catalog_generated_at_utc=GENERATED_AT,
    )
    assert [event.duration_minutes for event in events] == [10, 10, 60, 60, 1440, 1440]
    assert events[0].data_quality_flags == ["*"]
    assert all(event.total_precipitation_mm > 0 for event in events)
    assert all(event.profile_available is False for event in events)
    assert all(event.station_lon_deg == pytest.approx(139.36) for event in events)
    assert all(event.station_lat_deg == pytest.approx(34.781666666666666) for event in events)


def test_packaged_ranking_snapshots_parse_exact_top_ten_only() -> None:
    source_dir = JMA_DATA / "sources"
    station_payload = (source_dir / "ame_master.zip").read_bytes()
    stations = {station.station_id: station for station in parse_amedas_csv(station_payload, catalog_generated_at_utc=GENERATED_AT)}
    for station_id, station_name, source_url in DEFAULT_RANKING_SOURCES:
        station = stations[station_id]
        events = parse_jma_ranking_html(
            (source_dir / f"rank_{station_id}.html").read_bytes(),
            station_id=station_id,
            station_name=station_name,
            station_lon_deg=station.lon_deg,
            station_lat_deg=station.lat_deg,
            source_url=source_url,
            catalog_generated_at_utc=GENERATED_AT,
        )
        assert len(events) == 30
        assert {event.duration_minutes for event in events} == {10, 60, 1440}
        assert {event.rank for event in events} == set(range(1, 11))


def test_catalog_generator_builds_deterministic_fixture_payloads() -> None:
    stations, events = build_catalog(
        station_payload=fixture("jma_amedas.csv"),
        station_source_url="https://www.jma.go.jp/jma/kishou/know/amedas/ame_master.zip",
        ranking_payloads=[
            ("44173", "大島北ノ山", "https://www.data.jma.go.jp/example", fixture("jma_rank.html"))
        ],
        generated_at_utc=GENERATED_AT,
    )
    assert len(stations["stations"]) == 2
    assert sorted(event["duration_minutes"] for event in events["events"]) == [10, 10, 60, 60, 1440, 1440]
    assert all("station_lon_deg" in event and "station_lat_deg" in event for event in events["events"])


def test_committed_jma_catalogs_are_reproducible_from_packaged_sources() -> None:
    source_dir = JMA_DATA / "sources"
    ranking_payloads = [
        (station_id, station_name, source_url, (source_dir / f"rank_{station_id}.html").read_bytes())
        for station_id, station_name, source_url in DEFAULT_RANKING_SOURCES
    ]
    stations, events = build_catalog(
        station_payload=(source_dir / "ame_master.zip").read_bytes(),
        station_source_url="https://www.jma.go.jp/jma/kishou/know/amedas/ame_master.zip",
        ranking_payloads=ranking_payloads,
        generated_at_utc=GENERATED_AT,
    )
    assert stations == json.loads((JMA_DATA / "stations.json").read_text(encoding="utf-8"))
    assert events == json.loads((JMA_DATA / "rainfall_extremes.json").read_text(encoding="utf-8"))
    assert len(events["events"]) == 60


def test_event_ids_and_uniform_conversion_are_deterministic() -> None:
    args = ("44173", 60, 78.0, 1, "2000/7/4", "https://example.test/rank")
    assert make_event_id(*args) == make_event_id(*args)
    assert historical_uniform_intensity(78.0, 60) == 78.0
    with pytest.raises(ValueError):
        historical_uniform_intensity(0, 60)
    with pytest.raises(ValueError):
        historical_uniform_intensity(1, 0)


def _catalog_files(tmp_path: Path) -> tuple[Path, Path]:
    stations = [
        JmaStation("a", "A", "X", 139.0, 35.0, True, "https://jma.test", GENERATED_AT),
        JmaStation("b", "B", "X", 140.0, 35.0, True, "https://jma.test", GENERATED_AT),
    ]
    events = [
        JmaRainfallEvent(
            "e", "a", "A", 139.0, 35.0, 60, 12.0, 1, "2020/1/1", "https://jma.test/rank", GENERATED_AT, []
        )
    ]
    station_payload, event_payload = catalog_payload(stations, events, GENERATED_AT)
    stations_path = tmp_path / "stations.json"
    events_path = tmp_path / "events.json"
    stations_path.write_text(json.dumps(station_payload), encoding="utf-8")
    events_path.write_text(json.dumps(event_payload), encoding="utf-8")
    return stations_path, events_path


def test_catalog_loads_all_nearest_stations_and_rejects_corruption(tmp_path: Path) -> None:
    stations_path, events_path = _catalog_files(tmp_path)
    catalog = JmaCatalogProvider(stations_path, events_path).load()
    assert [station.station_id for station, _ in catalog.nearest_stations(139.0, 35.0, 2)] == ["a", "b"]
    assert catalog.extremes("a")[0].event_id == "e"
    assert catalog.extremes("b") == []
    assert haversine_distance_km(139.0, 35.0, 139.0, 35.0) == 0.0
    events_path.write_text("not json", encoding="utf-8")
    with pytest.raises(JmaCatalogError):
        load_catalog(stations_path, events_path)


@pytest.mark.parametrize(
    ("target", "mutation"),
    [
        ("stations", lambda payload: payload.pop("schema_version")),
        ("events", lambda payload: payload.update(schema_version="2")),
        ("events", lambda payload: payload["events"][0].update(event_date_or_datetime_metadata=123)),
        ("events", lambda payload: payload["events"][0].update(profile_id="")),
        ("events", lambda payload: payload["events"][0].update(profile_available=True, profile_id=None)),
        ("events", lambda payload: payload["events"][0].update(station_lon_deg=140.0)),
        ("events", lambda payload: payload["events"][0].update(station_name="wrong")),
        ("events", lambda payload: payload["events"][0].update(rank=11)),
    ],
)
def test_catalog_rejects_schema_and_event_contract_corruption(tmp_path: Path, target: str, mutation) -> None:
    stations_path, events_path = _catalog_files(tmp_path)
    path = stations_path if target == "stations" else events_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(JmaCatalogError):
        load_catalog(stations_path, events_path)


def test_geocode_api_input_limit_and_provider_error(monkeypatch) -> None:
    import floodsim.api.routes_geocode as routes

    class FakeGeocoder:
        def search(self, query):
            return parse_csis_xml(fixture("csis_multiple.xml"))

    monkeypatch.setattr(routes, "geocoder", FakeGeocoder())
    client = TestClient(app)
    assert client.get("/api/v1/geocode?q=%20%E9%A7%85%20").status_code == 200
    empty = client.get("/api/v1/geocode?q=%20")
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "INPUT_EMPTY_GEOCODE_QUERY"
    long_query = client.get("/api/v1/geocode", params={"q": "a" * 201})
    assert long_query.status_code == 400
    assert long_query.json()["error"]["code"] == "INPUT_GEOCODE_QUERY_TOO_LONG"
    missing = client.get("/api/v1/geocode")
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "INPUT_VALIDATION_ERROR"


def test_rainfall_api_returns_nearest_packaged_stations_and_event_coordinates() -> None:
    client = TestClient(app)
    stations = client.get("/api/v1/rainfall/stations", params={"lon": 139.75, "lat": 35.69, "limit": 2})
    assert stations.status_code == 200
    assert [station["station_id"] for station in stations.json()["stations"]] == ["44132", "44136"]
    assert stations.json()["stations"][0]["distance_km"] == pytest.approx(0.185, abs=0.01)

    extremes = client.get("/api/v1/rainfall/stations/44132/extremes")
    assert extremes.status_code == 200
    first = extremes.json()["events"][0]
    assert first["station_lon_deg"] == pytest.approx(139.75)
    assert first["station_lat_deg"] == pytest.approx(35.6916666667)
    assert first["profile_available"] is False

    no_events = client.get("/api/v1/rainfall/stations/44136/extremes")
    assert no_events.status_code == 200
    assert no_events.json()["events"] == []


def test_rainfall_api_uses_stable_not_found_errors() -> None:
    client = TestClient(app)
    missing_station = client.get("/api/v1/rainfall/stations/missing/extremes")
    assert missing_station.status_code == 404
    assert missing_station.json()["error"]["code"] == "JMA_STATION_NOT_FOUND"
    missing_event = client.get("/api/v1/rainfall/events/missing")
    assert missing_event.status_code == 404
    assert missing_event.json()["error"]["code"] == "JMA_EVENT_NOT_FOUND"


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 35},
        {"lon": 139},
        {"lon": -181, "lat": 35},
        {"lon": 139, "lat": 91},
        {"lon": 139, "lat": 35, "limit": 0},
        {"lon": 139, "lat": 35, "limit": 21},
    ],
)
def test_rainfall_query_validation_uses_canonical_error_envelope(params) -> None:
    response = TestClient(app).get("/api/v1/rainfall/stations", params=params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INPUT_VALIDATION_ERROR"


def test_rainfall_api_returns_stable_unavailable_error_for_corrupt_catalog(monkeypatch, tmp_path: Path) -> None:
    import floodsim.api.routes_rainfall as routes

    stations_path, events_path = _catalog_files(tmp_path)
    events_path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(routes, "catalog_provider", JmaCatalogProvider(stations_path, events_path))
    response = TestClient(app).get("/api/v1/rainfall/stations", params={"lon": 139, "lat": 35})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "JMA_CATALOG_UNAVAILABLE"
