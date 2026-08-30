# Codex validation plan for automatic GSI + PLATEAU inputs

This branch intentionally adds network-facing preprocessing. Please validate it in a Codex environment before merge.

## Use CodebaseMemory first

If the CodebaseMemory MCP is available, index/query this branch before editing. In particular, map the data contract among:

- `scripts/prepare_area.py`
- `scripts/download_gsi_dem.py`
- `scripts/download_plateau_vectors.py`
- `scripts/download_osm_vectors.py`
- `scripts/prepare_inputs.py`
- `src/solver.cpp`

Use CodebaseMemory to detect assumptions about row order, dtype, face orientation, filenames, and square-grid requirements that the new preprocessing may have missed. If CodebaseMemory finds a conflict, fix the branch rather than working around it in the test.

## 1. Static / unit tests

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Expected:

- all tests pass;
- GSI PNG decoding returns positive, negative and NoData values correctly;
- PLATEAU EPSG:6697 `lat lon z` geometry becomes local metric x/y;
- roof-rainfall redistribution conserves rainfall mass.

Also run:

```bash
python -m compileall scripts tests
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

Expected: no Python syntax errors and the C++ solver builds successfully.

## 2. Live GSI integration test

Use a public, non-sensitive location in central Tokyo:

```bash
python -m scripts.download_gsi_dem \
  --center-lat 35.6812 \
  --center-lon 139.7671 \
  --half-size-m 100 \
  --grid-m 1 \
  --out /tmp/gsi_dem.npz \
  --cache-dir /tmp/upfs-cache
```

Inspect `/tmp/gsi_dem.json` and the NPZ.

Expected:

- shape is `201 x 201`;
- all final `z` values are finite;
- `source` contains at least one nonzero provider id;
- elevation values are plausible for central Tokyo (no thousands-of-metres decoding error);
- provider counts sum to the number of cells before any reported nearest fill;
- a second identical run uses cached tiles and produces numerically identical `z`.

If DEM1A is unavailable at this exact point when tested, fallback DEM5/10 is acceptable, but confirm the order is `DEM1A -> DEM5A -> DEM5B -> DEM5C -> DEM10B`.

## 3. Live PLATEAU integration test

```bash
python -m scripts.download_plateau_vectors \
  --center-lat 35.6812 \
  --center-lon 139.7671 \
  --half-size-m 250 \
  --out-dir /tmp/plateau-vectors \
  --cache-dir /tmp/upfs-cache
```

Expected:

- `vectors_manifest.json` says provider `PLATEAU`;
- at least one `bldg` CityGML file is downloaded;
- `buildings.npz` contains non-empty, finite local x/y polygons;
- most returned building vertices lie within roughly the requested window plus clipping margin;
- `basemap_vectors.npz` contains `roads` and `road_polygons` keys even if one is empty;
- no latitude/longitude axis swap (a swapped parser normally produces coordinates far outside the 250 m window).

## 4. End-to-end automatic preparation

```bash
python -m scripts.prepare_area \
  --center-lat 35.6812 \
  --center-lon 139.7671 \
  --half-size-m 100 \
  --grid-m 1 \
  --out-dir /tmp/upfs-area
```

Expected files:

```text
/tmp/upfs-area/dem_1m.npz
/tmp/upfs-area/vectors/buildings.npz
/tmp/upfs-area/vectors/basemap_vectors.npz
/tmp/upfs-area/hydraulic_inputs/z.bin
/tmp/upfs-area/hydraulic_inputs/manning.bin
/tmp/upfs-area/hydraulic_inputs/rain_weight.bin
/tmp/upfs-area/hydraulic_inputs/building.bin
/tmp/upfs-area/hydraulic_inputs/road.bin
/tmp/upfs-area/hydraulic_inputs/metadata.npz
/tmp/upfs-area/manifest.json
```

Expected invariants:

- `N == 201`, `dx == 1`;
- `0 < building_fraction < 0.9` for the selected urban test area;
- `rain_weight.sum()` equals `N*N` within floating-point tolerance;
- building cells have zero roof-rain weight;
- Manning values are only the configured ground/road values;
- the manifest records GSI attribution and the actual vector provider.

## 5. Solver smoke test

Run a short simulation rather than a full production hour:

```bash
OMP_NUM_THREADS=4 ./build/local_inertial_solver \
  201 1.0 60 50 /tmp/upfs-area/hydraulic_inputs /tmp/upfs-smoke
```

Then inspect all four binary outputs as `float32`.

Expected:

- exact expected array sizes from `src/solver.cpp`;
- no NaN/Inf;
- all water depths are non-negative;
- `hmax >= h` cell-by-cell;
- blocked building cells remain dry;
- maximum depth is finite and physically plausible for only 60 s of 50 mm/h rainfall.

## 6. Fallback behavior

Mock or temporarily force the PLATEAU request to fail and exercise `--vector-provider auto`.

Expected:

- the pipeline tries PLATEAU first;
- it then uses OSM Overpass;
- `manifest.json` records `OpenStreetMap` and includes the PLATEAU failure message;
- `--vector-provider plateau` does not silently fall back and instead returns a clear error.

## 7. Review points before merge

Please specifically review:

- GSI PNG elevation decoding around the signed 24-bit threshold and NoData code;
- Web Mercator tile mosaic geotransform and north/south array flip;
- PLATEAU CityGML 2.0/3.0 namespace tolerance;
- LOD0 footprint vs roof-edge fallback behavior;
- road surface rasterization versus buffered road centerlines;
- cache uniqueness for CityGML URLs;
- HTTP timeout/retry behavior and polite request rates;
- attribution text and current GSI/PLATEAU terms.

Do not accept a test merely because it runs: verify spatial orientation visually or numerically with a few known points.
