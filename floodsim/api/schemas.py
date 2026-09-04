"""API response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EngineSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: Literal["SFINCS 2.4.0 Galibier"] = "SFINCS 2.4.0 Galibier"


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    api_version: Literal["v1"] = "v1"
    application_version: str
    engine: EngineSummary


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    stage: str | None = None
    retryable: bool = False


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ApiError


class GeocodeAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    url: str


class GeocodeCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    provider: Literal["csis_simple_geocoding"]
    confidence: int | None = None
    level: int | None = None
    converted: str | None = None


class GeocodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[GeocodeCandidateResponse] = Field(max_length=10)
    attribution: GeocodeAttribution


class RainfallStationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station_id: str
    name: str
    prefecture_or_region: str | None = None
    lon_deg: float = Field(ge=-180, le=180)
    lat_deg: float = Field(ge=-90, le=90)
    distance_km: float | None = Field(default=None, ge=0)


class RainfallStationSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stations: list[RainfallStationResponse]


class RainfallEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    station_id: str
    station_name: str
    station_lon_deg: float = Field(ge=-180, le=180)
    station_lat_deg: float = Field(ge=-90, le=90)
    duration_minutes: int = Field(gt=0)
    total_precipitation_mm: float = Field(gt=0)
    rank: int | None = Field(default=None, ge=1, le=10)
    event_date_or_datetime_metadata: str | None = None
    source_url: str
    catalog_generated_at_utc: str
    data_quality_flags: list[str]
    profile_available: bool
    profile_id: str | None = None
    intensity_mm_per_h: float = Field(gt=0)


class RainfallExtremesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    station: RainfallStationResponse
    events: list[RainfallEventResponse]
