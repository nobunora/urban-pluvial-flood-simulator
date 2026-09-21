from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest
import xarray as xr
from pyproj import CRS

pytest.importorskip("hydromt_sfincs")

from floodsim.domain.rainfall import RainfallTimeSeries
from floodsim.preprocessing.adaptive_grid import build_adaptive_grid
from floodsim.preprocessing.full_grid import FullGridProduct
from floodsim.preprocessing.roof_rainfall import allocate_roof_rainfall
from floodsim.sfincs.adaptive_model_builder import SfincsAdaptiveModelBuilder


def _grid(size: int = 96) -> FullGridProduct:
    crs = CRS.from_proj4(
        "+proj=aeqd +lat_0=35.0 +lon_0=139.0 +datum=WGS84 +units=m +no_defs"
    )
    yy, xx = np.mgrid[0:size, 0:size]
    terrain = (0.001 * xx + 0.002 * yy).astype(np.float32)
    buildings = np.zeros((size, size), dtype=bool)
    road = np.zeros((size, size), dtype=bool)
    mask = np.ones((size, size), dtype=np.uint8)
    mask[0, :] = 3
    mask[-1, :] = 3
    mask[:, 0] = 3
    mask[:, -1] = 3
    manning = np.full((size, size), 0.030, dtype=np.float32)
    roof = allocate_roof_rainfall(buildings)
    return FullGridProduct(
        elevation_m=terrain,
        building_mask=buildings,
        sfincs_mask=mask,
        manning_n=manning,
        rain_weight=roof.rain_weight.astype(np.float32),
        roof_allocation=roof,
        width_cells=size,
        height_cells=size,
        dx_m=1.0,
        dy_m=1.0,
        x0_m=0.0,
        y0_m=0.0,
        crs_wkt=crs.to_wkt(),
        road_mask=road,
    )


def _rainfall() -> RainfallTimeSeries:
    return RainfallTimeSeries(
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        elapsed_seconds=[0.0, 60.0],
        intensity_mm_per_h=[12.0, 12.0],
        source_metadata={"fixture": "adaptive-model-builder"},
    )


def test_adaptive_builder_writes_engine_consumable_model_inputs(tmp_path):
    grid = _grid()
    adaptive = build_adaptive_grid(grid)
    result = SfincsAdaptiveModelBuilder().build(
        tmp_path / "model",
        grid,
        adaptive,
        _rainfall(),
    )

    root = result.model_dir
    expected = {
        "sfincs.nc",
        "sfincs_subgrid.nc",
        "sfincs_netampr.nc",
        "sfincs.inp",
        "model_build_report.json",
    }
    assert expected.issubset({path.name for path in root.iterdir()})

    assert result.report["grid_type"] == "quadtree"
    assert result.report["accuracy_mode"] == "adaptive"
    assert result.report["hydraulic_cells"] > 0
    assert result.report["full_1m_equivalent_cells"] == grid.cell_count
    assert result.report["subgrid"]["source_terrain_resolution_m"] == 1.0
    assert result.report["subgrid"]["nr_subgrid_pixels"] == 2

    with xr.open_dataset(root / "sfincs.nc") as dataset:
        assert int(dataset.sizes["mesh2d_nFaces"]) == result.report["hydraulic_cells"]
        assert "mask" in dataset
        assert "manning" in dataset
        assert "mesh2d_crs" in dataset
        attrs = dataset["mesh2d_crs"].attrs
        assert "epsg" not in attrs
        assert "epsg_code" not in attrs
        assert CRS.from_wkt(str(attrs["crs_wkt"])).equals(
            CRS.from_wkt(grid.crs_wkt)
        )

    with xr.open_dataset(root / "sfincs_subgrid.nc") as dataset:
        assert "z_level" in dataset.data_vars

    with xr.open_dataset(root / "sfincs_netampr.nc") as dataset:
        assert dataset["Precipitation"].dims == ("time", "y", "x")
        assert dataset["Precipitation"].shape[1:] == (
            grid.height_cells,
            grid.width_cells,
        )
        np.testing.assert_allclose(dataset["Precipitation"].values, 12.0)

    config = (root / "sfincs.inp").read_text(encoding="utf-8")
    assert "qtrfile" in config
    assert "sbgfile" in config
    assert "netamprfile" in config
