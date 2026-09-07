from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr
import xugrid as xu
from pyproj import CRS

from floodsim.sfincs.model_builder import _load_sfincs_model, _sfincs_environment
from floodsim.sfincs.quadtree_writer import write_quadtree_grid_compat


class _FakeConfig:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get(self, key: str, *, abs_path: bool = False) -> Path | None:
        if key == "qtrfile":
            return self.path
        return None


class _FakeModel:
    def __init__(self, path: Path) -> None:
        self.config = _FakeConfig(path)


class _AuthorityBackedComponent:
    def __init__(self, path: Path) -> None:
        self.crs = CRS.from_epsg(3857)
        self.model = _FakeModel(path)
        self.calls: list[tuple[str | Path, list[object]]] = []

    def write(self, *, filename: str | Path, data_vars: list[object]) -> None:
        self.calls.append((filename, data_vars))


def test_authority_backed_quadtree_delegates_to_rc3_writer(tmp_path: Path) -> None:
    output = tmp_path / "sfincs.nc"
    component = _AuthorityBackedComponent(output)

    written = write_quadtree_grid_compat(component)

    assert written == output
    assert component.calls == [("sfincs.nc", [])]


def test_authorityless_quadtree_round_trips_via_wkt_only(tmp_path: Path) -> None:
    with _sfincs_environment():
        SfincsModel = _load_sfincs_model()
        model = SfincsModel(root=tmp_path, mode="w+", write_gis=False)
        _ = model.config.data

    component = model.quadtree_grid
    component.create(
        x0=0.0,
        y0=0.0,
        nmax=2,
        mmax=2,
        dx=32.0,
        dy=32.0,
        rotation=0.0,
        epsg=3857,
    )
    expected_crs = CRS.from_proj4(
        "+proj=aeqd +lat_0=35.0005 +lon_0=139.0005 "
        "+datum=WGS84 +units=m +no_defs"
    )
    component.data.grid.set_crs(expected_crs, allow_override=True)
    model.config.set("epsg", None)
    model.config.set("crsgeo", 0)
    assert component.crs.equals(expected_crs)
    assert component.crs.to_epsg() is None

    original_faces = int(component.data.sizes["mesh2d_nFaces"])
    original_level = component.data["level"].values.copy()
    written = write_quadtree_grid_compat(component)

    assert written == tmp_path / "sfincs.nc"
    with xr.open_dataset(written) as raw:
        attrs = raw["mesh2d_crs"].attrs
        assert "epsg" not in attrs
        assert "epsg_code" not in attrs
        assert CRS.from_wkt(attrs["crs_wkt"]).equals(expected_crs)
        assert raw["mesh2d_node_x"].attrs["units"] == "m"
        assert raw["mesh2d_node_y"].attrs["units"] == "m"
        assert raw["mesh2d_node_x"].attrs["grid_mapping"] == "mesh2d_crs"
        assert raw["mesh2d_node_y"].attrs["grid_mapping"] == "mesh2d_crs"

    loaded = xu.load_dataset(written)
    try:
        assert loaded.grid.crs is not None
        assert loaded.grid.crs.equals(expected_crs)
        assert loaded.grid.crs.to_epsg() is None
        assert int(loaded.sizes["mesh2d_nFaces"]) == original_faces
        np.testing.assert_array_equal(loaded["level"].values, original_level)
    finally:
        loaded.close()

    assert model.config.get("qtrfile") == "sfincs.nc"
    assert model.config.get("epsg", None) is None
    assert model.config.get("crsgeo") == 0
