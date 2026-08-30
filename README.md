# Urban Pluvial Flood Simulator

A compact **Rain-on-Grid urban pluvial flood simulator** based on the 2D Local-Inertial shallow-water approximation.

The preprocessing pipeline can now build a simulation area from only a latitude/longitude and size:

- elevation: **GSI public elevation tiles**, preferring DEM1A (~1 m)
- buildings/roads: **Project PLATEAU CityGML** first
- vector fallback: **OpenStreetMap / Overpass** when PLATEAU is unavailable
- hydraulic rasterization: building no-flow cells, lower road roughness, roof-rainfall redistribution

The repository contains no private location data or bundled source datasets.

## Quick start: fully automatic input preparation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Prepare a 2 km x 2 km area at 1 m grid spacing:

```bash
python -m scripts.prepare_area \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --grid-m 1 \
  --out-dir area
```

This performs:

```text
latitude / longitude
        ↓
GSI DEM1A elevation tiles
        ↓  NoData fallback
DEM5A -> DEM5B -> DEM5C -> DEM10B
        ↓
local metric DEM
        ↓
PLATEAU CityGML range query (bldg, tran)
        ↓
LOD0 building footprints + road geometry
        ↓  if PLATEAU unavailable
OpenStreetMap fallback
        ↓
raster hydraulic inputs
```

Outputs:

```text
area/
├─ dem_1m.npz
├─ dem_1m.json
├─ manifest.json
├─ cache/
├─ vectors/
│  ├─ buildings.npz
│  ├─ basemap_vectors.npz
│  └─ vectors_manifest.json
└─ hydraulic_inputs/
   ├─ z.bin
   ├─ manning.bin
   ├─ rain_weight.bin
   ├─ building.bin
   ├─ road.bin
   └─ metadata.npz
```

`manifest.json` records the providers actually used. Do not assume every area has DEM1A or PLATEAU coverage.

### Vector provider selection

Default `--vector-provider auto` tries PLATEAU first and uses OSM only if PLATEAU cannot provide usable building data.

```bash
python -m scripts.prepare_area ... --vector-provider plateau
python -m scripts.prepare_area ... --vector-provider osm
```

## GSI elevation acquisition

The automatic downloader uses the public GSI PNG elevation tile service, so a GSI Fundamental Geospatial Data account is **not required** for the normal automatic workflow.

Provider priority:

1. DEM1A (`dem1a_png`, zoom 17)
1. DEM5A (`dem5a_png`, zoom 15)
1. DEM5B (`dem5b_png`, zoom 15)
1. DEM5C (`dem5c_png`, zoom 15)
1. DEM10B (`dem_png`, zoom 14)

Tiles are decoded from GSI's signed 24-bit RGB elevation representation, mosaicked in Web Mercator, and reprojected to a local azimuthal-equidistant metric grid.

- https://maps.gsi.go.jp/development/ichiran.html
- https://maps.gsi.go.jp/development/demtile.html

## PLATEAU building/road acquisition

The automatic vector downloader queries the official PLATEAU distribution API by bounding box with `types=bldg,tran` and downloads only intersecting CityGML files.

- API endpoint: `https://api.plateauview.mlit.go.jp`
- docs: https://docs.plateauview.mlit.go.jp/datasets/citygml/

PLATEAU CityGML commonly uses EPSG:6697 and stores coordinate tuples as `latitude longitude elevation`. Buildings prefer `lod0FootPrint`, then `lod0RoofEdge`, then `GroundSurface`. Roads prefer surface polygons when available and fall back to line geometry.

The PLATEAU API is currently documented as a trial service, which is why `auto` mode has an OSM fallback.

## Legacy/manual GSI GML workflow

The original converters remain available when a version-pinned GML dataset is required:

```bash
python scripts/gsi_dem1a_to_npz.py \
  --zip DEM1A_A.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --grid-m 1 \
  --out dem_1m.npz
```

```bash
python scripts/gsi_basic_to_vectors.py \
  --zip BASIC_A.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --out-dir vectors
```

See `docs/data_download.md` for automatic vs version-pinned acquisition.

## Build the solver

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

or:

```bash
g++ -O3 -march=native -fopenmp -std=c++17 src/solver.cpp -o solver
```

## Run

Example: `2001 x 2001`, `dx=1 m`, `1 h`, `115 mm/h`:

```bash
OMP_NUM_THREADS=8 ./build/local_inertial_solver \
  2001 1.0 3600 115 area/hydraulic_inputs result
```

Outputs:

```text
result_h.bin      final water depth
result_hmax.bin   maximum water depth
result_qx.bin     final x-face unit-width discharge
result_qy.bin     final y-face unit-width discharge
```

## Plot maximum depth

```bash
python scripts/plot_results.py \
  --metadata area/hydraulic_inputs/metadata.npz \
  --prefix result \
  --out max_depth_rainbow.png
```

## Hydraulic model

The reference implementation includes:

- 2D Local-Inertial approximation
- adaptive global CFL
- de Almeida-style discharge stabilization
- semi-implicit Manning friction
- wet/dry handling
- positivity-preserving donor-cell limiter
- buildings as no-flow cells
- lower Manning roughness on roads
- roof-rainfall redistribution with rainfall-mass conservation
- OpenMP parallelization

Water-surface elevation:

```math
\eta = z + h
```

Continuity:

```math
\frac{\partial h}{\partial t}
+\frac{\partial q_x}{\partial x}
+\frac{\partial q_y}{\partial y}
=R
```

Reference Local-Inertial face update:

```math
q^{n+1}
=
\frac{
\bar q - g h_f \Delta t\, \partial\eta/\partial x
}{
1 + g\Delta t n^2 |\bar q|/h_f^{7/3}
}
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Network integration and solver smoke-test instructions for Codex are in `CODEX_TEST_PLAN.md`.

## Important limitations

This is a research/reference implementation, not an operational flood-warning product. It does not currently model sewer networks, storm-drain inlet capacity, infiltration, detailed curbs/walls, building-entry flooding, river-stage boundaries, or full advective inertia.

At 1 m resolution, DEM uncertainty and urban geometry can materially affect results. Grid spacing is not vertical accuracy.

## Documentation

- data acquisition: `docs/data_download.md`
- primary references: `docs/references.md`
- Codex validation: `CODEX_TEST_PLAN.md`

## License

No license has been selected yet. Choose an appropriate license before broad redistribution.
