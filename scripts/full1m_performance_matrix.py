#!/usr/bin/env python3
"""Run an isolated Full 1 m performance matrix for the three approved changes."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from floodsim.sfincs.model_builder import SfincsModelBuilder
from floodsim.sfincs.output_reader import SfincsRegularResult, read_regular_result
from floodsim.sfincs.runner import ResolvedEngine, SfincsRunner, sha256_file
from floodsim.storage.run_store import atomic_write_json
from floodsim.validation.adaptive_benchmarks import build_adaptive_benchmark_fixture

_VARIANTS: dict[str, dict[str, float | int | str]] = {
    "baseline": {
        "alpha": 0.50,
        "storecumprcp": 1,
        "dtmaxout": "dtmapout",
    },
    "dtmax_only": {
        "alpha": 0.50,
        "storecumprcp": 1,
        "dtmaxout": "duration",
    },
    "cumprcp_only": {
        "alpha": 0.50,
        "storecumprcp": 0,
        "dtmaxout": "dtmapout",
    },
    "alpha_only": {
        "alpha": 0.75,
        "storecumprcp": 1,
        "dtmaxout": "dtmapout",
    },
    "optimized": {
        "alpha": 0.75,
        "storecumprcp": 0,
        "dtmaxout": "duration",
    },
}

_TIMING_RE = re.compile(
    r"Time in (?P<name>[^:]+):\s*(?P<seconds>[-+0-9.eE]+)\s*"
    r"\(\s*(?P<percent>[-+0-9.eE]+)%\)"
)
_AVERAGE_DT_RE = re.compile(r"Average time step \(s\)\s*:\s*(?P<value>[-+0-9.eE]+)")


def _read_inp(path: Path) -> dict[str, str]:
    settings: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        settings[key.strip().lower()] = value.strip()
    return settings


def _rewrite_inp(path: Path, updates: dict[str, float | int]) -> None:
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    pending = {key.lower(): value for key, value in updates.items()}
    output: list[str] = []
    for raw in raw_lines:
        if "=" not in raw:
            output.append(raw)
            continue
        key, _value = raw.split("=", 1)
        normalized = key.strip().lower()
        if normalized not in pending:
            output.append(raw)
            continue
        output.append(f"{key.rstrip():<24} = {pending.pop(normalized)}")
    for key, value in pending.items():
        output.append(f"{key:<24} = {value}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def configure_variant(
    model_dir: Path,
    *,
    variant: str,
    duration_seconds: float,
) -> dict[str, str]:
    if variant not in _VARIANTS:
        raise ValueError(f"unknown performance variant: {variant}")
    inp = model_dir / "sfincs.inp"
    settings = _read_inp(inp)
    dtmapout = float(settings["dtmapout"])
    spec = _VARIANTS[variant]
    dtmaxout = dtmapout if spec["dtmaxout"] == "dtmapout" else duration_seconds
    _rewrite_inp(
        inp,
        {
            "dtmaxout": dtmaxout,
            "storecumprcp": int(spec["storecumprcp"]),
            "alpha": float(spec["alpha"]),
        },
    )
    return _read_inp(inp)


def _parse_engine_timings(stdout_path: Path) -> dict[str, Any]:
    text = stdout_path.read_text(encoding="utf-8", errors="replace")
    timings: dict[str, dict[str, float]] = {}
    for match in _TIMING_RE.finditer(text):
        timings[match.group("name").strip().lower().replace(" ", "_")] = {
            "seconds": float(match.group("seconds")),
            "percent": float(match.group("percent")),
        }
    average = _AVERAGE_DT_RE.search(text)
    return {
        "sections": timings,
        "average_timestep_seconds": (
            float(average.group("value")) if average is not None else None
        ),
    }


def _result_shape_summary(path: Path) -> dict[str, Any]:
    with xr.open_dataset(path) as dataset:
        return {
            "time_frames": int(dataset.sizes.get("time", 0)),
            "timemax_frames": int(dataset.sizes.get("timemax", 0)),
            "cumprcp_present": "cumprcp" in dataset.data_vars,
            "u_present": "u" in dataset.data_vars,
            "v_present": "v" in dataset.data_vars,
        }


def _compare_results(
    baseline: SfincsRegularResult,
    candidate: SfincsRegularResult,
) -> dict[str, Any]:
    if baseline.depth_time_m.shape != candidate.depth_time_m.shape:
        raise ValueError("time-depth shapes differ between performance variants")
    if baseline.max_depth_m.shape != candidate.max_depth_m.shape:
        raise ValueError("maximum-depth shapes differ between performance variants")

    max_mask = (
        np.isfinite(baseline.max_depth_m)
        & np.isfinite(candidate.max_depth_m)
    )
    max_diff = np.abs(
        baseline.max_depth_m[max_mask].astype(np.float64)
        - candidate.max_depth_m[max_mask].astype(np.float64)
    )
    time_mask = (
        np.isfinite(baseline.depth_time_m)
        & np.isfinite(candidate.depth_time_m)
    )
    time_diff = (
        baseline.depth_time_m[time_mask].astype(np.float64)
        - candidate.depth_time_m[time_mask].astype(np.float64)
    )

    velocity: dict[str, float] | None = None
    if (
        baseline.velocity_u_mps is not None
        and baseline.velocity_v_mps is not None
        and candidate.velocity_u_mps is not None
        and candidate.velocity_v_mps is not None
    ):
        base_speed = np.hypot(baseline.velocity_u_mps, baseline.velocity_v_mps)
        cand_speed = np.hypot(candidate.velocity_u_mps, candidate.velocity_v_mps)
        vel_mask = np.isfinite(base_speed) & np.isfinite(cand_speed)
        if np.any(vel_mask):
            vel_diff = base_speed[vel_mask].astype(np.float64) - cand_speed[
                vel_mask
            ].astype(np.float64)
            velocity = {
                "rmse_mps": float(np.sqrt(np.mean(np.square(vel_diff)))),
                "max_abs_difference_mps": float(np.max(np.abs(vel_diff))),
            }

    flooded_counts = {
        f"{threshold:.2f}m": {
            "baseline": int(
                np.count_nonzero(
                    np.isfinite(baseline.max_depth_m)
                    & (baseline.max_depth_m > threshold)
                )
            ),
            "candidate": int(
                np.count_nonzero(
                    np.isfinite(candidate.max_depth_m)
                    & (candidate.max_depth_m > threshold)
                )
            ),
        }
        for threshold in (0.01, 0.05, 0.10)
    }
    return {
        "global_max_depth_m": {
            "baseline": baseline.global_max_depth_m,
            "candidate": candidate.global_max_depth_m,
        },
        "hmax": {
            "rmse_m": (
                float(np.sqrt(np.mean(np.square(max_diff)))) if max_diff.size else 0.0
            ),
            "max_abs_difference_m": float(np.max(max_diff)) if max_diff.size else 0.0,
        },
        "time_depth": {
            "rmse_m": (
                float(np.sqrt(np.mean(np.square(time_diff)))) if time_diff.size else 0.0
            ),
            "max_abs_difference_m": (
                float(np.max(np.abs(time_diff))) if time_diff.size else 0.0
            ),
        },
        "flooded_cell_counts": flooded_counts,
        "velocity_magnitude": velocity,
    }


def run_matrix(
    *,
    out_dir: Path,
    sfincs_exe: Path,
) -> dict[str, Any]:
    executable = sfincs_exe.resolve()
    if not executable.is_file():
        raise FileNotFoundError(executable)

    fixture = build_adaptive_benchmark_fixture("open_area")
    duration_seconds = float(fixture.rainfall.elapsed_seconds[-1])
    out_dir.mkdir(parents=True, exist_ok=True)
    seed = SfincsModelBuilder().build(
        out_dir / "_seed_model",
        fixture.grid,
        fixture.rainfall,
    )
    engine = ResolvedEngine(
        executable=executable,
        source="explicit-full1m-performance-matrix",
        sha256=sha256_file(executable),
    )

    reports: dict[str, Any] = {}
    results: dict[str, SfincsRegularResult] = {}
    for name in _VARIANTS:
        root = out_dir / name
        model_dir = root / "model"
        if root.exists():
            shutil.rmtree(root)
        shutil.copytree(seed.model_dir, model_dir)
        settings = configure_variant(
            model_dir,
            variant=name,
            duration_seconds=duration_seconds,
        )
        execution = SfincsRunner().run(
            model_dir,
            logs_dir=root / "logs",
            engine=engine,
        )
        result = read_regular_result(execution.result_path)
        results[name] = result
        reports[name] = {
            "settings": {
                "dtmapout": float(settings["dtmapout"]),
                "dtmaxout": float(settings["dtmaxout"]),
                "storecumprcp": int(float(settings["storecumprcp"])),
                "storevel": int(float(settings["storevel"])),
                "alpha": float(settings["alpha"]),
            },
            "elapsed_seconds": execution.elapsed_seconds,
            "sfincs_map_size_bytes": execution.result_path.stat().st_size,
            "output": _result_shape_summary(execution.result_path),
            "timings": _parse_engine_timings(execution.stdout_log),
        }

    baseline = results["baseline"]
    comparisons = {
        name: _compare_results(baseline, result)
        for name, result in results.items()
        if name != "baseline"
    }
    payload = {
        "engine": {
            "path": str(executable),
            "sha256": engine.sha256,
        },
        "fixture": {
            "kind": "open_area",
            "size_cells": fixture.grid.width_cells,
            "duration_seconds": duration_seconds,
        },
        "variants": reports,
        "comparisons_to_baseline": comparisons,
    }
    atomic_write_json(out_dir / "performance_matrix.json", payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sfincs-exe", type=Path, required=True)
    args = parser.parse_args()

    payload = run_matrix(out_dir=args.out_dir, sfincs_exe=args.sfincs_exe)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
