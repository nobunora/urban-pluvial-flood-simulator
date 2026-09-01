"""PLATEAU-first vector acquisition with explicit OSM fallback."""

from __future__ import annotations

from dataclasses import replace

from floodsim.domain.geometry import AnalysisArea
from floodsim.providers.common import ProviderError, ProviderUnavailableError
from floodsim.providers.osm import OsmProvider, OsmVectors
from floodsim.providers.plateau import PlateauProvider, PlateauVectors


def acquire_vectors(
    area: AnalysisArea,
    mode: str = "auto",
    *,
    plateau: PlateauProvider | None = None,
    osm: OsmProvider | None = None,
    cache_dir: str = ".cache",
    out_dir: str | None = None,
    margin_m: float = 30.0,
    acquired_at_utc: str | None = None,
) -> PlateauVectors | OsmVectors:
    if mode not in {"auto", "plateau", "osm"}:
        raise ValueError("mode must be auto, plateau, or osm")
    plateau_provider = plateau or PlateauProvider()
    osm_provider = osm or OsmProvider()
    if mode == "osm":
        return osm_provider.acquire(area, cache_dir, out_dir, margin_m, acquired_at_utc)
    try:
        result = plateau_provider.acquire(area, cache_dir, out_dir, margin_m, acquired_at_utc)
    except ProviderError as plateau_error:
        if mode == "plateau":
            raise
        try:
            osm_result = osm_provider.acquire(area, cache_dir, out_dir, margin_m, acquired_at_utc)
        except ProviderError as osm_error:
            raise ProviderUnavailableError(
                "PLATEAU and OSM vector acquisition failed: "
                f"PLATEAU [{type(plateau_error).__name__}] {plateau_error}; "
                f"OSM [{type(osm_error).__name__}] {osm_error}"
            ) from osm_error
        warning = (
            f"PLATEAU unavailable ({type(plateau_error).__name__}: {plateau_error}); "
            "used OSM fallback."
        )
        osm_result.provenance = replace(
            osm_result.provenance,
            warnings=[*osm_result.provenance.warnings, warning],
            source_details={
                **osm_result.provenance.source_details,
                "fallback": {
                    "from_provider": "plateau",
                    "failure_category": type(plateau_error).__name__,
                    "failure_message": str(plateau_error),
                },
            },
        )
        return osm_result
    return result
