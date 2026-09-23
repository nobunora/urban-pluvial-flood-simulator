"""Replay Full 1 m grid construction from an existing local run.

This deliberately stops before HydroMT-SFINCS/model execution. It reuses the
run's persisted config/vector source refs and the normal elevation cache path so
BUILDING_GRID failures can be isolated without another live vector acquisition.
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import numpy as np
from platformdirs import user_data_path

from floodsim.domain.run_config import RunConfig
from floodsim.preprocessing.full_grid import build_full_1m_grid
from floodsim.providers.common import ProviderProvenance
from floodsim.providers.gsi_elevation import GsiElevationProvider
from floodsim.storage.run_store import atomic_write_json


def _default_runs_root() -> Path:
    return user_data_path("urban-pluvial-flood-simulator", appauthor=False) / "runs"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path.name} root must be an object")
    return payload


def _load_object_arrays(path: Path, key: str) -> list[np.ndarray]:
    with np.load(path, allow_pickle=True) as archive:
        values = archive[key]
        return [np.asarray(value) for value in values.tolist()]


def _load_vectors(source_refs: Path) -> SimpleNamespace:
    manifest = _load_json(source_refs / "vectors_manifest.json")
    provenance_payload = manifest.get("provenance")
    if not isinstance(provenance_payload, dict):
        raise TypeError("vectors_manifest.json is missing provenance")

    buildings = _load_object_arrays(source_refs / "buildings.npz", "buildings")
    with np.load(source_refs / "basemap_vectors.npz", allow_pickle=True) as archive:
        road_lines = [np.asarray(value) for value in archive["roads"].tolist()]
        road_polygons = [np.asarray(value) for value in archive["road_polygons"].tolist()]

    provenance = ProviderProvenance(**provenance_payload)
    return SimpleNamespace(
        buildings=buildings,
        road_lines=road_lines,
        road_polygons=road_polygons,
        provenance=provenance,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay BUILDING_GRID for an existing Full 1 m run."
    )
    parser.add_argument("run_id", type=UUID)
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=_default_runs_root(),
        help="Run-store root. Defaults to the normal platform user-data runs directory.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runs_root = args.runs_root.expanduser().resolve()
    run_root = runs_root / str(args.run_id)
    config_path = run_root / "run_config.json"
    source_refs = run_root / "source_refs"
    diagnostic_path = run_root / "logs" / "grid_replay_diagnostic.json"

    config = RunConfig.model_validate(_load_json(config_path))
    vectors = _load_vectors(source_refs)
    elevation = GsiElevationProvider().acquire(
        config.analysis_area,
        grid_m=1.0,
        cache_dir=runs_root.parent / "cache",
    )

    diagnostic: dict[str, Any] = {
        "run_id": str(args.run_id),
        "analysis_area": {
            "width_m": config.analysis_area.width_m,
            "height_m": config.analysis_area.height_m,
        },
        "elevation_shape": list(np.asarray(elevation.z).shape),
        "vector_provider": vectors.provenance.provider_id,
        "building_features": len(vectors.buildings),
        "road_line_features": len(vectors.road_lines),
        "road_polygon_features": len(vectors.road_polygons),
    }

    try:
        grid = build_full_1m_grid(config.analysis_area, elevation, vectors)
    except Exception as exc:
        diagnostic.update(
            {
                "result": "FAILED",
                "exception_type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        atomic_write_json(diagnostic_path, diagnostic)
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc

    diagnostic.update(
        {
            "result": "PASS",
            "cell_count": grid.cell_count,
            "building_cells": int(np.count_nonzero(grid.building_mask)),
            "road_cells": int(np.count_nonzero(grid.road_mask)),
            "building_components": grid.roof_allocation.building_components,
            "redistributed_roof_cells": grid.roof_allocation.redistributed_roof_cells,
            "roof_rain_relative_mass_error": grid.roof_allocation.relative_mass_error,
        }
    )
    atomic_write_json(diagnostic_path, diagnostic)
    print(json.dumps(diagnostic, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
