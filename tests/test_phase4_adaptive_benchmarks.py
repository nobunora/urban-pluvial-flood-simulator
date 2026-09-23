from __future__ import annotations

import numpy as np
import pytest

from floodsim.validation.adaptive_benchmarks import build_adaptive_benchmark_fixture


@pytest.mark.parametrize(
    ("kind", "benchmark_class"),
    [
        ("open_area", "open_area"),
        ("urban_obstacle", "urban"),
        ("road_channel", "road_channel"),
    ],
)
def test_adaptive_benchmark_fixtures_are_deterministic_and_mass_conserving(
    kind: str,
    benchmark_class: str,
) -> None:
    fixture = build_adaptive_benchmark_fixture(kind)  # type: ignore[arg-type]
    grid = fixture.grid

    assert fixture.benchmark_class == benchmark_class
    assert grid.elevation_m.shape == (64, 64)
    assert grid.roof_allocation.relative_mass_error <= 1e-9
    assert np.all(grid.sfincs_mask[0, :] != 1)
    assert np.all(grid.sfincs_mask[-1, :] != 1)
    assert fixture.rainfall.elapsed_seconds[-1] == pytest.approx(1800.0)

    if kind == "open_area":
        assert not np.any(grid.building_mask)
        assert grid.road_mask is not None
        assert not np.any(grid.road_mask)
        assert fixture.important_flow_path is None
    elif kind == "urban_obstacle":
        assert np.any(grid.building_mask)
        assert np.all(grid.sfincs_mask[grid.building_mask] == 0)
        assert fixture.important_flow_path is None
    else:
        assert grid.road_mask is not None
        assert np.any(grid.road_mask)
        assert np.allclose(grid.manning_n[grid.road_mask], 0.020)
        assert fixture.important_flow_path is not None


def test_adaptive_benchmark_size_must_align_to_quadtree_base() -> None:
    with pytest.raises(ValueError, match="multiple of 32"):
        build_adaptive_benchmark_fixture("open_area", size=48)
