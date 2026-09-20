"""Deterministic visualization and native inspection for normalized results."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
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
    except (KeyError, OSError, ValueError) as exc:
        raise ResultViewError("normalized result file is invalid") from exc

    if depth.ndim != 3 or max_depth.ndim != 2 or terrain.ndim != 2 or active.ndim != 2:
        raise ResultViewError("normalized result arrays have invalid dimensions")
    if depth.shape[1:] != max_depth.shape or terrain.shape != max_depth.shape or active.shape != max_depth.shape:
        raise ResultViewError("normalized result grid shapes are inconsistent")
    if depth.shape[0] != len(time_values):
        raise ResultViewError("normalized result time axis is inconsistent")

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
        categorical=False,
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
        categorical=False,
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
            "terrain_elevation_m": None,
            "grid_resolution_m": None,
        }

    depth_m = (
        float(arrays.depth_time_m[time_index, row, col])
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
        "terrain_elevation_m": float(arrays.terrain_elevation_m[row, col]),
        "grid_resolution_m": float(resolution_values[row, col]),
    }
