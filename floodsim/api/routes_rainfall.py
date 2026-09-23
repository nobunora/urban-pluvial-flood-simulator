"""Packaged JMA rainfall catalog API routes."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query

from floodsim.api.errors import ApiContractError
from floodsim.api.schemas import (
    RainfallEventResponse,
    RainfallExtremesResponse,
    RainfallStationResponse,
    RainfallStationSearchResponse,
    RecentRainfallRankingResponse,
)
from floodsim.domain.rainfall import historical_uniform_intensity
from floodsim.providers.common import ProviderError
from floodsim.providers.jma import JmaCatalogProvider, JmaRainfallEvent, JmaStation

router = APIRouter()
catalog_provider = JmaCatalogProvider()

_URBAN_FLOOD_RANKING = (
    ("2025-yokkaichi", "2025", "四日市市中心部", 123.5, 136.6245, 34.9650),
    ("2026-chiba", "2026", "千葉市周辺", 115.0, 140.1063, 35.6074),
    ("2019-saga", "2019", "佐賀県佐賀市", 110.0, 130.3009, 33.2635),
    ("2026-nagoya", "2026", "愛知県名古屋市", 104.5, 136.9066, 35.1815),
    ("2000-nagoya", "2000", "愛知県名古屋市周辺", 97.0, 136.9066, 35.1815),
)


def _catalog_or_error():
    try:
        return catalog_provider.load()
    except ProviderError as exc:
        raise ApiContractError(503, "JMA_CATALOG_UNAVAILABLE", "過去の降雨カタログを利用できません。") from exc


def _station_response(station: JmaStation, distance_km: float | None = None) -> RainfallStationResponse:
    return RainfallStationResponse(
        station_id=station.station_id,
        name=station.name,
        prefecture_or_region=station.prefecture_or_region,
        lon_deg=station.lon_deg,
        lat_deg=station.lat_deg,
        distance_km=distance_km,
    )


def _event_response(event: JmaRainfallEvent) -> RainfallEventResponse:
    payload = asdict(event)
    payload["intensity_mm_per_h"] = historical_uniform_intensity(
        event.total_precipitation_mm, event.duration_minutes
    )
    return RainfallEventResponse.model_validate(payload)


@router.get("/rainfall/stations", response_model=RainfallStationSearchResponse)
def rainfall_stations(
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    limit: int = Query(5, ge=1, le=20),
) -> RainfallStationSearchResponse:
    catalog = _catalog_or_error()
    stations = catalog.nearest_stations(lon, lat, limit)
    return RainfallStationSearchResponse(
        stations=[_station_response(station, distance) for station, distance in stations]
    )


@router.get("/rainfall/stations/{station_id}/extremes", response_model=RainfallExtremesResponse)
def rainfall_station_extremes(station_id: str) -> RainfallExtremesResponse:
    catalog = _catalog_or_error()
    station = catalog.station(station_id)
    if station is None:
        raise ApiContractError(404, "JMA_STATION_NOT_FOUND", "指定された観測地点が見つかりません。")
    return RainfallExtremesResponse(
        station=_station_response(station),
        events=[_event_response(event) for event in catalog.extremes(station_id)],
    )


@router.get("/rainfall/recent-ranking", response_model=RecentRainfallRankingResponse)
def recent_rainfall_ranking() -> RecentRainfallRankingResponse:
    """Return the configured urban-flood rainfall scenarios in rank order."""
    events = [
        RainfallEventResponse(
            event_id=event_id,
            station_id=event_id,
            station_name=region,
            station_lon_deg=lon,
            station_lat_deg=lat,
            duration_minutes=60,
            total_precipitation_mm=precipitation,
            rank=rank,
            event_date_or_datetime_metadata=year,
            source_url="user-provided://urban-flood-ranking",
            catalog_generated_at_utc="2026-09-23T00:00:00+09:00",
            data_quality_flags=["user_provided_scenario"],
            profile_available=False,
            intensity_mm_per_h=precipitation,
        )
        for rank, (event_id, year, region, precipitation, lon, lat) in enumerate(
            _URBAN_FLOOD_RANKING, start=1
        )
    ]
    return RecentRainfallRankingResponse(
        period_start="2000-01-01",
        period_end="2026-12-31",
        coverage_note="指定された都市型豪雨シナリオ",
        events=events,
    )


@router.get("/rainfall/events/{event_id}", response_model=RainfallEventResponse)
def rainfall_event(event_id: str) -> RainfallEventResponse:
    catalog = _catalog_or_error()
    event = catalog.event(event_id)
    if event is None:
        raise ApiContractError(404, "JMA_EVENT_NOT_FOUND", "指定された降雨記録が見つかりません。")
    return _event_response(event)
