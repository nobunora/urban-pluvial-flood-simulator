"""Persisted run manifest contract."""

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

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
    limitations: Limitations = Limitations()
    run_status: RunState

    @field_validator("created_at_utc")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("created_at_utc must include a UTC timezone")
        return value
