"""Resolve user rainfall scenarios to deterministic SFINCS forcing series."""

from __future__ import annotations

from datetime import datetime, timezone

from floodsim.domain.rainfall import (
    ConstantRainfall,
    HistoricalObservedProfile,
    HistoricalUniformRainfall,
    RainfallTimeSeries,
)
from floodsim.domain.run_config import RunConfig
from floodsim.providers.jma import JmaCatalogProvider

MODEL_REFERENCE_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)


class RainfallResolutionError(RuntimeError):
    code = "INPUT_RAINFALL_INVALID"
    retryable = False


class RainfallEventUnavailable(RainfallResolutionError):
    code = "JMA_EVENT_NOT_FOUND"


class RainfallProfileUnavailable(RainfallResolutionError):
    code = "JMA_PROFILE_UNAVAILABLE"


def _constant_series(intensity: float, duration_minutes: int, metadata: dict[str, str]) -> RainfallTimeSeries:
    if intensity <= 0 or intensity > 500:
        raise RainfallResolutionError("constant rainfall intensity must be within (0, 500] mm/h")
    if not 1 <= duration_minutes <= 10080:
        raise RainfallResolutionError("rainfall duration must be within 1..10080 minutes")
    duration_seconds = float(duration_minutes * 60)
    return RainfallTimeSeries(
        start_time=MODEL_REFERENCE_TIME,
        elapsed_seconds=[0.0, duration_seconds],
        intensity_mm_per_h=[float(intensity), 0.0],
        source_metadata=metadata,
    )


def resolve_rainfall(
    config: RunConfig,
    catalog_provider: JmaCatalogProvider | None = None,
) -> RainfallTimeSeries:
    """Resolve supported Phase 3 rainfall modes without runtime historical scraping."""
    scenario = config.rainfall
    if isinstance(scenario, ConstantRainfall):
        return _constant_series(
            scenario.intensity_mm_per_h,
            scenario.duration_minutes,
            {
                "kind": "constant",
                "intensity_mm_per_h": str(scenario.intensity_mm_per_h),
                "duration_minutes": str(scenario.duration_minutes),
            },
        )

    if isinstance(scenario, HistoricalUniformRainfall):
        if not scenario.available:
            raise RainfallEventUnavailable("selected historical event is unavailable")
        catalog = (catalog_provider or JmaCatalogProvider()).load()
        event = catalog.event(scenario.event_id)
        if event is None:
            raise RainfallEventUnavailable("selected historical event is not present in the packaged catalog")
        return _constant_series(
            event.intensity_mm_per_h,
            event.duration_minutes,
            {
                "kind": "historical_uniform",
                "event_id": event.event_id,
                "station_id": event.station_id,
                "total_precipitation_mm": str(event.total_precipitation_mm),
                "duration_minutes": str(event.duration_minutes),
                "source_url": event.source_url,
            },
        )

    if isinstance(scenario, HistoricalObservedProfile):
        raise RainfallProfileUnavailable(
            "observed-profile rainfall is not available until a validated profile source is packaged"
        )
    raise RainfallResolutionError("unsupported rainfall scenario")
