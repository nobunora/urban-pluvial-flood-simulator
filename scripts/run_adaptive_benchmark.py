#!/usr/bin/env python3
"""Run one deterministic Full 1 m versus Adaptive benchmark with native SFINCS."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from floodsim.preprocessing.adaptive_grid import (
    DEFAULT_ADAPTIVE_GRID_POLICY,
    build_adaptive_grid,
)
from floodsim.sfincs.model_builder import AdaptiveSfincsModelBuilder, SfincsModelBuilder
from floodsim.sfincs.output_reader import read_quadtree_result, read_regular_result
from floodsim.sfincs.runner import ResolvedEngine, SfincsRunner, sha256_file
from floodsim.storage.run_store import atomic_write_json
from floodsim.validation.adaptive_accuracy import evaluate_adaptive_case
from floodsim.validation.adaptive_benchmarks import (
    BenchmarkKind,
    build_adaptive_benchmark_fixture,
)


def run_benchmark(
    *,
    kind: BenchmarkKind,
    out_dir: Path,
    sfincs_exe: Path,
    full_accounted_volume_m3: float | None = None,
    adaptive_accounted_volume_m3: float | None = None,
    connectivity_preserved: bool | None = None,
) -> dict[str, object]:
    if (full_accounted_volume_m3 is None) != (
        adaptive_accounted_volume_m3 is None
    ):
        raise ValueError("accounted Full and Adaptive volumes must be supplied together")

    executable = sfincs_exe.resolve()
    if not executable.is_file():
        raise FileNotFoundError(executable)

    fixture = build_adaptive_benchmark_fixture(kind)
    adaptive_grid = build_adaptive_grid(
        fixture.grid,
        policy=replace(
            DEFAULT_ADAPTIVE_GRID_POLICY,
            target_core_radius_m=0.0,
            target_mid_radius_m=0.0,
        ),
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    full_build = SfincsModelBuilder().build(
        out_dir / "full" / "model",
        fixture.grid,
        fixture.rainfall,
    )
    adaptive_build = AdaptiveSfincsModelBuilder().build(
        out_dir / "adaptive" / "model",
        fixture.grid,
        adaptive_grid,
        fixture.rainfall,
    )
    if adaptive_build.adaptive_layout_path is None:
        raise RuntimeError("Adaptive build did not produce face layout")

    engine = ResolvedEngine(
        executable=executable,
        source="explicit-adaptive-benchmark",
        sha256=sha256_file(executable),
    )
    runner = SfincsRunner()
    full_execution = runner.run(
        full_build.model_dir,
        logs_dir=out_dir / "full" / "logs",
        engine=engine,
    )
    adaptive_execution = runner.run(
        adaptive_build.model_dir,
        logs_dir=out_dir / "adaptive" / "logs",
        engine=engine,
    )

    full_result = read_regular_result(full_execution.result_path)
    adaptive_result = read_quadtree_result(
        adaptive_execution.result_path,
        layout_path=adaptive_build.adaptive_layout_path,
    )
    validation = evaluate_adaptive_case(
        full_result,
        adaptive_result,
        benchmark_name=fixture.name,
        benchmark_class=fixture.benchmark_class,
        full_accounted_volume_m3=full_accounted_volume_m3,
        adaptive_accounted_volume_m3=adaptive_accounted_volume_m3,
        connectivity_preserved=connectivity_preserved,
    )
    payload: dict[str, object] = {
        "benchmark": {
            "name": fixture.name,
            "class": fixture.benchmark_class,
            "important_flow_path": fixture.important_flow_path,
            "size_cells": fixture.grid.width_cells,
            "rainfall": dict(fixture.rainfall.source_metadata),
        },
        "engine": {
            "source": engine.source,
            "sha256": engine.sha256,
        },
        "full": {
            "elapsed_seconds": full_execution.elapsed_seconds,
            "hydraulic_cells": fixture.grid.cell_count,
            "result_path": str(full_execution.result_path),
        },
        "adaptive": {
            "elapsed_seconds": adaptive_execution.elapsed_seconds,
            "hydraulic_cells": adaptive_grid.total_hydraulic_cells,
            "reduction_ratio": adaptive_grid.reduction_ratio,
            "threshold_identity": adaptive_grid.threshold_identity,
            "result_path": str(adaptive_execution.result_path),
            "layout_path": str(adaptive_build.adaptive_layout_path),
        },
        "validation": validation.to_dict(),
    }
    atomic_write_json(out_dir / "benchmark_report.json", payload)
    return payload


def _optional_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        choices=("open_area", "urban_obstacle", "road_channel"),
        required=True,
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sfincs-exe", type=Path, required=True)
    parser.add_argument("--full-accounted-volume-m3", type=float)
    parser.add_argument("--adaptive-accounted-volume-m3", type=float)
    parser.add_argument("--connectivity-preserved", type=_optional_bool)
    args = parser.parse_args()

    payload = run_benchmark(
        kind=args.case,
        out_dir=args.out_dir,
        sfincs_exe=args.sfincs_exe,
        full_accounted_volume_m3=args.full_accounted_volume_m3,
        adaptive_accounted_volume_m3=args.adaptive_accounted_volume_m3,
        connectivity_preserved=args.connectivity_preserved,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
