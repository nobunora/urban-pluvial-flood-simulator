"""Quadtree writer compatibility for authority-less projected CRS in rc3.

HydroMT-SFINCS 2.0.0rc3 writes full CF/WKT CRS metadata for quadtree grids,
but its writer also emits optional EPSG authority attributes. The canonical
local AEQD CRS used by this project intentionally has no EPSG authority, so
rc3 tries to serialize ``epsg=None`` and ``EPSG:None`` and NetCDF rejects the
file.

This adapter is deliberately narrow. Authority-backed CRS delegates to the
upstream writer unchanged. Authority-less CRS follows the upstream
``data_vars=[]`` main-file path while omitting only invalid authority metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from pyproj import CRS


class QuadtreeSerializationError(RuntimeError):
    """Raised when the pinned rc3 quadtree compatibility contract is violated."""


def _validate_authorityless_crs_metadata(dataset: Any, crs: CRS) -> None:
    """Verify WKT is authoritative and remove only invalid EPSG metadata."""

    if "mesh2d_crs" not in dataset:
        raise QuadtreeSerializationError("quadtree Dataset has no mesh2d_crs variable")

    attrs = dataset["mesh2d_crs"].attrs
    crs_wkt = attrs.get("crs_wkt")
    if not isinstance(crs_wkt, str) or not crs_wkt:
        raise QuadtreeSerializationError("quadtree Dataset has no usable crs_wkt")
    try:
        dataset_crs = CRS.from_wkt(crs_wkt)
    except Exception as exc:
        raise QuadtreeSerializationError("quadtree Dataset crs_wkt is invalid") from exc
    if not dataset_crs.equals(crs):
        raise QuadtreeSerializationError(
            "quadtree Dataset crs_wkt does not match the model CRS"
        )

    epsg = attrs.get("epsg")
    if epsg is not None:
        raise QuadtreeSerializationError(
            "authority-less model CRS has conflicting EPSG metadata"
        )
    attrs.pop("epsg", None)

    epsg_code = attrs.get("epsg_code")
    if epsg_code not in (None, "EPSG:None"):
        raise QuadtreeSerializationError(
            "authority-less model CRS has conflicting EPSG code metadata"
        )
    attrs.pop("epsg_code", None)


def _prepare_authorityless_dataset(component: Any) -> Any:
    """Mirror the pinned rc3 main quadtree Dataset preparation without EPSG."""

    crs = component.crs
    if crs.to_epsg() is not None:
        raise QuadtreeSerializationError(
            "authority-less Dataset preparation received an authority-backed CRS"
        )

    dataset = component.data.ugrid.to_dataset()
    _validate_authorityless_crs_metadata(dataset, crs)

    if "dep" in dataset:
        dataset = dataset.rename({"dep": "z"})

    attrs = dict(component.data.attrs)
    attrs["Conventions"] = "CF-1.8 UGRID-1.0 Deltares-0.10"
    dataset.attrs = attrs

    for variable in list(dataset.data_vars):
        if dataset[variable].dtype in (np.int8, np.uint8):
            dataset[variable] = dataset[variable].astype(np.int32)

    crs_var_name = "mesh2d_crs" if "mesh2d_crs" in dataset else "crs"
    coordinate_units = {
        "mesh2d_node_x": "degrees_east" if crs.is_geographic else "m",
        "mesh2d_node_y": "degrees_north" if crs.is_geographic else "m",
    }
    for coordinate, units in coordinate_units.items():
        if coordinate not in dataset:
            continue
        dataset[coordinate].attrs.setdefault("units", units)
        dataset[coordinate].attrs["grid_mapping"] = crs_var_name

    return dataset


def write_quadtree_grid_compat(
    component: Any,
    filename: str | Path = "sfincs.nc",
) -> Path:
    """Write a pinned-rc3 quadtree grid while preserving authority-less AEQD.

    For an authority-backed CRS this delegates to the ordinary rc3 writer with
    ``data_vars=[]``. For the project's authority-less local AEQD it writes the
    equivalent main quadtree Dataset but omits only invalid optional EPSG
    authority attributes. Full WKT/CF/UGRID metadata remains authoritative.

    The caller owns any separate-variable policy. This function intentionally
    follows rc3's ``data_vars=[]`` behavior so all currently attached quadtree
    variables remain in the main file.
    """

    crs = component.crs
    if crs.to_epsg() is not None:
        component.write(filename=filename, data_vars=[])
        written = component.model.config.get("qtrfile", abs_path=True)
        if written is None:
            raise QuadtreeSerializationError("rc3 writer did not configure qtrfile")
        return Path(written)

    dataset = _prepare_authorityless_dataset(component)
    try:
        written = component.model.config.get_set_file_variable(
            "qtrfile",
            value=filename,
            default="sfincs.nc",
        )
        if written is None:
            raise QuadtreeSerializationError("could not resolve quadtree output path")
        written.parent.mkdir(parents=True, exist_ok=True)

        component.model.config.set("epsg", None)
        component.model.config.set("crsgeo", int(crs.is_geographic))
        dataset.to_netcdf(written)
        return Path(written)
    finally:
        dataset.close()
