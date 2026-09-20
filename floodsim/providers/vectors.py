"""PLATEAU-first vector acquisition with OSM building supplementation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event

from floodsim.domain.geometry import AnalysisArea
from floodsim.providers.common import ProviderError, ProviderUnavailableError
from floodsim.providers.osm import OsmProvider, OsmVectors
from floodsim.providers.plateau import PlateauProvider, PlateauVectors


def _write_result(result: PlateauVectors | OsmVectors, out_dir: str | None) -> None:
    if out_dir is None:
        return
    out = Path(out_dir)
    if isinstance(result, PlateauVectors):
        PlateauProvider._write_legacy(result, out)
    else:
        OsmProvider._write_legacy(result, out)


def _supplement_plateau_with_osm(
    plateau_result: PlateauVectors,
    osm_result: OsmVectors,
) -> PlateauVectors:
    plateau_provenance = plateau_result.provenance
    osm_provenance = osm_result.provenance
    supplement_details = {
        "provider_id": osm_provenance.provider_id,
        "provider_name": osm_provenance.provider_name,
        "building_polygons": len(osm_result.buildings),
        "road_lines": len(osm_result.road_lines),
        "attribution": osm_provenance.attribution,
        "terms_url": osm_provenance.terms_url,
    }
    provenance = replace(
        plateau_provenance,
        provider_id="plateau+osm",
        provider_name="Project PLATEAU + OpenStreetMap",
        attribution=f"{plateau_provenance.attribution}; {osm_provenance.attribution}",
        warnings=[
            *plateau_provenance.warnings,
            *osm_provenance.warnings,
            "OSM building/building:part footprints supplement PLATEAU to reduce missing small structures.",
        ],
        source_details={
            **plateau_provenance.source_details,
            "osm_supplement": supplement_details,
        },
    )
    return PlateauVectors(
        buildings=[*plateau_result.buildings, *osm_result.buildings],
        road_lines=[*plateau_result.road_lines, *osm_result.road_lines],
        road_polygons=list(plateau_result.road_polygons),
        provenance=provenance,
    )


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
    plateau_budget_s: float | None = None,
    osm_budget_s: float | None = None,
    cancel_event: Event | None = None,
) -> PlateauVectors | OsmVectors:
    if mode not in {"auto", "plateau", "osm"}:
        raise ValueError("mode must be auto, plateau, or osm")
    plateau_provider = plateau or PlateauProvider()
    osm_provider = osm or OsmProvider()

    if mode == "osm":
        return osm_provider.acquire(
            area,
            cache_dir,
            out_dir,
            margin_m,
            acquired_at_utc,
            time_budget_s=osm_budget_s,
        )
    if mode == "plateau":
        return plateau_provider.acquire(
            area,
            cache_dir,
            out_dir,
            margin_m,
            acquired_at_utc,
            time_budget_s=plateau_budget_s,
        )

    try:
        plateau_result = plateau_provider.acquire(
            area,
            cache_dir,
            None,
            margin_m,
            acquired_at_utc,
            time_budget_s=plateau_budget_s,
        )
    except ProviderError as plateau_error:
        if cancel_event is not None and cancel_event.is_set():
            raise
        try:
            osm_result = osm_provider.acquire(
                area,
                cache_dir,
                None,
                margin_m,
                acquired_at_utc,
                time_budget_s=osm_budget_s,
            )
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
        _write_result(osm_result, out_dir)
        return osm_result

    if cancel_event is not None and cancel_event.is_set():
        _write_result(plateau_result, out_dir)
        return plateau_result

    try:
        osm_supplement = osm_provider.acquire(
            area,
            cache_dir,
            None,
            margin_m,
            acquired_at_utc,
            time_budget_s=osm_budget_s,
        )
    except ProviderError as osm_error:
        supplement_warning = (
            "OSM small-building supplement unavailable "
            f"({type(osm_error).__name__}: {osm_error}); using PLATEAU only."
        )
        plateau_result.provenance = replace(
            plateau_result.provenance,
            warnings=[
                *plateau_result.provenance.warnings,
                supplement_warning,
            ],
            source_details={
                **plateau_result.provenance.source_details,
                "osm_supplement": {
                    "status": "unavailable",
                    "failure_category": type(osm_error).__name__,
                    "failure_message": str(osm_error),
                },
            },
        )
        _write_result(plateau_result, out_dir)
        return plateau_result

    combined = _supplement_plateau_with_osm(plateau_result, osm_supplement)
    _write_result(combined, out_dir)
    return combined
