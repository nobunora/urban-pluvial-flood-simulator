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
)
from floodsim.domain.rainfall import historical_uniform_intensity
from floodsim.providers.common import ProviderError
from floodsim.providers.jma import JmaCatalogProvider, JmaRainfallEvent, JmaStation

router = APIRouter()
catalog_provider = JmaCatalogProvider()


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


@router.get("/rainfall/events/{event_id}", response_model=RainfallEventResponse)
def rainfall_event(event_id: str) -> RainfallEventResponse:
    catalog = _catalog_or_error()
    event = catalog.event(event_id)
    if event is None:
        raise ApiContractError(404, "JMA_EVENT_NOT_FOUND", "指定された降雨記録が見つかりません。")
    return _event_response(event)
