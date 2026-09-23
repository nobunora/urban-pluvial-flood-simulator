#!/usr/bin/env python3
"""Evaluate one real Full 1 m versus Adaptive SFINCS benchmark case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from floodsim.sfincs.output_reader import read_quadtree_result, read_regular_result
from floodsim.storage.run_store import atomic_write_json
from floodsim.validation.adaptive_accuracy import evaluate_adaptive_case


def evaluate_paths(
    *,
    full_map: Path,
    adaptive_map: Path,
    adaptive_layout: Path,
    benchmark_name: str,
    benchmark_class: str,
    full_accounted_volume_m3: float | None = None,
    adaptive_accounted_volume_m3: float | None = None,
    connectivity_preserved: bool | None = None,
) -> dict[str, object]:
    full = read_regular_result(full_map)
    adaptive = read_quadtree_result(
        adaptive_map,
        layout_path=adaptive_layout,
    )
    report = evaluate_adaptive_case(
        full,
        adaptive,
        benchmark_name=benchmark_name,
        benchmark_class=benchmark_class,
        full_accounted_volume_m3=full_accounted_volume_m3,
        adaptive_accounted_volume_m3=adaptive_accounted_volume_m3,
        connectivity_preserved=connectivity_preserved,
    )
    return report.to_dict()


def _optional_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-map", type=Path, required=True)
    parser.add_argument("--adaptive-map", type=Path, required=True)
    parser.add_argument("--adaptive-layout", type=Path, required=True)
    parser.add_argument("--benchmark-name", required=True)
    parser.add_argument(
        "--benchmark-class",
        choices=("open_area", "urban", "road_channel"),
        required=True,
    )
    parser.add_argument("--full-accounted-volume-m3", type=float)
    parser.add_argument("--adaptive-accounted-volume-m3", type=float)
    parser.add_argument("--connectivity-preserved", type=_optional_bool)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if (args.full_accounted_volume_m3 is None) != (
        args.adaptive_accounted_volume_m3 is None
    ):
        parser.error(
            "both accounted-volume arguments must be supplied together"
        )

    payload = evaluate_paths(
        full_map=args.full_map,
        adaptive_map=args.adaptive_map,
        adaptive_layout=args.adaptive_layout,
        benchmark_name=args.benchmark_name,
        benchmark_class=args.benchmark_class,
        full_accounted_volume_m3=args.full_accounted_volume_m3,
        adaptive_accounted_volume_m3=args.adaptive_accounted_volume_m3,
        connectivity_preserved=args.connectivity_preserved,
    )
    atomic_write_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    raise SystemExit(0 if payload["passed"] is True else 2)


if __name__ == "__main__":
    main()
