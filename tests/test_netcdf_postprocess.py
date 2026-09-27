from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from floodsim.results.netcdf_postprocess import downsample_regular_netcdf


def test_downsample_regular_netcdf_keeps_fifteen_minute_frames(tmp_path: Path) -> None:
    path = tmp_path / "sfincs_map.nc"
    times = np.datetime64("2000-01-01T00:00:00") + np.arange(61) * np.timedelta64(60, "s")
    values = np.arange(61 * 2 * 3, dtype=np.float32).reshape(61, 2, 3)
    dataset = xr.Dataset(
        {
            "h": (("time", "n", "m"), values),
            "u": (("time", "n", "m"), values + 1),
            "v": (("time", "n", "m"), values + 2),
            "hmax": (("timemax", "n", "m"), values[-1:]),
            "zb": (("n", "m"), np.ones((2, 3), dtype=np.float32)),
            "msk": (("n", "m"), np.ones((2, 3), dtype=np.int8)),
        },
        coords={"time": times, "timemax": np.asarray([3600], dtype=np.int32)},
    )
    encoding = {
        name: {"chunksizes": (1, 2, 3), "zlib": True}
        for name in ("h", "u", "v", "hmax")
    }
    dataset.to_netcdf(path, engine="netcdf4", encoding=encoding)

    result = downsample_regular_netcdf(path, interval_seconds=900)

    assert result.source_time_count == 61
    assert result.output_time_count == 5
    assert result.selected_indices == (0, 15, 30, 45, 60)
    with xr.open_dataset(path) as reduced:
        np.testing.assert_array_equal(reduced["time"].values, times[[0, 15, 30, 45, 60]])
        np.testing.assert_array_equal(reduced["h"].values, values[[0, 15, 30, 45, 60]])
        np.testing.assert_array_equal(reduced["hmax"].values, values[-1:])
