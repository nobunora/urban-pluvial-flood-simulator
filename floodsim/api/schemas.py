"""API response schemas."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from floodsim.domain.geometry import GeoBounds
from floodsim.domain.run_state import RunState


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


class RunCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    status: Literal["QUEUED"] = "QUEUED"


class RunStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    state: RunState
    stage_code: str
    stage_label: str
    failure_code: str | None = None
    failure_message: str | None = None


class CancelRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    state: RunState


class ResourceEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    accuracy_mode: Literal["full_1m", "adaptive"]


class ResourceEstimateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_1m_equivalent_cells: int
    preliminary_adaptive_cells: int | None = None
    estimated_memory_class: Literal["small", "medium", "heavy", "very_heavy"]
    estimated_disk_class: Literal["small", "medium", "heavy", "very_heavy"]
    runtime_class: Literal["small", "medium", "heavy", "very_heavy"]
    warnings: list[str]


class ResultMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    bounds: GeoBounds
    units: dict[str, str]
    available_time_indices: list[int]
    time_values: list[str]
    max_depth_summary: dict[str, float]
    grid_level_summary: dict[str, int]
    no_data_policy: str
    limitations: dict[str, bool]


class RunEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    state: RunState
    stage_code: str
    stage_label: str
    progress: float | None = Field(default=None, ge=0, le=1)
    message: str
    timestamp: str


class GenericJsonResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    data: dict[str, Any] = Field(default_factory=dict)
