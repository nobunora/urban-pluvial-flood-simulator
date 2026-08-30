import pytest


spike = pytest.importorskip("scripts.sfincs_phase0_spike")
pytest.importorskip("hydromt_sfincs")
xr = pytest.importorskip("xarray")


def test_phase0_builds_all_model_forms(tmp_path):
    result = spike.run(tmp_path)

    assert result["regular_build"]["files"] == [
        "sfincs.dep",
        "sfincs.ind",
        "sfincs.inp",
        "sfincs.manning",
        "sfincs.msk",
    ]
    assert result["quadtree_build"]["files"] == ["sfincs.inp", "sfincs.nc"]
    assert result["quadtree_build"]["cells"] > 64
    assert result["subgrid_build"]["source_raster_resolution_m"] == 5
    assert result["subgrid_build"]["hydraulic_grid_resolution_m"] == 10
    assert "z_level" in result["subgrid_build"]["subgrid_variables"]
    assert result["execution"]["status"] == "blocked"


def test_phase0_result_reader_uses_direct_netcdf_contract(tmp_path):
    output = xr.Dataset(
        {
            "h": (("time", "n", "m"), [[[0.0, 0.0], [0.0, 0.0]]]),
            "hmax": (("timemax", "n", "m"), [[[0.0, 0.0], [0.0, 0.0]]]),
            "zs": (("time", "n", "m"), [[[0.0, 0.0], [0.0, 0.0]]]),
            "zb": (("n", "m"), [[0.0, 0.0], [0.0, 0.0]]),
            "msk": (("n", "m"), [[1, 1], [1, 1]]),
        }
    )
    for name in ("h", "hmax", "zs", "zb"):
        output[name].attrs["units"] = "m"
    output["msk"].attrs["units"] = "-"
    result_path = tmp_path / "sfincs_map.nc"
    output.to_netcdf(result_path)

    result = spike.read_result(result_path)

    assert result["max_abs_depth_m"] == 0
    assert result["variables"]["h"] == ["time", "n", "m"]
