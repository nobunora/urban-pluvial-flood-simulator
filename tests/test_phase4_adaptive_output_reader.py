from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from floodsim.sfincs.output_reader import SfincsResultError, read_quadtree_result


def _layout(path: Path) -> Path:
    np.savez_compressed(
        path,
        resolution_m=np.asarray([2, 2, 2, 2], dtype=np.int16),
        row_index=np.asarray([0, 0, 1, 1], dtype=np.int32),
        col_index=np.asarray([0, 1, 0, 1], dtype=np.int32),
        source_overlap_area_m2=np.asarray([4.0, 4.0, 4.0, 4.0]),
        sfincs_mask=np.asarray([1, 1, 3, 0], dtype=np.uint8),
        source_height_cells=np.int32(4),
        source_width_cells=np.int32(4),
    )
    return path


def _result(path: Path, *, negative_hmax: bool = False) -> Path:
    hmax0 = -0.1 if negative_hmax else 0.3
    dataset = xr.Dataset(
        {
            "h": (
                ("time", "nmesh2d_face"),
                np.asarray(
                    [
                        [-0.05, np.nan, 0.0, 0.0],
                        [0.20, 0.40, 0.0, 0.0],
                    ],
                    dtype=np.float32,
                ),
            ),
            "hmax": (
                ("timemax", "nmesh2d_face"),
                np.asarray([[hmax0, np.nan, np.nan, np.nan]], dtype=np.float32),
            ),
            "zs": (
                ("time", "nmesh2d_face"),
                np.asarray([[1.0, 1.0, 1.0, 1.0], [1.2, 1.4, 1.0, 1.0]], dtype=np.float32),
            ),
            "zb": (
                ("nmesh2d_face",),
                np.asarray([1.0, 1.0, 1.0, 1.0], dtype=np.float32),
            ),
            "msk": (
                ("nmesh2d_face",),
                np.asarray([1, 1, 3, 0], dtype=np.int32),
            ),
            "subgrid_volume": (
                ("time", "nmesh2d_face"),
                np.asarray(
                    [[0.0, 0.0, 0.0, 0.0], [0.8, 1.6, 0.0, 0.0]],
                    dtype=np.float32,
                ),
            ),
            "u": (
                ("time", "nmesh2d_face"),
                np.asarray([[5.0, 5.0, 0.0, 0.0], [1.0, 2.0, 0.0, 0.0]], dtype=np.float32),
            ),
            "v": (
                ("time", "nmesh2d_face"),
                np.asarray([[5.0, 5.0, 0.0, 0.0], [3.0, 4.0, 0.0, 0.0]], dtype=np.float32),
            ),
        },
        coords={"time": [0.0, 60.0], "timemax": [60.0]},
    )
    dataset.to_netcdf(path)
    return path


def test_quadtree_reader_preserves_native_faces_and_dry_depth_policy(tmp_path: Path) -> None:
    result = read_quadtree_result(
        _result(tmp_path / "sfincs_map.nc"),
        layout_path=_layout(tmp_path / "adaptive_face_layout.npz"),
    )

    assert result.depth_time_m.shape == (2, 4)
    assert result.max_depth_m.shape == (4,)
    assert result.layout.face_count == 4
    assert result.dry_fill_depth_values == 1
    assert result.negative_depth_clipped_values == 1
    assert result.depth_time_m[0, 0] == 0.0
    assert result.depth_time_m[0, 1] == 0.0
    assert result.max_depth_m[0] == pytest.approx(0.3)
    assert result.max_depth_m[1] == pytest.approx(0.4)
    assert result.hmax_reconstructed_cells == 1
    assert result.excluded_boundary_cells == 1
    assert result.global_max_depth_m == pytest.approx(0.4)
    assert result.flow_vectors_available
    assert result.subgrid_volume_m3 is not None
    assert np.nansum(result.subgrid_volume_m3[-1]) == pytest.approx(2.4)
    assert result.velocity_u_mps is not None
    assert result.velocity_u_mps[0, 0] == 0.0
    assert np.isnan(result.depth_time_m[:, 2:]).all()


def test_quadtree_reader_rejects_negative_finite_hmax(tmp_path: Path) -> None:
    with pytest.raises(SfincsResultError, match="negative finite"):
        read_quadtree_result(
            _result(tmp_path / "sfincs_map.nc", negative_hmax=True),
            layout_path=_layout(tmp_path / "adaptive_face_layout.npz"),
        )


def test_quadtree_reader_rejects_face_order_mask_mismatch(tmp_path: Path) -> None:
    result_path = _result(tmp_path / "sfincs_map.nc")
    layout_path = _layout(tmp_path / "adaptive_face_layout.npz")
    with np.load(layout_path, allow_pickle=False) as archive:
        payload = {name: archive[name] for name in archive.files}
    payload["sfincs_mask"] = np.asarray([1, 3, 1, 0], dtype=np.uint8)
    np.savez_compressed(layout_path, **payload)

    with pytest.raises(SfincsResultError, match="face order/mask"):
        read_quadtree_result(result_path, layout_path=layout_path)



def test_quadtree_reader_rejects_infinite_active_depth(tmp_path: Path) -> None:
    result_path = _result(tmp_path / "sfincs_map.nc")
    with xr.open_dataset(result_path) as dataset:
        loaded = dataset.load()
    values = np.asarray(loaded["h"].values, dtype=np.float32)
    values[0, 0] = np.inf
    loaded["h"] = (("time", "nmesh2d_face"), values)
    loaded.to_netcdf(result_path, mode="w")

    with pytest.raises(SfincsResultError, match="infinite values"):
        read_quadtree_result(
            result_path,
            layout_path=_layout(tmp_path / "adaptive_face_layout.npz"),
        )


def test_quadtree_reader_clips_finite_negative_subgrid_storage_with_diagnostics(
    tmp_path: Path,
) -> None:
    result_path = _result(tmp_path / "sfincs_map.nc")
    with xr.open_dataset(result_path) as dataset:
        loaded = dataset.load()
    values = np.asarray(loaded["subgrid_volume"].values, dtype=np.float32)
    values[1, 0] = -0.0016041
    values[1, 1] = -1.0e-9
    loaded["subgrid_volume"] = (("time", "nmesh2d_face"), values)
    loaded.to_netcdf(result_path, mode="w")

    result = read_quadtree_result(
        result_path,
        layout_path=_layout(tmp_path / "adaptive_face_layout.npz"),
    )

    assert result.subgrid_volume_m3 is not None
    assert result.negative_subgrid_volume_clipped_values == 2
    assert result.min_raw_active_subgrid_volume_m3 == pytest.approx(-0.0016041)
    assert np.nanmin(result.subgrid_volume_m3) == 0.0
