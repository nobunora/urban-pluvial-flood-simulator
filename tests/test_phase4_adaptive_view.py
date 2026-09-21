from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from floodsim.domain.geometry import AnalysisArea, GeoBounds, LonLat
from floodsim.results.view import (
    DEPTH_BANDS,
    GRID_RESOLUTION_COLORS,
    AdaptiveNormalizedArrays,
    flow_vectors_geojson,
    inspect_native_point,
    load_normalized_arrays,
    render_grid_resolution_png,
    render_max_depth_png,
    render_time_depth_png,
)


def _area() -> AnalysisArea:
    return AnalysisArea(
        mode="rectangle",
        bounds=GeoBounds(
            west_deg=138.999,
            south_deg=34.999,
            east_deg=139.001,
            north_deg=35.001,
        ),
        center=LonLat(lon_deg=139.0, lat_deg=35.0),
        width_m=4.0,
        height_m=4.0,
        area_m2=16.0,
    )


def _arrays() -> AdaptiveNormalizedArrays:
    return AdaptiveNormalizedArrays(
        depth_time_m=np.asarray(
            [[0.02, 0.20, 0.0, 0.0], [0.06, 1.20, 0.0, 0.40]],
            dtype=np.float32,
        ),
        max_depth_m=np.asarray([0.06, 1.20, np.nan, 0.40], dtype=np.float32),
        terrain_elevation_m=np.asarray([1.0, 2.0, np.nan, 4.0], dtype=np.float32),
        active_mask=np.asarray([True, True, False, True]),
        time_values=("0", "60"),
        face_resolution_m=np.asarray([2, 2, 2, 2], dtype=np.int16),
        face_row_index=np.asarray([0, 0, 1, 1], dtype=np.int32),
        face_col_index=np.asarray([0, 1, 0, 1], dtype=np.int32),
        face_source_overlap_area_m2=np.asarray([4.0, 4.0, 4.0, 4.0]),
        source_height_cells=4,
        source_width_cells=4,
    )


def _rgba(content: bytes) -> np.ndarray:
    with Image.open(BytesIO(content)) as image:
        return np.asarray(image.convert("RGBA"))


def test_adaptive_loader_keeps_face_native_arrays(tmp_path: Path) -> None:
    arrays = _arrays()
    path = tmp_path / "normalized_adaptive_faces.npz"
    np.savez_compressed(
        path,
        storage_kind=np.asarray("quadtree_faces"),
        depth_time_m=arrays.depth_time_m,
        max_depth_m=arrays.max_depth_m,
        terrain_elevation_m=arrays.terrain_elevation_m,
        active_mask=arrays.active_mask,
        time_values=np.asarray(arrays.time_values),
        face_resolution_m=arrays.face_resolution_m,
        face_row_index=arrays.face_row_index,
        face_col_index=arrays.face_col_index,
        face_source_overlap_area_m2=arrays.face_source_overlap_area_m2,
        source_height_cells=np.int32(4),
        source_width_cells=np.int32(4),
    )

    loaded = load_normalized_arrays(path)

    assert isinstance(loaded, AdaptiveNormalizedArrays)
    assert loaded.depth_time_m.shape == (2, 4)
    assert loaded.shape == (4, 4)


def test_adaptive_png_rendering_expands_only_selected_face_field() -> None:
    arrays = _arrays()

    maximum = _rgba(render_max_depth_png(arrays))
    first = _rgba(render_time_depth_png(arrays, time_index=0))
    resolution = _rgba(render_grid_resolution_png(arrays))

    assert maximum.shape == (4, 4, 4)
    # Internal southern face row becomes the bottom PNG half.
    assert tuple(maximum[3, 0]) == DEPTH_BANDS[1].rgba
    assert tuple(maximum[3, 3]) == DEPTH_BANDS[-1].rgba
    # Inactive north-west face remains transparent.
    assert maximum[0, 0, 3] == 0
    assert tuple(resolution[3, 0]) == (20, 27, 36, 245)
    assert tuple(resolution[2, 1]) == GRID_RESOLUTION_COLORS[2]
    assert tuple(first[3, 0]) == DEPTH_BANDS[0].rgba


def test_adaptive_point_inspection_returns_native_face_value() -> None:
    inspected = inspect_native_point(
        _arrays(),
        area=_area(),
        lon_deg=139.0,
        lat_deg=35.0,
        time_index=1,
    )

    assert inspected["has_data"] is True
    assert inspected["row"] == 2
    assert inspected["column"] == 2
    assert inspected["depth_m"] == pytest.approx(0.40)
    assert inspected["max_depth_m"] == pytest.approx(0.40)
    assert inspected["grid_resolution_m"] == pytest.approx(2.0)
    assert inspected["terrain_elevation_m"] == pytest.approx(4.0)



def test_adaptive_flow_vectors_use_native_face_centers() -> None:
    arrays = _arrays()
    u = np.zeros_like(arrays.depth_time_m)
    vv = np.zeros_like(arrays.depth_time_m)
    u[1, 3] = 0.3
    vv[1, 3] = 0.4
    arrays = AdaptiveNormalizedArrays(
        **{
            **arrays.__dict__,
            "velocity_u_mps": u,
            "velocity_v_mps": vv,
        }
    )

    payload = flow_vectors_geojson(
        arrays,
        area=_area(),
        time_index=1,
        max_vectors=10,
    )

    assert payload["metadata"]["arrow_count"] == 1
    assert payload["metadata"]["sampling_method"] == "native-quadtree-face-top-speed"
    feature = payload["features"][0]
    assert feature["properties"]["face_index"] == 3
    assert feature["properties"]["grid_resolution_m"] == pytest.approx(2.0)
    assert feature["properties"]["speed_mps"] == pytest.approx(0.5)
