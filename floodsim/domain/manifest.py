"""Persisted run manifest contract."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from floodsim.domain.geometry import AnalysisArea
from floodsim.domain.run_config import AccuracyMode
from floodsim.domain.run_state import RunState


class Limitations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    infiltration_modelled: bool = False
    sewer_network_modelled: bool = False
    storm_drain_inlets_modelled: bool = False
    building_interior_modelled: bool = False
    spatial_meteorological_rainfall_modelled: bool = False
    river_stage_boundary_modelled: bool = False
    coastal_tide_surge_modelled: bool = False
    official_forecast: bool = False


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    application_version: str
    run_id: UUID
    created_at_utc: datetime
    analysis_area: AnalysisArea
    requested_accuracy_mode: AccuracyMode
    projected_crs: str | None = None
    final_grid_level_counts: dict[str, int] = Field(default_factory=dict)
    elevation_provider_counts: dict[str, int] = Field(default_factory=dict)
    elevation_source_summary: dict[str, Any] = Field(default_factory=dict)
    building_provider: str | None = None
    road_provider: str | None = None
    provider_warnings: list[str] = Field(default_factory=list)
    rainfall_source: dict[str, Any] = Field(default_factory=dict)
    sfincs_version: str | None = None
    sfincs_build_sha256: str | None = None
    sfincs_engine_source: str | None = None
    hydromt_sfincs_version: str | None = None
    manning_defaults: dict[str, float] = Field(
        default_factory=lambda: {"general": 0.030, "road": 0.020}
    )
    boundary_policy: str = "outer eligible cells use SFINCS outflow mask msk=3"
    roof_rain_mass_diagnostic: dict[str, float | int] = Field(default_factory=dict)
    limitations: Limitations = Limitations()
    run_status: RunState
    failing_stage: str | None = None
    failure_code: str | None = None
    output_files: dict[str, str] = Field(default_factory=dict)

    @field_validator("created_at_utc")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("created_at_utc must include a UTC timezone")
        return value
