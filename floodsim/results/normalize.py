"""Persist SFINCS regular-grid output behind an unambiguous result contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from floodsim.domain.geometry import AnalysisArea
from floodsim.domain.manifest import Limitations
from floodsim.results.view import depth_legend_metadata
from floodsim.sfincs.output_reader import SfincsRegularResult
from floodsim.storage.run_store import atomic_write_json


@dataclass(frozen=True)
class NormalizedResult:
    arrays_path: Path
    metadata_path: Path
    metadata: dict[str, Any]


def normalize_regular_result(
    result: SfincsRegularResult,
    *,
    area: AnalysisArea,
    results_dir: str | Path,
    limitations: Limitations,
    provider_summary: Mapping[str, Any] | None = None,
    engine_summary: Mapping[str, Any] | None = None,
    run_summary: Mapping[str, Any] | None = None,
) -> NormalizedResult:
    root = Path(results_dir)
    root.mkdir(parents=True, exist_ok=True)
    arrays_path = root / "normalized_full_1m.npz"
    arrays_payload: dict[str, Any] = {
        "depth_time_m": result.depth_time_m,
        "max_depth_m": result.max_depth_m,
        "terrain_elevation_m": result.terrain_elevation_m,
        "active_mask": result.active_mask,
        "time_values": np.asarray(result.time_values),
        "grid_resolution_m": np.float32(1.0),
    }
    if result.flow_vectors_available:
        arrays_payload["velocity_u_mps"] = result.velocity_u_mps
        arrays_payload["velocity_v_mps"] = result.velocity_v_mps
    np.savez_compressed(arrays_path, **arrays_payload)
    metadata = {
        "schema_version": "1",
        "bounds": area.bounds.model_dump(),
        "units": {
            "water_depth": "m",
            "terrain_elevation": "m",
            "grid_resolution": "m",
        },
        "available_time_indices": list(range(len(result.time_values))),
        "time_values": list(result.time_values),
        "flow_vectors_available": result.flow_vectors_available,
        "max_depth_summary": {
            "global_max_depth_m": result.global_max_depth_m,
            "hmax_reconstructed_cells": result.hmax_reconstructed_cells,
            "negative_depth_clipped_values": result.negative_depth_clipped_values,
            "negative_max_depth_clipped_cells": result.negative_max_depth_clipped_cells,
            "min_raw_active_depth_m": result.min_raw_active_depth_m,
            "excluded_boundary_cells": result.excluded_boundary_cells,
        },
        "grid_level_summary": {
            "1m": int(np.count_nonzero(result.active_mask)),
        },
        "depth_legend": depth_legend_metadata(),
        "provider_summary": dict(provider_summary or {}),
        "engine_summary": dict(engine_summary or {}),
        "run_summary": dict(run_summary or {}),
        "no_data_policy": (
            "inactive/blocked and SFINCS boundary-control cells are NaN in normalized arrays; "
            "regular-grid SFINCS h is an unfiltered signed zs-zb output, so finite negative "
            "time-depth values represent dry-state output and are normalized to zero while "
            "remaining visible in diagnostics; missing wet-filtered hmax is reconstructed from "
            "the normalized time-depth series; finite negative hmax remains invalid"
        ),
        "limitations": limitations.model_dump(),
    }
    metadata_path = root / "result_metadata.json"
    atomic_write_json(metadata_path, metadata)
    return NormalizedResult(arrays_path, metadata_path, metadata)
