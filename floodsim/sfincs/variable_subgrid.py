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
        if size == 1:
            values = np.full(4, elevation[row, col], np.float64)
            pixel_size = 0.5
        else:
            values = (
                elevation[row : row + size, col : col + size]
                .copy()
                .reshape(-1)
                .astype(np.float64)
            )
            pixel_size = 1.0
        z, volume, lo, hi = subgrid_v_table(
            values, pixel_size, pixel_size, nr_levels, -20.0, 5.0
        )
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
        if size == 1:
            flat_z = np.full(4, elevations[0, 0], np.float64)
            flat_n = np.full(4, mannings[0, 0], np.float64)
        else:
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


@njit(cache=True)
def _selected_uv_metadata_arrays(
    levels,
    rows,
    cols,
    mu,
    mu1,
    mu2,
    nu,
    nu1,
    nu2,
    selected_min_level,
    selected_max_level,
):
    """Return selected UV rows and positions without sorting all UVs."""
    selected_count = 0
    for source in range(levels.size):
        for flag, first, second in (
            (mu[source], mu1[source], mu2[source]),
            (nu[source], nu1[source], nu2[source]),
        ):
            effective_level = levels[source] + (flag > 0)
            if selected_min_level <= effective_level <= selected_max_level:
                selected_count += first >= 0
                selected_count += flag > 0 and second >= 0

    uv_indices = np.empty(selected_count, np.int64)
    selected = np.empty((9, selected_count), np.int64)
    global_uv_index = 0
    output_index = 0
    for source in range(levels.size):
        for direction, flag, first, second in (
            (0, mu[source], mu1[source], mu2[source]),
            (1, nu[source], nu1[source], nu2[source]),
        ):
            effective_level = levels[source] + (flag > 0)
            for neighbor, allowed in (
                (first, first >= 0),
                (second, flag > 0 and second >= 0),
            ):
                if not allowed:
                    continue
                if selected_min_level <= effective_level <= selected_max_level:
                    uv_indices[output_index] = global_uv_index
                    selected[0, output_index] = effective_level
                    selected[1, output_index] = rows[source]
                    selected[2, output_index] = cols[source]
                    selected[3, output_index] = rows[neighbor]
                    selected[4, output_index] = cols[neighbor]
                    selected[5, output_index] = direction
                    selected[6, output_index] = source
                    selected[7, output_index] = neighbor
                    selected[8, output_index] = flag
                    output_index += 1
                global_uv_index += 1
    return uv_indices, selected


def _selected_uv_metadata(
    grid: xr.Dataset, selected_max_level: int = 2, selected_min_level: int = 1
) -> tuple[np.ndarray, np.ndarray]:
    return _selected_uv_metadata_arrays(
        np.asarray(grid["level"].values, dtype=np.int64) - 1,
        np.asarray(grid["n"].values, dtype=np.int64) - 1,
        np.asarray(grid["m"].values, dtype=np.int64) - 1,
        np.asarray(grid["mu"].values, dtype=np.int64),
        np.asarray(grid["mu1"].values, dtype=np.int64) - 1,
        np.asarray(grid["mu2"].values, dtype=np.int64) - 1,
        np.asarray(grid["nu"].values, dtype=np.int64),
        np.asarray(grid["nu1"].values, dtype=np.int64) - 1,
        np.asarray(grid["nu2"].values, dtype=np.int64) - 1,
        selected_min_level,
        selected_max_level,
    )


def build_optimized_2248_subgrid(
    grid: xr.Dataset,
    elevation_m: np.ndarray,
    manning_n: np.ndarray,
    *,
    nr_levels: int,
) -> tuple[xr.Dataset, dict[str, int]]:
    """Build 2/2/4/8 tables directly from aligned 1 m source arrays."""
    base_size = round(float(grid.attrs["dx"]))
    height = int(grid.attrs["nmax"]) * base_size
    width = int(grid.attrs["mmax"]) * base_size
    elevation = _padded(elevation_m, height, width)
    roughness = _padded(manning_n, height, width)
    face_levels = np.asarray(grid["level"].values, dtype=np.int64) - 1
    face_rows = np.asarray(grid["n"].values, dtype=np.int64) - 1
    face_cols = np.asarray(grid["m"].values, dtype=np.int64) - 1
    zmin, zmax, volmax, zlevel = _cell_tables(
        elevation,
        face_levels,
        face_rows,
        face_cols,
        base_size,
        nr_levels,
    )
    uv_indices, uv = _selected_uv_metadata(
        grid, selected_min_level=0, selected_max_level=int(face_levels.max())
    )
    if not np.array_equal(uv_indices, np.arange(uv_indices.size)):
        raise ValueError("direct UV metadata does not cover the complete ordered UV table")
    uv_values = _uv_tables(
        elevation,
        roughness,
        uv[0],
        uv[1],
        uv[2],
        uv[3],
        uv[4],
        uv[5],
        uv[8],
        zmin[uv[6]],
        zmin[uv[7]],
        base_size,
        nr_levels,
    )
    dataset = xr.Dataset(
        data_vars={
            "z_zmin": (("np",), zmin),
            "z_zmax": (("np",), zmax),
            "z_volmax": (("np",), volmax),
            "z_level": (("np", "levels"), zlevel),
            **{
                name: (("npuv", "levels") if values.ndim == 2 else ("npuv",), values)
                for name, values in zip(
                    (
                        "uv_zmin",
                        "uv_zmax",
                        "uv_havg",
                        "uv_nrep",
                        "uv_pwet",
                        "uv_ffit",
                        "uv_navg",
                    ),
                    uv_values,
                    strict=True,
                )
            },
        },
        attrs={"version": "1.0"},
    )
    face_sizes = base_size // (2**face_levels)
    uv_sizes = base_size // (2 ** uv[0])
    sample_evaluations = int(
        np.sum(np.maximum(face_sizes, 2) ** 2)
        + np.sum(np.maximum(uv_sizes, 2) ** 2)
    )
    return dataset, {
        "patched_faces": int(face_levels.size),
        "patched_uv_points": int(uv_indices.size),
        "patch_sample_evaluations": sample_evaluations,
    }


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
    """Replace coarse tables with aligned 1 m source-grid evaluations."""
    base_size = round(float(grid.attrs["dx"]))
    height = int(grid.attrs["nmax"]) * base_size
    width = int(grid.attrs["mmax"]) * base_size
    elevation = _padded(elevation_m, height, width)
    roughness = _padded(manning_n, height, width)
    face_levels = np.asarray(grid["level"].values, dtype=np.int64) - 1
    face_rows = np.asarray(grid["n"].values, dtype=np.int64) - 1
    face_cols = np.asarray(grid["m"].values, dtype=np.int64) - 1
    selected_max_level = 2
    face_indices = np.flatnonzero((face_levels >= 1) & (face_levels <= 2))
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

    uv_indices, uv = _selected_uv_metadata(grid, selected_max_level)
    values = _uv_tables(
        elevation,
        roughness,
        uv[0],
        uv[1],
        uv[2],
        uv[3],
        uv[4],
        uv[5],
        uv[8],
        subgrid["z_zmin"].values[uv[6]],
        subgrid["z_zmin"].values[uv[7]],
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
        + np.sum((base_size // (2 ** uv[0])) ** 2)
    )
    return {
        "patched_faces": int(face_indices.size),
        "patched_uv_points": int(uv_indices.size),
        "patch_sample_evaluations": patch_samples,
    }
