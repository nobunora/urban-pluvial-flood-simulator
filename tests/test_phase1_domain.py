from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from floodsim.domain.geometry import AnalysisArea, GeoBounds, LonLat, ProjectedBounds
from floodsim.domain.manifest import Limitations, RunManifest
from floodsim.domain.rainfall import (
    ConstantRainfall,
    HistoricalObservedProfile,
    RainfallTimeSeries,
)
from floodsim.domain.run_config import AccuracyMode
from floodsim.domain.run_state import RunState, RunStateMachine, StateTransitionError


def area() -> AnalysisArea:
    return AnalysisArea(
        mode="preset_square",
        bounds=GeoBounds(west_deg=139.7, south_deg=35.6, east_deg=139.8, north_deg=35.7),
        center=LonLat(lon_deg=139.75, lat_deg=35.65),
        width_m=500,
        height_m=500,
        area_m2=250000,
    )


def test_geometry_contracts_validate_bounds_and_explicit_crs() -> None:
    assert LonLat(lon_deg=-180, lat_deg=90).lat_deg == 90
    assert ProjectedBounds(xmin_m=0, ymin_m=0, xmax_m=10, ymax_m=10, crs="EPSG:6697").crs == "EPSG:6697"

    with pytest.raises(ValidationError):
        LonLat(lon_deg=181, lat_deg=0)
    with pytest.raises(ValidationError):
        GeoBounds(west_deg=1, south_deg=0, east_deg=1, north_deg=2)
    with pytest.raises(ValidationError):
        ProjectedBounds(xmin_m=0, ymin_m=0, xmax_m=10, ymax_m=10, crs="")


def test_analysis_area_enforces_preset_sizes_and_area() -> None:
    assert area().area_m2 == 250000
    with pytest.raises(ValidationError):
        AnalysisArea(
            mode="preset_square",
            bounds=area().bounds,
            center=area().center,
            width_m=300,
            height_m=300,
            area_m2=90000,
        )
    with pytest.raises(ValidationError):
        AnalysisArea(
            mode="rectangle",
            bounds=area().bounds,
            center=area().center,
            width_m=300,
            height_m=400,
            area_m2=1,
        )


def test_accuracy_mode_rejects_unknown_values() -> None:
    assert AccuracyMode("full_1m") is AccuracyMode.FULL_1M
    with pytest.raises(ValueError):
        AccuracyMode("fast")


def test_rainfall_distinguishes_zero_from_missing() -> None:
    assert ConstantRainfall(intensity_mm_per_h=0).intensity_mm_per_h == 0
    assert HistoricalObservedProfile(available=False).profile_id is None
    with pytest.raises(ValidationError):
        HistoricalObservedProfile(available=True)
    with pytest.raises(ValidationError):
        RainfallTimeSeries(
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            elapsed_seconds=[0, 60],
            intensity_mm_per_h=[0],
            source_metadata={"source": "test"},
        )


def test_limitations_defaults_are_explicitly_false() -> None:
    assert Limitations().model_dump() == {
        "infiltration_modelled": False,
        "sewer_network_modelled": False,
        "storm_drain_inlets_modelled": False,
        "building_interior_modelled": False,
        "spatial_meteorological_rainfall_modelled": False,
        "river_stage_boundary_modelled": False,
        "coastal_tide_surge_modelled": False,
        "official_forecast": False,
    }


def test_manifest_contains_required_typed_fields() -> None:
    manifest = RunManifest(
        application_version="0.1.0",
        run_id=uuid4(),
        created_at_utc=datetime.now(timezone.utc),
        analysis_area=area(),
        requested_accuracy_mode=AccuracyMode.ADAPTIVE,
        run_status=RunState.CREATED,
    )
    assert manifest.schema_version == "1"
    with pytest.raises(ValidationError):
        RunManifest(
            application_version="0.1.0",
            run_id=uuid4(),
            created_at_utc=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1))),
            analysis_area=area(),
            requested_accuracy_mode=AccuracyMode.ADAPTIVE,
            run_status=RunState.CREATED,
        )


def test_run_state_machine_allows_normal_progression() -> None:
    machine = RunStateMachine()
    normal_states = [
        RunState.VALIDATING,
        RunState.ACQUIRING_TERRAIN,
        RunState.ACQUIRING_VECTORS,
        RunState.ACQUIRING_RAINFALL,
        RunState.PREPROCESSING_TERRAIN,
        RunState.ALLOCATING_ROOF_RAIN,
        RunState.BUILDING_GRID,
        RunState.BUILDING_MODEL,
        RunState.ENSURING_ENGINE,
        RunState.RUNNING_ENGINE,
        RunState.READING_RESULTS,
        RunState.COMPLETE,
    ]
    for state in normal_states:
        assert machine.transition(state) is state


def test_run_state_machine_allows_failure_and_cancellation_paths() -> None:
    failed = RunStateMachine()
    assert failed.transition(RunState.FAILED) is RunState.FAILED

    cancelled = RunStateMachine()
    cancelled.transition(RunState.VALIDATING)
    assert cancelled.transition(RunState.CANCELLING) is RunState.CANCELLING
    assert cancelled.transition(RunState.CANCELLED) is RunState.CANCELLED


def test_run_state_machine_rejects_illegal_and_terminal_transitions() -> None:
    machine = RunStateMachine()
    with pytest.raises(StateTransitionError):
        machine.transition(RunState.RUNNING_ENGINE)
    machine.transition(RunState.FAILED)
    with pytest.raises(StateTransitionError):
        machine.transition(RunState.CREATED)
