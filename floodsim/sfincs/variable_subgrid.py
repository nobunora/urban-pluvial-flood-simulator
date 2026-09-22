"""Direct aligned-grid patches for the 2/2/4/8 SFINCS subgrid strategy."""

from __future__ import annotations

import numpy as np
import xarray as xr
from hydromt_sfincs.workflows.subgrid import subgrid_q_table, subgrid_v_table
from numba import njit


@njit(cache=True)
def _cell_tables(elevation, levels, rows, cols, base_size, nr_levels):
    count = levels.size
    zmin = np.empty(count, np.float32)
    zmax = np.empty(count, np.float32)
    volmax = np.empty(count, np.float32)
    zlevel = np.empty((count, nr_levels), np.float32)
    for i in range(count):
        size = base_size // (2 ** levels[i])
        row, col = rows[i] * size, cols[i] * size
        values = elevation[row : row + size, col : col + size].copy().reshape(-1)
        z, volume, lo, hi = subgrid_v_table(values, 1.0, 1.0, nr_levels, -20.0, 5.0)
        zmin[i], zmax[i], volmax[i] = lo, hi, volume[-1]
        zlevel[i, :] = z
    return zmin, zmax, volmax, zlevel


@njit(cache=True)
def _uv_tables(
    elevation,
    roughness,
    levels,
    rows,
    cols,
    neighbor_rows,
    neighbor_cols,
    directions,
    face_types,
    zmin_a,
    zmin_b,
    base_size,
    nr_levels,
):
    count = levels.size
    uv_zmin = np.full(count, np.nan, np.float32)
    uv_zmax = np.full(count, np.nan, np.float32)
    uv_havg = np.full((count, nr_levels), np.nan, np.float32)
    uv_nrep = np.full((count, nr_levels), np.nan, np.float32)
    uv_pwet = np.full((count, nr_levels), np.nan, np.float32)
    uv_ffit = np.full(count, np.nan, np.float32)
    uv_navg = np.full(count, np.nan, np.float32)
    for i in range(count):
        if not np.isfinite(zmin_a[i]) or not np.isfinite(zmin_b[i]):
            continue
        size = base_size // (2 ** levels[i])
        row, col = rows[i] * size, cols[i] * size
        if face_types[i] > 0:
            if directions[i] == 0:
                start_row = neighbor_rows[i] * size
                start_col = neighbor_cols[i] * size - size // 2
            else:
                start_row = neighbor_rows[i] * size - size // 2
                start_col = neighbor_cols[i] * size
        elif directions[i] == 0:
            start_row, start_col = row, col + size // 2
        else:
            start_row, start_col = row + size // 2, col
        elevations = elevation[
            start_row : start_row + size, start_col : start_col + size
        ].copy()
        mannings = roughness[
            start_row : start_row + size, start_col : start_col + size
        ].copy()
        if directions[i] == 0:
            elevations = elevations.T.copy()
            mannings = mannings.T.copy()
        flat_z = elevations.reshape(-1).astype(np.float64)
        flat_n = mannings.reshape(-1).astype(np.float64)
        if not np.isfinite(flat_z).all() or not np.isfinite(flat_n).all():
            continue
        lo, hi, havg, nrep, pwet, ffit, navg, _ = subgrid_q_table(
            flat_z,
            flat_n,
            nr_levels,
            0.01,
            2,
            zmin_a[i],
            zmin_b[i],
            "min",
            "manning",
        )
        uv_zmin[i], uv_zmax[i] = lo, hi
        uv_havg[i, :], uv_nrep[i, :], uv_pwet[i, :] = havg, nrep, pwet
        uv_ffit[i], uv_navg[i] = ffit, navg
    return uv_zmin, uv_zmax, uv_havg, uv_nrep, uv_pwet, uv_ffit, uv_navg


def _uv_metadata(grid: xr.Dataset) -> np.ndarray:
    levels = np.asarray(grid["level"].values, dtype=np.int64) - 1
    rows = np.asarray(grid["n"].values, dtype=np.int64) - 1
    cols = np.asarray(grid["m"].values, dtype=np.int64) - 1
    indices = np.arange(levels.size, dtype=np.int64)
    chunks: list[np.ndarray] = []
    for direction, flag, first, second in (
        (0, grid["mu"].values, grid["mu1"].values - 1, grid["mu2"].values - 1),
        (1, grid["nu"].values, grid["nu1"].values - 1, grid["nu2"].values - 1),
    ):
        flag = np.asarray(flag, dtype=np.int64)
        for sequence, neighbor, allowed in (
            (0, np.asarray(first, dtype=np.int64), first >= 0),
            (1, np.asarray(second, dtype=np.int64), (flag > 0) & (second >= 0)),
        ):
            keep = np.asarray(allowed) & ((sequence == 0) | (flag > 0))
            source = indices[keep]
            target = neighbor[keep]
            key = source * 4 + direction * 2 + sequence
            chunks.append(
                np.vstack(
                    (
                        key,
                        levels[source] + (flag[keep] > 0),
                        rows[source],
                        cols[source],
                        rows[target],
                        cols[target],
                        np.full(source.size, direction),
                        source,
                        target,
                        flag[keep],
                    )
                )
            )
    packed = np.concatenate(chunks, axis=1)
    return packed[1:, np.argsort(packed[0], kind="stable")]


def _padded(values: np.ndarray, height: int, width: int) -> np.ndarray:
    result = np.full((height, width), np.nan, dtype=np.float32)
    result[: values.shape[0], : values.shape[1]] = values
    return result


def apply_2248_subgrid_patch(
    subgrid: xr.Dataset,
    grid: xr.Dataset,
    elevation_m: np.ndarray,
    manning_n: np.ndarray,
    *,
    nr_levels: int,
) -> dict[str, int]:
    """Replace 4 m and 8 m global-2x2 tables with aligned 4x4/8x8 tables."""
    base_size = round(float(grid.attrs["dx"]))
    height = int(grid.attrs["nmax"]) * base_size
    width = int(grid.attrs["mmax"]) * base_size
    elevation = _padded(elevation_m, height, width)
    roughness = _padded(manning_n, height, width)
    face_levels = np.asarray(grid["level"].values, dtype=np.int64) - 1
    face_rows = np.asarray(grid["n"].values, dtype=np.int64) - 1
    face_cols = np.asarray(grid["m"].values, dtype=np.int64) - 1
    face_indices = np.flatnonzero((face_levels == 1) | (face_levels == 2))
    zmin, zmax, volmax, zlevel = _cell_tables(
        elevation,
        face_levels[face_indices],
        face_rows[face_indices],
        face_cols[face_indices],
        base_size,
        nr_levels,
    )
    for name, values in (
        ("z_zmin", zmin),
        ("z_zmax", zmax),
        ("z_volmax", volmax),
        ("z_level", zlevel),
    ):
        subgrid[name].values[face_indices] = values

    uv = _uv_metadata(grid)
    uv_indices = np.flatnonzero((uv[0] == 1) | (uv[0] == 2))
    values = _uv_tables(
        elevation,
        roughness,
        uv[0, uv_indices],
        uv[1, uv_indices],
        uv[2, uv_indices],
        uv[3, uv_indices],
        uv[4, uv_indices],
        uv[5, uv_indices],
        uv[8, uv_indices],
        subgrid["z_zmin"].values[uv[6, uv_indices]],
        subgrid["z_zmin"].values[uv[7, uv_indices]],
        base_size,
        nr_levels,
    )
    for name, patch in zip(
        ("uv_zmin", "uv_zmax", "uv_havg", "uv_nrep", "uv_pwet", "uv_ffit", "uv_navg"),
        values,
        strict=True,
    ):
        subgrid[name].values[uv_indices] = patch
    patch_samples = int(
        np.sum((base_size // (2 ** face_levels[face_indices])) ** 2)
        + np.sum((base_size // (2 ** uv[0, uv_indices])) ** 2)
    )
    return {
        "patched_faces": int(face_indices.size),
        "patched_uv_points": int(uv_indices.size),
        "patch_sample_evaluations": patch_samples,
    }
