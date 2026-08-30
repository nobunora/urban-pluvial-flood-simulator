# Automatic terrain and urban-geometry acquisition

## Recommended workflow

The normal workflow no longer requires manually downloading GSI ZIP files.

```bash
python -m scripts.prepare_area \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --grid-m 1 \
  --out-dir area
```

This automatically acquires elevation and urban geometry, caches downloaded source files, and creates the binary arrays consumed by `src/solver.cpp`.

## Elevation: public GSI elevation tiles

GSI publishes PNG elevation tiles at:

```text
https://cyberjapandata.gsi.go.jp/xyz/dem1a_png/{z}/{x}/{y}.png
https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png
https://cyberjapandata.gsi.go.jp/xyz/dem5b_png/{z}/{x}/{y}.png
https://cyberjapandata.gsi.go.jp/xyz/dem5c_png/{z}/{x}/{y}.png
https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png
```

Official tile list:

https://maps.gsi.go.jp/development/ichiran.html

The automatic downloader uses the highest native published zoom for each source and fills only missing cells from lower-resolution models.

Priority:

```text
DEM1A -> DEM5A -> DEM5B -> DEM5C -> DEM10B
```

DEM1A is approximately a 1 m elevation grid derived from airborne laser surveying where available. GSI's stated vertical accuracy is not 1 m simply because the horizontal grid is approximately 1 m.

https://maps.gsi.go.jp/development/hyokochi.html

### PNG elevation decoding

GSI stores an elevation code in RGB:

```text
x = 2^16 R + 2^8 G + B
```

The decoder handles positive values, signed negative values, and the NoData sentinel according to the official tile specification:

https://maps.gsi.go.jp/development/demtile.html

### Why keep the manual GML converter?

Live elevation tiles are convenient and automatic, but their content can be updated. For a paper, benchmark, or long-term reproducible run, it may be preferable to archive a specific Fundamental Geospatial Data GML release and use `gsi_dem1a_to_npz.py`.

## Buildings and roads: PLATEAU first

Project PLATEAU provides an official distribution API:

https://docs.plateauview.mlit.go.jp/api/rest/

The downloader constructs a bounding-box query such as:

```text
GET https://api.plateauview.mlit.go.jp/datacatalog/citygml/r:<lon1>,<lat1>,<lon2>,<lat2>?types=bldg,tran
```

The API returns CityGML file URLs grouped by feature type. Only the intersecting building (`bldg`) and transportation (`tran`) files are downloaded.

PLATEAU CityGML documentation:

https://docs.plateauview.mlit.go.jp/datasets/citygml/

### Coordinate handling

PLATEAU commonly uses EPSG:6697. Its CityGML coordinate tuples are written in axis order:

```text
latitude longitude elevation
```

The downloader ignores the vertical component for footprint generation and transforms the horizontal coordinates to a local AEQD metric CRS centred on the requested simulation area.

Official explanation:

https://www.mlit.go.jp/plateau/learning/tpc03-4/

### Footprint extraction priority

For buildings:

1. `lod0FootPrint`
1. `lod0RoofEdge`
1. `GroundSurface`
1. remaining polygon geometry as a final conservative fallback

For roads, polygon surfaces are preferred. When only network lines are available, the hydraulic rasterizer buffers them by `--road-half-width`.

## PLATEAU fallback

The PLATEAU API is documented as trial/experimental and PLATEAU coverage is not universal. The default:

```text
--vector-provider auto
```

therefore performs:

```text
PLATEAU
   ↓ unavailable / no usable building footprint
OpenStreetMap Overpass
```

OSM is a fallback, not equivalent-quality authoritative data. Completeness varies by region and `manifest.json` records when it was used.

To prohibit fallback:

```bash
--vector-provider plateau
```

## Cache and reproducibility

Downloaded GSI tiles, PLATEAU CityGML files, and OSM responses are cached under the selected output directory. A second identical preprocessing run should reuse the cache and produce the same raster inputs as long as the cached source files are retained.

`manifest.json` records:

- centre and area size
- DEM source-cell counts
- nearest-filled cell count
- vector provider
- PLATEAU city/year/spec metadata where available
- hydraulic raster fractions and rain-weight mass check

For reproducible publication work, archive both the manifest and cache/source data used for the run.

## Attribution and terms

Source data are not relicensed by this repository. Users are responsible for complying with current source-provider terms and attribution requirements.

- GSI tiles: https://maps.gsi.go.jp/development/ichiran.html
- PLATEAU: https://www.mlit.go.jp/plateau/open-data/
- OpenStreetMap: https://www.openstreetmap.org/copyright

## Manual Fundamental Geospatial Data path

The old path remains useful when a version-pinned GML/ZIP is required.

DEM:

```bash
python scripts/gsi_dem1a_to_npz.py \
  --zip FG-GML-XXXXXX-DEM1A-YYYYMMDD.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --grid-m 1 \
  --out dem_1m.npz
```

Buildings/roads:

```bash
python scripts/gsi_basic_to_vectors.py \
  --zip BASIC_A.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --out-dir vectors
```

Then:

```bash
python scripts/prepare_inputs.py \
  --dem dem_1m.npz \
  --buildings vectors/buildings.npz \
  --vectors vectors/basemap_vectors.npz \
  --out hydraulic_inputs
```
