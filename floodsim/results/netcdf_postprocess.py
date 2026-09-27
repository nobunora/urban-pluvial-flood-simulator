"""Bounded post-processing for publishable regular-grid NetCDF results."""

from __future__ import annotations

import os
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import netCDF4
import numpy as np
import xarray as xr


@dataclass(frozen=True)
class TemporalDownsampleResult:
    source_time_count: int
    output_time_count: int
    selected_indices: tuple[int, ...]
    source_size_bytes: int
    output_size_bytes: int


def downsample_regular_netcdf(
    source_path: str | Path,
    *,
    interval_seconds: int = 900,
) -> TemporalDownsampleResult:
    """Atomically retain interval-aligned frames while copying one source chunk at a time."""
    path = Path(source_path)
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    indices = _interval_indices(path, interval_seconds)
    source_size = path.stat().st_size
    temporary = path.with_name(f".{path.name}.downsample.tmp")
    temporary.unlink(missing_ok=True)
    try:
        _copy_selected_times(path, temporary, indices)
        with xr.open_dataset(temporary) as dataset:
            if int(dataset.sizes.get("time", 0)) != len(indices):
                raise RuntimeError("downsampled NetCDF time dimension is invalid")
        output_size = temporary.stat().st_size
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return TemporalDownsampleResult(
        source_time_count=indices[-1] + 1,
        output_time_count=len(indices),
        selected_indices=indices,
        source_size_bytes=source_size,
        output_size_bytes=output_size,
    )


def _interval_indices(path: Path, interval_seconds: int) -> tuple[int, ...]:
    with xr.open_dataset(path) as dataset:
        if "time" not in dataset or not int(dataset.sizes.get("time", 0)):
            raise ValueError("NetCDF result has no time coordinate")
        values = np.asarray(dataset["time"].values)
    elapsed = _elapsed_seconds(values)
    targets = np.arange(0.0, elapsed[-1] + 0.5, float(interval_seconds))
    indices: list[int] = []
    tolerance = max(1.0, interval_seconds * 0.01)
    for target in targets:
        index = int(np.argmin(np.abs(elapsed - target)))
        if abs(float(elapsed[index] - target)) > tolerance:
            raise ValueError(f"NetCDF result has no frame at {target:g} seconds")
        if not indices or index != indices[-1]:
            indices.append(index)
    if elapsed[-1] - targets[-1] > tolerance:
        indices.append(len(elapsed) - 1)
    return tuple(indices)


def _elapsed_seconds(values: np.ndarray) -> np.ndarray:
    first = values[0]
    if np.issubdtype(values.dtype, np.datetime64) or np.issubdtype(values.dtype, np.timedelta64):
        return np.asarray((values - first) / np.timedelta64(1, "s"), dtype=np.float64)
    if np.issubdtype(values.dtype, np.number):
        return np.asarray(values - first, dtype=np.float64)
    elapsed = []
    for value in values:
        difference = value - first
        elapsed.append(float(difference.total_seconds()))
    return np.asarray(elapsed, dtype=np.float64)


def _copy_selected_times(source_path: Path, target_path: Path, indices: tuple[int, ...]) -> None:
    with netCDF4.Dataset(source_path, "r") as source, netCDF4.Dataset(
        target_path, "w", format=source.data_model
    ) as target:
        target.setncatts(source.__dict__)
        for name, dimension in source.dimensions.items():
            size = len(indices) if name == "time" else len(dimension)
            target.createDimension(name, None if dimension.isunlimited() else size)
        for name, source_variable in source.variables.items():
            target_variable = _create_variable(target, name, source_variable, len(indices))
            _copy_variable(source_variable, target_variable, indices)


def _create_variable(
    target: netCDF4.Dataset,
    name: str,
    source: netCDF4.Variable,
    output_time_count: int,
) -> netCDF4.Variable:
    kwargs: dict[str, object] = {}
    if "_FillValue" in source.ncattrs():
        kwargs["fill_value"] = source.getncattr("_FillValue")
    chunking = source.chunking()
    if isinstance(chunking, list):
        chunks = list(chunking)
        if "time" in source.dimensions:
            chunks[source.dimensions.index("time")] = min(
                chunks[source.dimensions.index("time")], output_time_count
            )
        kwargs["chunksizes"] = tuple(chunks)
    filters = source.filters() or {}
    if filters.get("zlib"):
        kwargs.update(
            zlib=True,
            complevel=int(filters.get("complevel", 4)),
            shuffle=bool(filters.get("shuffle", True)),
        )
    if filters.get("fletcher32"):
        kwargs["fletcher32"] = True
    # netCDF4's overload stubs cannot express the runtime encoding dictionary
    # returned by Variable.filters()/chunking().
    variable = target.createVariable(  # type: ignore[call-overload]
        name, source.datatype, source.dimensions, **kwargs
    )
    attributes = {key: source.getncattr(key) for key in source.ncattrs() if key != "_FillValue"}
    if attributes:
        variable.setncatts(attributes)
    return variable


def _copy_variable(
    source: netCDF4.Variable,
    target: netCDF4.Variable,
    indices: tuple[int, ...],
) -> None:
    if not source.dimensions:
        target.assignValue(source.getValue())
        return
    chunking = source.chunking()
    chunks = (
        tuple(int(value) for value in chunking)
        if isinstance(chunking, list)
        else tuple(max(1, min(size, 256)) for size in source.shape)
    )
    target_shape = tuple(len(indices) if dim == "time" else size for dim, size in zip(source.dimensions, source.shape))
    block_counts = tuple((size + chunk - 1) // chunk for size, chunk in zip(target_shape, chunks))
    time_axis = source.dimensions.index("time") if "time" in source.dimensions else None
    for block in product(*(range(count) for count in block_counts)):
        target_key = tuple(
            slice(offset * chunk, min((offset + 1) * chunk, size))
            for offset, chunk, size in zip(block, chunks, target_shape)
        )
        if time_axis is None:
            target[target_key] = source[target_key]
            continue
        time_slice = target_key[time_axis]
        for target_time in range(time_slice.start, time_slice.stop):
            source_selection: list[slice | int] = list(target_key)
            destination_selection: list[slice | int] = list(target_key)
            source_selection[time_axis] = indices[target_time]
            destination_selection[time_axis] = target_time
            target[tuple(destination_selection)] = source[tuple(source_selection)]
