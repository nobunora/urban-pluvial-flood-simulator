from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from floodsim.domain.geometry import AnalysisArea, GeoBounds, LonLat
from floodsim.domain.manifest import Limitations
from floodsim.results.normalize import normalize_quadtree_result
from floodsim.sfincs.output_reader import AdaptiveFaceLayout, SfincsQuadtreeResult


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


def _result() -> SfincsQuadtreeResult:
    layout = AdaptiveFaceLayout(
        resolution_m=np.asarray([2, 2, 2, 2], dtype=np.int16),
        row_index=np.asarray([0, 0, 1, 1], dtype=np.int32),
        col_index=np.asarray([0, 1, 0, 1], dtype=np.int32),
        source_overlap_area_m2=np.asarray([4.0, 4.0, 4.0, 4.0]),
        sfincs_mask=np.asarray([1, 1, 3, 0], dtype=np.uint8),
        source_height_cells=4,
        source_width_cells=4,
    )
    return SfincsQuadtreeResult(
        depth_time_m=np.asarray(
            [[0.0, 0.1, np.nan, np.nan], [0.2, 0.4, np.nan, np.nan]],
            dtype=np.float32,
        ),
        max_depth_m=np.asarray([0.2, 0.4, np.nan, np.nan], dtype=np.float32),
        terrain_elevation_m=np.asarray([1.0, 2.0, np.nan, np.nan], dtype=np.float32),
        active_mask=np.asarray([True, True, False, False]),
        time_values=("0", "60"),
        layout=layout,
        velocity_u_mps=np.asarray(
            [[0.0, 0.0, np.nan, np.nan], [0.1, 0.2, np.nan, np.nan]],
            dtype=np.float32,
        ),
        velocity_v_mps=np.asarray(
            [[0.0, 0.0, np.nan, np.nan], [0.3, 0.4, np.nan, np.nan]],
            dtype=np.float32,
        ),
        hmax_reconstructed_cells=1,
        negative_depth_clipped_values=2,
        min_raw_active_depth_m=-0.01,
        excluded_boundary_cells=1,
    )


def test_adaptive_normalizer_keeps_native_face_storage(tmp_path: Path) -> None:
    result = normalize_quadtree_result(
        _result(),
        area=_area(),
        results_dir=tmp_path,
        limitations=Limitations(),
        run_summary={"requested_accuracy_mode": "adaptive"},
    )

    assert result.arrays_path.name == "normalized_adaptive_faces.npz"
    assert result.metadata["grid_level_summary"] == {"2m": 2}
    assert result.metadata["max_depth_summary"]["global_max_depth_m"] == pytest.approx(0.4)
    assert result.metadata["flow_vectors_available"] is True
    assert "native quadtree-face order" in result.metadata["no_data_policy"]

    with np.load(result.arrays_path, allow_pickle=False) as archive:
        assert str(archive["storage_kind"].item()) == "quadtree_faces"
        assert archive["depth_time_m"].shape == (2, 4)
        assert archive["max_depth_m"].shape == (4,)
        assert archive["face_resolution_m"].tolist() == [2, 2, 2, 2]
        assert archive["face_row_index"].tolist() == [0, 0, 1, 1]
        assert archive["face_col_index"].tolist() == [0, 1, 0, 1]
        assert int(archive["source_height_cells"].item()) == 4
        assert int(archive["source_width_cells"].item()) == 4
        assert "velocity_u_mps" in archive.files
        assert "velocity_v_mps" in archive.files
