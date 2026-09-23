"""Generate the allowlisted 4 km x 4 km demo result archives sequentially."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from floodsim.api.runtime_config import DEMO_EVENT_IDS
from floodsim.domain.geometry import AnalysisArea
from floodsim.domain.rainfall import ConstantRainfall
from floodsim.domain.run_config import AccuracyMode, RunConfig
from floodsim.domain.run_state import RunState
from floodsim.orchestration.run_coordinator import RunCoordinator
from floodsim.providers.common import area_from_square
from floodsim.providers.gsi_elevation import (
    PROVIDERS,
    ElevationProduct,
    GsiElevationProvider,
)
from floodsim.results.archive import create_result_archive
from floodsim.sfincs.model_builder import SfincsModelBuilder


@dataclass(frozen=True)
class DemoEvent:
    event_id: str
    year: int
    location: str
    latitude: float
    longitude: float
    rainfall_mm_per_h: float


EVENTS = (
    DemoEvent("2025-yokkaichi", 2025, "三重県四日市市中心部", 34.9665, 136.6208, 123.5),
    DemoEvent("2026-chiba", 2026, "千葉県千葉市周辺", 35.6129, 140.1141, 115.0),
    DemoEvent("2019-saga", 2019, "佐賀県佐賀市中心部", 33.2642, 130.2975, 110.0),
    DemoEvent("2026-nagoya", 2026, "愛知県名古屋市中心部", 35.1569, 136.9196, 104.5),
    DemoEvent("2000-nagoya", 2000, "愛知県名古屋市周辺", 35.1028, 136.9555, 97.0),
)
TERMINAL_STATES = {RunState.COMPLETE, RunState.FAILED, RunState.CANCELLED}


class DemoElevationProvider(GsiElevationProvider):
    """Use the production fill method with a coastal-demo coverage allowance."""

    def acquire(
        self,
        area: AnalysisArea,
        grid_m: float = 1.0,
        cache_dir: str | Path = ".cache",
        providers: Iterable[tuple[str, str, int]] = PROVIDERS,
        max_nearest_fill_fraction: float = 0.05,
        acquired_at_utc: str | None = None,
    ) -> ElevationProduct:
        return super().acquire(
            area,
            grid_m=grid_m,
            cache_dir=cache_dir,
            providers=providers,
            max_nearest_fill_fraction=max_nearest_fill_fraction,
            acquired_at_utc=acquired_at_utc,
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_run(coordinator: RunCoordinator, event: DemoEvent, output_dir: Path) -> dict[str, object]:
    config = RunConfig(
        analysis_area=area_from_square(event.latitude, event.longitude, 2000.0),
        requested_accuracy_mode=AccuracyMode.FULL_1M,
        rainfall=ConstantRainfall(
            intensity_mm_per_h=event.rainfall_mm_per_h,
            duration_minutes=60,
        ),
    )
    record = coordinator.create_run(config)
    printed = 0
    last_state: RunState | None = None
    while True:
        current = coordinator.get(record.run_id)
        with current.lock:
            state = current.machine.state
            lines = current.activity_lines[printed:]
            printed = len(current.activity_lines)
        if state is not last_state:
            print(f"[{event.event_id}] state={state.value}", flush=True)
            last_state = state
        for line in lines:
            print(f"[{event.event_id}] {line}", flush=True)
        if state in TERMINAL_STATES:
            break
        time.sleep(2.0)
    if record.future is not None:
        record.future.result()
    if state is not RunState.COMPLETE:
        raise RuntimeError(f"{event.event_id} finished as {state.value}")

    run_dir = coordinator.store.run_dir(record.run_id)
    archive_path = output_dir / f"{event.event_id}.zip"
    create_result_archive(
        archive_path,
        config_path=run_dir / "run_config.json",
        manifest_path=run_dir / "manifest.json",
        metadata_path=run_dir / "results" / "result_metadata.json",
        arrays_path=(
            run_dir
            / "results"
            / record.manifest.output_files["normalized_arrays"]
        ),
    )
    return {
        "event_id": event.event_id,
        "year": event.year,
        "location": event.location,
        "center": {"latitude": event.latitude, "longitude": event.longitude},
        "half_size_m": 2000,
        "rainfall_mm_per_h": event.rainfall_mm_per_h,
        "duration_minutes": 60,
        "output_interval_seconds": 900,
        "archive": archive_path.name,
        "archive_bytes": archive_path.stat().st_size,
        "sha256": _sha256(archive_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--event", choices=DEMO_EVENT_IDS, action="append")
    args = parser.parse_args()
    if not os.environ.get("SFINCS_BIN"):
        parser.error("SFINCS_BIN must point to the locally licensed SFINCS executable")

    selected = set(args.event or DEMO_EVENT_IDS)
    events = [event for event in EVENTS if event.event_id in selected]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    coordinator = RunCoordinator(
        runs_root=args.work_dir / "runs",
        elevation_provider=DemoElevationProvider(),
        model_builder=SfincsModelBuilder(minimum_output_interval_seconds=900),
    )
    generated = [_archive_run(coordinator, event, args.output_dir) for event in events]
    manifest = {
        "schema_version": "1",
        "generator": "scripts/generate_demo_results.py",
        "hydraulic_mode": "full_1m",
        "elevation_missing_fill": {
            "method": "production nearest-neighbour fill",
            "maximum_fraction": 0.05,
            "scope": "demo generation only",
        },
        "events": generated,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
