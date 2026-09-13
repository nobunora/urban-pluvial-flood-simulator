"""Persist SFINCS regular-grid output behind an unambiguous result contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from floodsim.domain.geometry import AnalysisArea
from floodsim.domain.manifest import Limitations
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
) -> NormalizedResult:
    root = Path(results_dir)
    root.mkdir(parents=True, exist_ok=True)
    arrays_path = root / "normalized_full_1m.npz"
    np.savez_compressed(
        arrays_path,
        depth_time_m=result.depth_time_m,
        max_depth_m=result.max_depth_m,
        terrain_elevation_m=result.terrain_elevation_m,
        active_mask=result.active_mask,
        time_values=np.asarray(result.time_values),
        grid_resolution_m=np.float32(1.0),
    )
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
        "max_depth_summary": {
            "global_max_depth_m": result.global_max_depth_m,
        },
        "grid_level_summary": {
            "1m": int(np.count_nonzero(result.active_mask)),
        },
        "no_data_policy": "inactive/blocked SFINCS cells are NaN in normalized arrays",
        "limitations": limitations.model_dump(),
    }
    metadata_path = root / "result_metadata.json"
    atomic_write_json(metadata_path, metadata)
    return NormalizedResult(arrays_path, metadata_path, metadata)
