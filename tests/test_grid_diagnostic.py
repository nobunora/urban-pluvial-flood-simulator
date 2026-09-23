from __future__ import annotations

import json

import numpy as np

from floodsim.domain.geometry import GeoBounds
from floodsim.providers.common import ProviderProvenance
from scripts.diagnose_grid_run import _load_vectors


def test_load_vectors_rehydrates_persisted_source_refs(tmp_path) -> None:
    provenance = ProviderProvenance.create(
        "plateau",
        "PLATEAU",
        GeoBounds(
            west_deg=139.0,
            south_deg=35.0,
            east_deg=139.01,
            north_deg=35.01,
        ),
        "test attribution",
        "https://example.invalid/terms",
        acquired_at_utc="2026-01-01T00:00:00+00:00",
    )
    (tmp_path / "vectors_manifest.json").write_text(
        json.dumps({"provenance": provenance.to_dict()}),
        encoding="utf-8",
    )

    building = np.asarray(
        [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]],
        dtype=float,
    )
    road = np.asarray([[0.0, 1.0], [2.0, 1.0]], dtype=float)
    road_polygon = np.asarray(
        [[0.0, 0.8], [2.0, 0.8], [2.0, 1.2], [0.0, 1.2], [0.0, 0.8]],
        dtype=float,
    )
    np.savez_compressed(
        tmp_path / "buildings.npz",
        buildings=np.asarray([building], dtype=object),
    )
    np.savez_compressed(
        tmp_path / "basemap_vectors.npz",
        roads=np.asarray([road], dtype=object),
        road_polygons=np.asarray([road_polygon], dtype=object),
    )

    vectors = _load_vectors(tmp_path)

    assert vectors.provenance.provider_id == "plateau"
    assert len(vectors.buildings) == 1
    assert len(vectors.road_lines) == 1
    assert len(vectors.road_polygons) == 1
    np.testing.assert_allclose(vectors.buildings[0], building)
