import json

import numpy as np
import pytest
from pyproj import CRS, Transformer

from floodsim.domain.geometry import AnalysisArea, GeoBounds, LonLat
from floodsim.providers.common import (
    ProviderCoverageError,
    ProviderParseError,
    ProviderProvenance,
    ProviderRequestError,
    ProviderUnavailableError,
    request_with_retry,
)
from floodsim.providers.gsi_elevation import GsiElevationProvider
from floodsim.providers.osm import OsmProvider, OsmVectors
from floodsim.providers.plateau import PlateauProvider, extract_citygml
from floodsim.providers.vectors import acquire_vectors


def rectangle() -> AnalysisArea:
    return AnalysisArea(
        mode="rectangle",
        bounds=GeoBounds(west_deg=139.7668, south_deg=35.6808, east_deg=139.7673, north_deg=35.6813),
        center=LonLat(lon_deg=139.76705, lat_deg=35.68105),
        width_m=40.0,
        height_m=20.0,
        area_m2=800.0,
    )


class Response:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


def provenance(provider_id="test"):
    return ProviderProvenance.create(
        provider_id, "Test", rectangle().bounds, "Test attribution", "https://example.test/terms",
        acquired_at_utc="2026-09-02T00:00:00+00:00",
    )


def test_gsi_rectangular_shape_priority_counts_and_orientation(monkeypatch):
    import floodsim.providers.gsi_elevation as gsi

    requested_layers = []

    def fake_mosaic(session, layer, zoom, bounds, cache_dir, **kwargs):
        requested_layers.append(layer)
        return np.zeros((1, 1), dtype=np.float32), layer

    def fake_reproject(mosaic, transform, area, grid_m):
        value = {"dem1a_png": np.nan, "dem5a_png": 10.0, "dem5b_png": 20.0}[transform]
        return np.full((5, 9), value, dtype=np.float32)

    monkeypatch.setattr(gsi, "provider_mosaic", fake_mosaic)
    monkeypatch.setattr(gsi, "reproject_provider", fake_reproject)
    product = GsiElevationProvider(session=object()).acquire(
        rectangle(), grid_m=5.0,
        providers=(("DEM1A", "dem1a_png", 17), ("DEM5A", "dem5a_png", 15), ("DEM5B", "dem5b_png", 15)),
        acquired_at_utc="2026-09-02T00:00:00+00:00",
    )
    assert product.z.shape == (5, 9)
    assert product.x.tolist() == [-20.0, -15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0]
    assert product.y.tolist() == [-10.0, -5.0, 0.0, 5.0, 10.0]
    assert product.z[0, 0] == 10.0
    assert product.provenance.source_details["provider_counts"] == {"DEM1A": 0, "DEM5A": 45}
    assert requested_layers == ["dem1a_png", "dem5a_png"]


def test_gsi_coverage_failure_is_typed_and_not_zero(monkeypatch):
    import floodsim.providers.gsi_elevation as gsi

    monkeypatch.setattr(gsi, "provider_mosaic", lambda *args, **kwargs: None)
    with pytest.raises(ProviderCoverageError):
        GsiElevationProvider(session=object()).acquire(
            rectangle(), grid_m=10.0, max_nearest_fill_fraction=0.1,
            providers=(("DEM1A", "dem1a_png", 17),),
        )


def test_retry_policy_retries_without_sleep_and_converts_error():
    session = Session([Response(503), Response(503), Response(503)])
    with pytest.raises(ProviderRequestError):
        request_with_retry(session, "GET", "https://example.test", sleeper=lambda seconds: None)
    assert [call[2]["timeout"] for call in session.calls] == [(10.0, 60.0)] * 3


def test_plateau_rectangular_clip_and_axis_order():
    citygml = b'''<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"
      xmlns:gml="http://www.opengis.net/gml" xmlns:bldg="http://www.opengis.net/citygml/building/2.0">
      <core:cityObjectMember><bldg:Building><bldg:lod0FootPrint><gml:MultiSurface><gml:surfaceMember>
      <gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>35.68100 139.76700 0 35.68100 139.76710 0 35.68110 139.76710 0 35.68110 139.76700 0 35.68100 139.76700 0</gml:posList>
      </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod0FootPrint></bldg:Building></core:cityObjectMember>
      </core:CityModel>'''
    buildings, lines, polygons = extract_citygml(citygml, rectangle(), margin_m=0.0)
    assert len(buildings) == 1
    assert not lines and not polygons
    assert np.max(np.abs(buildings[0][:, 0])) <= 20.0
    assert np.max(np.abs(buildings[0][:, 1])) <= 10.0


def test_plateau_provider_writes_provenance_and_prefers_road_polygons(tmp_path):
    citygml = b'''<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"
      xmlns:gml="http://www.opengis.net/gml" xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
      xmlns:tran="http://www.opengis.net/citygml/transportation/2.0">
      <core:cityObjectMember><bldg:Building><bldg:lod0RoofEdge><gml:MultiSurface><gml:surfaceMember>
      <gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>35.68100 139.76700 0 35.68100 139.76710 0 35.68110 139.76710 0 35.68110 139.76700 0 35.68100 139.76700 0</gml:posList>
      </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod0RoofEdge></bldg:Building></core:cityObjectMember>
      <core:cityObjectMember><tran:Road><gml:Polygon><gml:exterior><gml:LinearRing><gml:posList>35.68099 139.76699 0 35.68099 139.76702 0 35.68101 139.76702 0 35.68101 139.76699 0 35.68099 139.76699 0</gml:posList></gml:LinearRing></gml:exterior></gml:Polygon></tran:Road></core:cityObjectMember>
      <core:cityObjectMember><tran:Road><gml:LineString><gml:posList>35.68100 139.76700 0 35.68105 139.76720 0</gml:posList></gml:LineString></tran:Road></core:cityObjectMember>
      </core:CityModel>'''
    catalog = {"cities": [{"cityCode": "13101", "cityName": "test", "year": 2024, "spec": "3", "files": {
        "bldg": [{"url": "https://example.test/building.gml"}],
        "tran": [{"url": "https://example.test/transport.gml"}],
    }}]}
    result = PlateauProvider(session=Session([Response(payload=catalog), Response(content=citygml), Response(content=citygml)])).acquire(
        rectangle(), cache_dir=tmp_path / "cache", out_dir=tmp_path / "vectors",
        margin_m=0.0, acquired_at_utc="2026-09-02T00:00:00+00:00",
    )
    assert len(result.buildings) == 1
    assert len(result.road_polygons) == 1
    assert len(result.road_lines) == 1
    assert result.provenance.source_details["feature_types"] == ["bldg", "tran"]
    assert json.loads((tmp_path / "vectors" / "vectors_manifest.json").read_text(encoding="utf-8"))["provider"] == "PLATEAU"


def test_expected_empty_provider_failures_are_typed(tmp_path):
    plateau_session = Session([Response(payload={"cities": []})])
    with pytest.raises(ProviderUnavailableError):
        PlateauProvider(session=plateau_session).acquire(rectangle(), cache_dir=tmp_path)
    osm_session = Session([Response(payload={"elements": []})])
    with pytest.raises(ProviderUnavailableError):
        OsmProvider(session=osm_session).acquire(rectangle(), cache_dir=tmp_path)


def test_osm_rectangular_parsing_and_provenance(tmp_path):
    area = rectangle()
    local = CRS.from_proj4(f"+proj=aeqd +lat_0={area.center.lat_deg} +lon_0={area.center.lon_deg} +datum=WGS84 +units=m +no_defs")
    to_ll = Transformer.from_crs(local, CRS.from_epsg(4326), always_xy=True)
    building_ll = [to_ll.transform(x, y) for x, y in ((-15, -5), (-15, 5), (15, 5), (15, -5), (-15, -5))]
    road_ll = [to_ll.transform(x, y) for x, y in ((-20, 0), (20, 0))]
    payload = {"elements": [
        {"type": "way", "id": 1, "tags": {"building": "yes"}, "geometry": [{"lon": lon, "lat": lat} for lon, lat in building_ll]},
        {"type": "way", "id": 2, "tags": {"highway": "residential"}, "geometry": [{"lon": lon, "lat": lat} for lon, lat in road_ll]},
    ]}
    result = OsmProvider(session=Session([Response(payload=payload)])).acquire(
        area, cache_dir=tmp_path, acquired_at_utc="2026-09-02T00:00:00+00:00"
    )
    assert len(result.buildings) == 1
    assert len(result.road_lines) == 1
    assert result.provenance.provider_id == "osm"
    assert result.provenance.attribution == "© OpenStreetMap contributors"
    assert result.provenance.terms_url == "https://www.openstreetmap.org/copyright"
    json.dumps(result.provenance.to_dict(), ensure_ascii=False)


class FakePlateau:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def acquire(self, *args, **kwargs):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class FakeOsm:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    def acquire(self, *args, **kwargs):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def test_auto_fallback_is_disclosed_and_unexpected_errors_do_not_fallback():
    osm_result = OsmVectors([], [], provenance("osm"))
    plateau = FakePlateau(RuntimeError("bug"))
    osm = FakeOsm(osm_result)
    with pytest.raises(RuntimeError):
        acquire_vectors(rectangle(), "auto", plateau=plateau, osm=osm)
    assert osm.calls == 0

    plateau = FakePlateau(ProviderParseError("catalog malformed"))
    osm = FakeOsm(osm_result)
    result = acquire_vectors(rectangle(), "auto", plateau=plateau, osm=osm)
    assert osm.calls == 1
    assert result.provenance.source_details["fallback"]["failure_category"] == "ProviderParseError"
    assert "fallback" in result.provenance.warnings[-1].lower()

    plateau = FakePlateau(ProviderUnavailableError("no city"))
    osm = FakeOsm(ProviderUnavailableError("no buildings"))
    with pytest.raises(ProviderUnavailableError, match="PLATEAU.*OSM"):
        acquire_vectors(rectangle(), "auto", plateau=plateau, osm=osm)
