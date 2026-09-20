"""Deterministic visualization and native inspection for normalized results."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from pyproj import CRS, Transformer

from floodsim.domain.geometry import AnalysisArea
from floodsim.providers.common import local_crs

DISPLAY_DRY_THRESHOLD_M = 0.01
MIN_RENDER_PX = 256
MAX_RENDER_PX = 4096


class ResultViewError(RuntimeError):
    code = "RESULT_VIEW_FAILED"
    retryable = False


class ResultArtifactMissing(ResultViewError):
    code = "RESULT_ARTIFACT_MISSING"


class ResultTimeIndexInvalid(ResultViewError):
    code = "RESULT_TIME_INDEX_INVALID"


class PointOutsideResult(ResultViewError):
    code = "POINT_OUTSIDE_RESULT"


@dataclass(frozen=True)
class DepthBand:
    label: str
    minimum_m: float
    maximum_m: float | None
    rgba: tuple[int, int, int, int]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "min_m": self.minimum_m,
            "max_m": self.maximum_m,
            "color": "#{:02X}{:02X}{:02X}".format(*self.rgba[:3]),
        }


# Labels are fixed by docs/specs/v0.1-ui-implementation-spec.md.
# The initial colors are centralized here so server-rendered PNG and metadata stay identical.
DEPTH_BANDS: tuple[DepthBand, ...] = (
    DepthBand("0.01–0.05 m", 0.01, 0.05, (198, 232, 255, 210)),
    DepthBand("0.05–0.10 m", 0.05, 0.10, (91, 177, 255, 215)),
    DepthBand("0.10–0.30 m", 0.10, 0.30, (64, 110, 222, 220)),
    DepthBand("0.30–0.50 m", 0.30, 0.50, (126, 82, 196, 225)),
    DepthBand("0.50–1.00 m", 0.50, 1.00, (196, 65, 139, 230)),
    DepthBand("1.00 m以上", 1.00, None, (109, 27, 74, 235)),
)

GRID_RESOLUTION_COLORS: dict[int, tuple[int, int, int, int]] = {
    1: (38, 70, 83, 210),
    2: (42, 111, 151, 210),
    4: (61, 145, 128, 210),
    8: (122, 168, 116, 210),
    16: (186, 188, 125, 210),
    32: (208, 200, 173, 210),
}


@dataclass(frozen=True)
class NormalizedArrays:
    depth_time_m: np.ndarray
    max_depth_m: np.ndarray
    terrain_elevation_m: np.ndarray
    active_mask: np.ndarray
    time_values: tuple[str, ...]
    grid_resolution_m: np.ndarray | float
    velocity_u_mps: np.ndarray | None = None
    velocity_v_mps: np.ndarray | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return self.max_depth_m.shape


def depth_legend_metadata() -> list[dict[str, Any]]:
    return [band.to_metadata() for band in DEPTH_BANDS]


def load_normalized_arrays(path: str | Path) -> NormalizedArrays:
    source = Path(path)
    if not source.is_file():
        raise ResultArtifactMissing(f"normalized result file is missing: {source.name}")
    try:
        with np.load(source, allow_pickle=False) as archive:
            depth = np.asarray(archive["depth_time_m"], dtype=np.float32)
            max_depth = np.asarray(archive["max_depth_m"], dtype=np.float32)
            terrain = np.asarray(archive["terrain_elevation_m"], dtype=np.float32)
            active = np.asarray(archive["active_mask"], dtype=bool)
            time_values = tuple(str(value) for value in np.asarray(archive["time_values"]).tolist())
            raw_resolution = np.asarray(archive["grid_resolution_m"], dtype=np.float32)
            has_u = "velocity_u_mps" in archive.files
            has_v = "velocity_v_mps" in archive.files
            if has_u != has_v:
                raise ResultViewError("normalized velocity arrays must contain both u and v")
            velocity_u = (
                np.asarray(archive["velocity_u_mps"], dtype=np.float32) if has_u else None
            )
            velocity_v = (
                np.asarray(archive["velocity_v_mps"], dtype=np.float32) if has_v else None
            )
    except (KeyError, OSError, ValueError) as exc:
        raise ResultViewError("normalized result file is invalid") from exc

    if depth.ndim != 3 or max_depth.ndim != 2 or terrain.ndim != 2 or active.ndim != 2:
        raise ResultViewError("normalized result arrays have invalid dimensions")
    if depth.shape[1:] != max_depth.shape or terrain.shape != max_depth.shape or active.shape != max_depth.shape:
        raise ResultViewError("normalized result grid shapes are inconsistent")
    if depth.shape[0] != len(time_values):
        raise ResultViewError("normalized result time axis is inconsistent")
    if velocity_u is not None and (
        velocity_u.shape != depth.shape or velocity_v is None or velocity_v.shape != depth.shape
    ):
        raise ResultViewError("normalized velocity grid/time shape is inconsistent")

    if raw_resolution.ndim == 0:
        resolution: np.ndarray | float = float(raw_resolution)
    elif raw_resolution.shape == max_depth.shape:
        resolution = raw_resolution
    else:
        raise ResultViewError("normalized grid-resolution shape is inconsistent")

    return NormalizedArrays(
        depth_time_m=depth,
        max_depth_m=max_depth,
        terrain_elevation_m=terrain,
        active_mask=active,
        time_values=time_values,
        grid_resolution_m=resolution,
        velocity_u_mps=velocity_u,
        velocity_v_mps=velocity_v,
    )


def _clamped_max_px(max_px: int) -> int:
    return max(MIN_RENDER_PX, min(MAX_RENDER_PX, int(max_px)))


def _resize_png(image: Image.Image, *, max_px: int, categorical: bool) -> Image.Image:
    limit = _clamped_max_px(max_px)
    width, height = image.size
    longest = max(width, height)
    if longest <= limit:
        return image
    scale = limit / float(longest)
    target = (max(1, round(width * scale)), max(1, round(height * scale)))
    resampling = Image.Resampling.NEAREST if categorical else Image.Resampling.BILINEAR
    return image.resize(target, resample=resampling)


def _png_bytes(rgba: np.ndarray, *, max_px: int, categorical: bool) -> bytes:
    # Normalized arrays use row 0 as the southern edge. PNG row 0 must be north.
    north_up = np.flipud(rgba)
    image = Image.fromarray(north_up, mode="RGBA")
    image = _resize_png(image, max_px=max_px, categorical=categorical)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=6)
    return buffer.getvalue()


def _depth_rgba(values: np.ndarray, active_mask: np.ndarray) -> np.ndarray:
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    visible = active_mask & np.isfinite(values) & (values >= DISPLAY_DRY_THRESHOLD_M)
    for band in DEPTH_BANDS:
        mask = visible & (values >= band.minimum_m)
        if band.maximum_m is not None:
            mask &= values < band.maximum_m
        rgba[mask] = band.rgba
    return rgba


def render_max_depth_png(arrays: NormalizedArrays, *, max_px: int = MAX_RENDER_PX) -> bytes:
    return _png_bytes(
        _depth_rgba(arrays.max_depth_m, arrays.active_mask),
        max_px=max_px,
        categorical=True,
    )


def render_time_depth_png(
    arrays: NormalizedArrays,
    *,
    time_index: int,
    max_px: int = MAX_RENDER_PX,
) -> bytes:
    if time_index < 0 or time_index >= arrays.depth_time_m.shape[0]:
        raise ResultTimeIndexInvalid(f"time_index {time_index} is outside available output")
    return _png_bytes(
        _depth_rgba(arrays.depth_time_m[time_index], arrays.active_mask),
        max_px=max_px,
        categorical=True,
    )


def _grid_resolution_values(arrays: NormalizedArrays) -> np.ndarray:
    if isinstance(arrays.grid_resolution_m, float):
        return np.full(arrays.shape, arrays.grid_resolution_m, dtype=np.float32)
    return np.asarray(arrays.grid_resolution_m, dtype=np.float32)


def render_grid_resolution_png(
    arrays: NormalizedArrays,
    *,
    max_px: int = MAX_RENDER_PX,
) -> bytes:
    values = _grid_resolution_values(arrays)
    rgba = np.zeros((*arrays.shape, 4), dtype=np.uint8)
    for level, color in GRID_RESOLUTION_COLORS.items():
        rgba[arrays.active_mask & np.isclose(values, float(level))] = color
    return _png_bytes(rgba, max_px=max_px, categorical=True)



def flow_vectors_geojson(
    arrays: NormalizedArrays,
    *,
    area: AnalysisArea,
    time_index: int,
    max_vectors: int = 900,
    min_speed_mps: float = 0.01,
) -> dict[str, Any]:
    """Return sampled flow arrows as vector GeoJSON with speed metadata."""
    if time_index < 0 or time_index >= arrays.depth_time_m.shape[0]:
        raise ResultTimeIndexInvalid(f"time_index {time_index} is outside available output")
    if arrays.velocity_u_mps is None or arrays.velocity_v_mps is None:
        raise ResultArtifactMissing("flow-vector output is not available for this run")
    if max_vectors <= 0:
        raise ResultViewError("max_vectors must be positive")

    height, width = arrays.shape
    target_stride = int(np.ceil(np.sqrt((height * width) / float(max_vectors))))
    stride = max(4, target_stride)
    depth = arrays.depth_time_m[time_index]
    u = arrays.velocity_u_mps[time_index]
    v = arrays.velocity_v_mps[time_index]
    cell_width_m = area.width_m / float(width)
    cell_height_m = area.height_m / float(height)
    xmin = -area.width_m / 2.0
    ymin = -area.height_m / 2.0
    transformer = Transformer.from_crs(
        local_crs(area),
        CRS.from_epsg(4326),
        always_xy=True,
    )

    features: list[dict[str, Any]] = []
    for row0 in range(0, height, stride):
        row1 = min(height, row0 + stride)
        for col0 in range(0, width, stride):
            col1 = min(width, col0 + stride)
            wet = (
                arrays.active_mask[row0:row1, col0:col1]
                & np.isfinite(depth[row0:row1, col0:col1])
                & (depth[row0:row1, col0:col1] >= DISPLAY_DRY_THRESHOLD_M)
                & np.isfinite(u[row0:row1, col0:col1])
                & np.isfinite(v[row0:row1, col0:col1])
            )
            if not np.any(wet):
                continue

            mean_u = float(np.mean(u[row0:row1, col0:col1][wet]))
            mean_v = float(np.mean(v[row0:row1, col0:col1][wet]))
            speed = float(np.hypot(mean_u, mean_v))
            if not np.isfinite(speed) or speed < min_speed_mps:
                continue

            direction_x = mean_u / speed
            direction_y = mean_v / speed
            center_x = xmin + ((col0 + col1) / 2.0) * cell_width_m
            center_y = ymin + ((row0 + row1) / 2.0) * cell_height_m
            block_span_m = min(
                max(cell_width_m, 1e-6) * (col1 - col0),
                max(cell_height_m, 1e-6) * (row1 - row0),
            )
            arrow_length_m = max(2.0, min(14.0, block_span_m * 0.62))
            tail_scale = arrow_length_m * 0.42
            tip_scale = arrow_length_m * 0.58

            tail = (
                center_x - direction_x * tail_scale,
                center_y - direction_y * tail_scale,
            )
            tip = (
                center_x + direction_x * tip_scale,
                center_y + direction_y * tip_scale,
            )
            head_length = max(1.2, arrow_length_m * 0.28)
            head_angle = np.deg2rad(30.0)
            cos_a = float(np.cos(head_angle))
            sin_a = float(np.sin(head_angle))
            back_x = -direction_x
            back_y = -direction_y
            left_dir = (
                back_x * cos_a - back_y * sin_a,
                back_x * sin_a + back_y * cos_a,
            )
            right_dir = (
                back_x * cos_a + back_y * sin_a,
                -back_x * sin_a + back_y * cos_a,
            )
            left = (
                tip[0] + left_dir[0] * head_length,
                tip[1] + left_dir[1] * head_length,
            )
            right = (
                tip[0] + right_dir[0] * head_length,
                tip[1] + right_dir[1] * head_length,
            )

            def lonlat(point: tuple[float, float]) -> list[float]:
                lon, lat = transformer.transform(point[0], point[1])
                return [float(lon), float(lat)]

            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [
                            [lonlat(tail), lonlat(tip)],
                            [lonlat(tip), lonlat(left)],
                            [lonlat(tip), lonlat(right)],
                        ],
                    },
                    "properties": {
                        "speed_mps": speed,
                        "u_mps": mean_u,
                        "v_mps": mean_v,
                        "time_index": time_index,
                        "row": int((row0 + row1 - 1) // 2),
                        "column": int((col0 + col1 - 1) // 2),
                    },
                }
            )

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "speed_unit": "m/s",
            "min_speed_mps": float(min_speed_mps),
            "sample_stride_cells": stride,
            "arrow_count": len(features),
        },
    }


def render_flow_vectors_png(
    arrays: NormalizedArrays,
    *,
    time_index: int,
    max_px: int = MAX_RENDER_PX,
    min_speed_mps: float = 0.01,
) -> bytes:
    if time_index < 0 or time_index >= arrays.depth_time_m.shape[0]:
        raise ResultTimeIndexInvalid(f"time_index {time_index} is outside available output")
    if arrays.velocity_u_mps is None or arrays.velocity_v_mps is None:
        raise ResultArtifactMissing("flow-vector output is not available for this run")

    height, width = arrays.shape
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    stride = max(6, int(np.ceil(max(width, height) / 36)))
    depth = arrays.depth_time_m[time_index]
    u = arrays.velocity_u_mps[time_index]
    v = arrays.velocity_v_mps[time_index]

    for row0 in range(0, height, stride):
        row1 = min(height, row0 + stride)
        for col0 in range(0, width, stride):
            col1 = min(width, col0 + stride)
            wet = (
                arrays.active_mask[row0:row1, col0:col1]
                & np.isfinite(depth[row0:row1, col0:col1])
                & (depth[row0:row1, col0:col1] >= DISPLAY_DRY_THRESHOLD_M)
            )
            if not np.any(wet):
                continue
            block_u = u[row0:row1, col0:col1][wet]
            block_v = v[row0:row1, col0:col1][wet]
            mean_u = float(np.mean(block_u))
            mean_v = float(np.mean(block_v))
            speed = float(np.hypot(mean_u, mean_v))
            if not np.isfinite(speed) or speed < min_speed_mps:
                continue

            dx = mean_u / speed
            dy = mean_v / speed
            cx = (col0 + col1 - 1) / 2.0
            # Normalized arrays run south->north; PNG y increases north->south.
            cy = height - 1 - ((row0 + row1 - 1) / 2.0)
            length = min(16.0, 8.0 + 6.0 * min(speed, 1.0))
            x2 = cx + dx * length
            y2 = cy - dy * length
            x1 = cx - dx * length * 0.35
            y1 = cy + dy * length * 0.35

            draw.line((x1, y1, x2, y2), fill=(17, 24, 39, 235), width=2)
            head = 4.0
            perp_x, perp_y = -dy, -dx
            base_x = x2 - dx * head
            base_y = y2 + dy * head
            draw.polygon(
                [
                    (x2, y2),
                    (base_x + perp_x * head * 0.6, base_y + perp_y * head * 0.6),
                    (base_x - perp_x * head * 0.6, base_y - perp_y * head * 0.6),
                ],
                fill=(17, 24, 39, 235),
            )

    image = _resize_png(image, max_px=max_px, categorical=False)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=6)
    return buffer.getvalue()


def inspect_native_point(
    arrays: NormalizedArrays,
    *,
    area: AnalysisArea,
    lon_deg: float,
    lat_deg: float,
    time_index: int | None = None,
) -> dict[str, Any]:
    if time_index is not None and (time_index < 0 or time_index >= arrays.depth_time_m.shape[0]):
        raise ResultTimeIndexInvalid(f"time_index {time_index} is outside available output")

    transformer = Transformer.from_crs(
        CRS.from_epsg(4326),
        local_crs(area),
        always_xy=True,
    )
    x_m, y_m = transformer.transform(lon_deg, lat_deg)
    xmin = -area.width_m / 2.0
    ymin = -area.height_m / 2.0
    xmax = area.width_m / 2.0
    ymax = area.height_m / 2.0
    if not (xmin <= x_m < xmax and ymin <= y_m < ymax):
        raise PointOutsideResult("point is outside result bounds")

    row = int(np.floor(y_m - ymin))
    col = int(np.floor(x_m - xmin))
    height, width = arrays.shape
    if row < 0 or row >= height or col < 0 or col >= width:
        raise PointOutsideResult("point is outside result grid")

    time_value = arrays.time_values[time_index] if time_index is not None else None
    if not bool(arrays.active_mask[row, col]):
        return {
            "lon_deg": lon_deg,
            "lat_deg": lat_deg,
            "has_data": False,
            "row": row,
            "column": col,
            "time_index": time_index,
            "time_value": time_value,
            "depth_m": None,
            "max_depth_m": None,
            "max_time_index": None,
            "max_time_value": None,
            "terrain_elevation_m": None,
            "grid_resolution_m": None,
        }

    depth_series = arrays.depth_time_m[:, row, col]
    max_time_index = int(np.argmax(depth_series))
    max_time_value = arrays.time_values[max_time_index]
    depth_m = (
        float(depth_series[time_index])
        if time_index is not None
        else None
    )
    resolution_values = _grid_resolution_values(arrays)
    return {
        "lon_deg": lon_deg,
        "lat_deg": lat_deg,
        "has_data": True,
        "row": row,
        "column": col,
        "time_index": time_index,
        "time_value": time_value,
        "depth_m": depth_m,
        "max_depth_m": float(arrays.max_depth_m[row, col]),
        "max_time_index": max_time_index,
        "max_time_value": max_time_value,
        "terrain_elevation_m": float(arrays.terrain_elevation_m[row, col]),
        "grid_resolution_m": float(resolution_values[row, col]),
    }
