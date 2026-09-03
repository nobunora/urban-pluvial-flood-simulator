"""Rainfall scenario and resolved time-series contracts.

These models describe data; they do not fetch, resolve, interpolate, or write
forcing data. A zero intensity is a valid value and is never used for missing
data.
"""

from __future__ import annotations

import math
from datetime import datetime
from itertools import pairwise
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RainfallModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConstantRainfall(RainfallModel):
    kind: Literal["constant"] = "constant"
    intensity_mm_per_h: float = Field(ge=0)


class HistoricalUniformRainfall(RainfallModel):
    kind: Literal["historical_uniform"] = "historical_uniform"
    event_id: str = Field(min_length=1)
    available: bool


class HistoricalObservedProfile(RainfallModel):
    kind: Literal["historical_observed_profile"] = "historical_observed_profile"
    profile_id: str | None = None
    available: bool

    @model_validator(mode="after")
    def validate_availability(self) -> HistoricalObservedProfile:
        if self.available and not self.profile_id:
            raise ValueError("available observed profiles require profile_id")
        return self


RainfallScenario = Annotated[
    ConstantRainfall | HistoricalUniformRainfall | HistoricalObservedProfile,
    Field(discriminator="kind"),
]


class RainfallTimeSeries(RainfallModel):
    start_time: datetime
    elapsed_seconds: list[float] = Field(min_length=1)
    intensity_mm_per_h: list[float] = Field(min_length=1)
    source_metadata: dict[str, str]
    meteorological_spatial_mode: Literal["uniform"] = "uniform"

    @field_validator("elapsed_seconds")
    @classmethod
    def validate_elapsed_seconds(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("elapsed_seconds must be finite and non-negative")
        if any(later <= earlier for earlier, later in pairwise(values)):
            raise ValueError("elapsed_seconds must be strictly increasing")
        return values

    @field_validator("intensity_mm_per_h")
    @classmethod
    def validate_intensity(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("intensity_mm_per_h must be finite and non-negative")
        return values

    @model_validator(mode="after")
    def validate_lengths(self) -> RainfallTimeSeries:
        if len(self.elapsed_seconds) != len(self.intensity_mm_per_h):
            raise ValueError("elapsed_seconds and intensity_mm_per_h must have equal length")
        return self


def historical_uniform_intensity(total_precipitation_mm: float, duration_minutes: float) -> float:
    """Convert a positive historical total to a spatially uniform intensity."""
    if not math.isfinite(total_precipitation_mm) or total_precipitation_mm <= 0:
        raise ValueError("total_precipitation_mm must be finite and positive")
    if not math.isfinite(float(duration_minutes)) or duration_minutes <= 0:
        raise ValueError("duration_minutes must be finite and positive")
    return total_precipitation_mm / (float(duration_minutes) / 60.0)


uniform_intensity_from_total = historical_uniform_intensity
