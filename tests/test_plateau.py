from scripts.download_plateau_vectors import extract_citygml

CITYGML = b'''<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"
 xmlns:gml="http://www.opengis.net/gml" xmlns:bldg="http://www.opengis.net/citygml/building/2.0">
 <gml:boundedBy><gml:Envelope srsName="http://www.opengis.net/def/crs/EPSG/0/6697" srsDimension="3">
  <gml:lowerCorner>35.6800 139.7660 0</gml:lowerCorner><gml:upperCorner>35.6820 139.7680 100</gml:upperCorner>
 </gml:Envelope></gml:boundedBy>
 <core:cityObjectMember><bldg:Building>
  <bldg:lod0FootPrint><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
   <gml:posList>35.68100 139.76700 5 35.68100 139.76710 5 35.68110 139.76710 5 35.68110 139.76700 5 35.68100 139.76700 5</gml:posList>
  </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod0FootPrint>
 </bldg:Building></core:cityObjectMember>
</core:CityModel>'''


def test_extract_lod0_building():
    buildings, roads, road_polygons = extract_citygml(CITYGML, 35.68105, 139.76705, 100)
    assert len(buildings) == 1
    assert len(roads) == 0
    assert len(road_polygons) == 0
    assert buildings[0].shape[1] == 2
    assert abs(buildings[0]).max() < 100
