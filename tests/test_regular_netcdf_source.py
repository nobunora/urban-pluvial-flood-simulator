from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from floodsim.results.regular_netcdf_source import (
    RegularNetcdfSourceError,
    inspect_regular_netcdf_source,
    scan_regular_diagnostics,
    validate_source_identity,
)


def _write_result(path: Path) -> None:
    depth = np.asarray(
        [
            [[0.0, 0.2], [0.1, 0.0]],
            [[0.0, 0.3], [0.2, 0.0]],
        ],
        dtype=np.float32,
    )
    xr.Dataset(
        {
            "h": (("time", "n", "m"), depth),
            "hmax": (("timemax", "n", "m"), np.asarray([[[np.nan, 0.3], [0.2, np.nan]]], dtype=np.float32)),
            "zb": (("n", "m"), np.zeros((2, 2), dtype=np.float32)),
            "msk": (("n", "m"), np.ones((2, 2), dtype=np.int16)),
        },
        coords={"time": [0, 60], "timemax": [60]},
    ).to_netcdf(path)


def test_descriptor_is_relative_and_diagnostics_are_chunk_bounded(tmp_path: Path) -> None:
    model = tmp_path / "model"
    model.mkdir()
    source_path = model / "sfincs_map.nc"
    _write_result(source_path)

    source = inspect_regular_netcdf_source(
        source_path,
        model_dir=model,
        bounds={"west": 139.0, "south": 35.0, "east": 139.1, "north": 35.1},
        block_size_m=1.0,
    )

    assert source.source_filename == "sfincs_map.nc"
    assert source.time_values == ("0", "60")
    assert source.to_json()["schema_version"] == "regular-netcdf-source-v1"
    assert scan_regular_diagnostics(source, model_dir=model)["global_max_depth_m"] == pytest.approx(0.3)


def test_descriptor_rejects_source_outside_model_and_identity_change(tmp_path: Path) -> None:
    model = tmp_path / "model"
    model.mkdir()
    external = tmp_path / "sfincs_map.nc"
    _write_result(external)
    with pytest.raises(RegularNetcdfSourceError, match="below the model"):
        inspect_regular_netcdf_source(
            external,
            model_dir=model,
            bounds={"west": 0, "south": 0, "east": 1, "north": 1},
            block_size_m=1.0,
        )

    source_path = model / "sfincs_map.nc"
    _write_result(source_path)
    source = inspect_regular_netcdf_source(
        source_path,
        model_dir=model,
        bounds={"west": 0, "south": 0, "east": 1, "north": 1},
        block_size_m=1.0,
    )
    source_path.write_bytes(source_path.read_bytes() + b"changed")
    with pytest.raises(RegularNetcdfSourceError, match="identity"):
        validate_source_identity(source, model_dir=model)
