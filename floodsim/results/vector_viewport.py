"""Viewport flow-vector sampling at a display-space target density."""

from __future__ import annotations

from typing import Any

import numpy as np
from pyproj import CRS, Transformer

from floodsim.domain.geometry import AnalysisArea
from floodsim.providers.common import local_crs
from floodsim.results.view import (
    DISPLAY_DRY_THRESHOLD_M,
    AdaptiveNormalizedArrays,
    NormalizedArrays,
    ResultArrays,
    ResultArtifactMissing,
    ResultTimeIndexInvalid,
    ResultViewError,
)

_MIN_SPEED_MPS = 0.001


def _viewport_cell_bounds(
    arrays: ResultArrays,
    *,
    area: AnalysisArea,
    west: float,
    south: float,
    east: float,
    north: float,
) -> tuple[int, int, int, int]:
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ResultViewError("viewport bounds are invalid")
    to_local = Transformer.from_crs(CRS.from_epsg(4326), local_crs(area), always_xy=True)
    corners = [
        to_local.transform(west, south),
        to_local.transform(west, north),
        to_local.transform(east, south),
        to_local.transform(east, north),
    ]
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    xmin = -area.width_m / 2.0
    ymin = -area.height_m / 2.0
    height, width = arrays.shape
    cell_width_m = area.width_m / float(width)
    cell_height_m = area.height_m / float(height)
    col0 = max(0, min(width, int(np.floor((min(xs) - xmin) / cell_width_m))))
    col1 = max(0, min(width, int(np.ceil((max(xs) - xmin) / cell_width_m))))
    row0 = max(0, min(height, int(np.floor((min(ys) - ymin) / cell_height_m))))
    row1 = max(0, min(height, int(np.ceil((max(ys) - ymin) / cell_height_m))))
    return row0, row1, col0, col1


def _face_lookup(arrays: AdaptiveNormalizedArrays) -> np.ndarray:
    lookup = np.full(arrays.shape, -1, dtype=np.int32)
    for face in range(arrays.face_resolution_m.size):
        size = int(arrays.face_resolution_m[face])
        r0 = int(arrays.face_row_index[face]) * size
        c0 = int(arrays.face_col_index[face]) * size
        r1 = min(arrays.source_height_cells, r0 + size)
        c1 = min(arrays.source_width_cells, c0 + size)
        if r1 > r0 and c1 > c0:
            lookup[r0:r1, c0:c1] = face
    return lookup


def flow_vectors_viewport_geojson(
    arrays: ResultArrays,
    *,
    area: AnalysisArea,
    time_index: int,
    west: float,
    south: float,
    east: float,
    north: float,
    stride: int,
    min_speed_mps: float = _MIN_SPEED_MPS,
) -> dict[str, Any]:
    """Return viewport samples at ``stride`` metres, independent of grid size."""
    if stride < 1:
        raise ResultViewError("stride must be a positive integer")
    if time_index < 0 or time_index >= arrays.depth_time_m.shape[0]:
        raise ResultTimeIndexInvalid(f"time_index {time_index} is outside available output")
    if arrays.velocity_u_mps is None or arrays.velocity_v_mps is None:
        raise ResultArtifactMissing("flow-vector output is not available for this run")

    row0, row1, col0, col1 = _viewport_cell_bounds(
        arrays, area=area, west=west, south=south, east=east, north=north
    )
    to_wgs84 = Transformer.from_crs(local_crs(area), CRS.from_epsg(4326), always_xy=True)
    xmin = -area.width_m / 2.0
    ymin = -area.height_m / 2.0
    adaptive = isinstance(arrays, AdaptiveNormalizedArrays)
    if adaptive:
        assert isinstance(arrays, AdaptiveNormalizedArrays)
        face_lookup = _face_lookup(arrays)
    else:
        face_lookup = None
    cell_width_m = area.width_m / float(arrays.shape[1])
    cell_height_m = area.height_m / float(arrays.shape[0])
    cell_spacing_m = min(cell_width_m, cell_height_m)
    stride_cells = max(1, round(float(stride) / cell_spacing_m))
    arrow_length_m = 0.8 * float(stride)
    features: list[dict[str, Any]] = []

    for row in range(row0, row1, stride_cells):
        for col in range(col0, col1, stride_cells):
            face = int(face_lookup[row, col]) if face_lookup is not None else -1
            if adaptive:
                assert isinstance(arrays, AdaptiveNormalizedArrays)
                if face < 0 or not bool(arrays.active_mask[face]):
                    continue
                depth = float(arrays.depth_time_m[time_index, face])
                u = float(arrays.velocity_u_mps[time_index, face])
                v = float(arrays.velocity_v_mps[time_index, face])
                grid_resolution = float(arrays.face_resolution_m[face])
            else:
                assert isinstance(arrays, NormalizedArrays)
                if not bool(arrays.active_mask[row, col]):
                    continue
                depth = float(arrays.depth_time_m[time_index, row, col])
                u = float(arrays.velocity_u_mps[time_index, row, col])
                v = float(arrays.velocity_v_mps[time_index, row, col])
                grid_resolution = (
                    float(arrays.grid_resolution_m)
                    if np.ndim(arrays.grid_resolution_m) == 0
                    else float(np.asarray(arrays.grid_resolution_m)[row, col])
                )

            speed = float(np.hypot(u, v))
            if (
                not np.isfinite(depth)
                or depth < DISPLAY_DRY_THRESHOLD_M
                or not np.isfinite(speed)
                or speed < min_speed_mps
            ):
                continue

            dx = u / speed
            dy = v / speed
            cx = xmin + (col + 0.5) * cell_width_m
            cy = ymin + (row + 0.5) * cell_height_m
            tail = (cx - dx * arrow_length_m * 0.42, cy - dy * arrow_length_m * 0.42)
            tip = (cx + dx * arrow_length_m * 0.58, cy + dy * arrow_length_m * 0.58)
            head = arrow_length_m * 0.28
            angle = np.deg2rad(30.0)
            ca, sa = float(np.cos(angle)), float(np.sin(angle))
            bx, by = -dx, -dy
            left = (tip[0] + (bx * ca - by * sa) * head, tip[1] + (bx * sa + by * ca) * head)
            right = (tip[0] + (bx * ca + by * sa) * head, tip[1] + (-bx * sa + by * ca) * head)

            def lonlat(point: tuple[float, float]) -> list[float]:
                lon, lat = to_wgs84.transform(*point)
                return [float(lon), float(lat)]

            props: dict[str, Any] = {
                "speed_mps": speed,
                "u_mps": u,
                "v_mps": v,
                "time_index": time_index,
                "row": row,
                "column": col,
                "grid_resolution_m": grid_resolution,
            }
            if adaptive:
                props["face_index"] = face
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [
                        [lonlat(tail), lonlat(tip)],
                        [lonlat(tip), lonlat(left)],
                        [lonlat(tip), lonlat(right)],
                    ],
                },
                "properties": props,
            })

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "speed_unit": "m/s",
            "min_speed_mps": float(min_speed_mps),
            "sample_stride_cells": stride_cells,
            "target_spacing_m": float(stride),
            "arrow_length_m": arrow_length_m,
            "arrow_count": len(features),
            "sampling_method": "viewport-target-spacing-m",
            "canonical_grid_spacing_m": cell_spacing_m,
            "stride_anchor_row": 0,
            "stride_anchor_column": 0,
            "viewport": {"west": west, "south": south, "east": east, "north": north},
        },
    }
