# Local-Inertial 2D Flood Solver — Reference Implementation

A compact reference implementation for a **Rain-on-Grid urban flood model** using:

- GSI DEM1A (~1 m grid) preprocessing
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

This repository contains **no private location data, DEM files, map files, or simulation results**.

## Repository layout

```text
.
├─ README.md
├─ CMakeLists.txt
├─ requirements.txt
├─ src/
│  └─ solver.cpp
├─ scripts/
│  ├─ gsi_dem1a_to_npz.py
│  ├─ gsi_basic_to_vectors.py
│  ├─ prepare_inputs.py
│  └─ plot_results.py
└─ docs/
   ├─ qiita_article.md
   ├─ data_download.md
   └─ references.md
```

## 1. Download source data

For Japan, GSI Fundamental Geospatial Data can provide:

- DEM1A: ~1 m elevation grid derived from airborne laser surveying
- building outlines
- road edges

See:

- https://service.gsi.go.jp/kiban/
- `docs/data_download.md`

The GSI service currently requires user registration/login for downloads.

## 2. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. Convert DEM1A GML/ZIP to a local metric grid

```bash
python scripts/gsi_dem1a_to_npz.py \
  --zip DEM1A_A.zip \
  --zip DEM1A_B.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --grid-m 1 \
  --out dem_1m.npz
```

The script:

1. reads only overlapping DEM1A GML tiles;
2. restores `gml:startPoint` omissions;
3. projects JGD2024 latitude/longitude data to a local AEQD metric CRS;
4. resamples to a regular metric grid;
5. optionally blends source seams with a cosine taper.

## 4. Extract buildings and roads

```bash
python scripts/gsi_basic_to_vectors.py \
  --zip BASIC_A.zip \
  --zip BASIC_B.zip \
  --center-lat <LATITUDE> \
  --center-lon <LONGITUDE> \
  --half-size-m 1000 \
  --out-dir vectors
```

Output:

```text
vectors/buildings.npz
vectors/basemap_vectors.npz
```

## 5. Prepare hydraulic arrays

```bash
python scripts/prepare_inputs.py \
  --dem dem_1m.npz \
  --buildings vectors/buildings.npz \
  --vectors vectors/basemap_vectors.npz \
  --out hydraulic_inputs
```

Default reference parameters:

```text
general Manning n = 0.030
road Manning n    = 0.020
road buffer       = 3 m
```

Roof rainfall is redistributed to building-perimeter ground cells. The preprocessing script prints a rainfall-mass check.

## 6. Build the solver

### CMake

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
```

### Direct GCC

```bash
g++ -O3 -march=native -fopenmp -std=c++17 src/solver.cpp -o solver
```

## 7. Run

Example: `2001 × 2001`, `dx=1 m`, `1 h`, `115 mm/h`.

```bash
OMP_NUM_THREADS=8 ./build/local_inertial_solver \
  2001 1.0 3600 115 hydraulic_inputs result
```

Direct-GCC executable:

```bash
OMP_NUM_THREADS=8 ./solver \
  2001 1.0 3600 115 hydraulic_inputs result
```

Outputs:

```text
result_h.bin      final water depth
result_hmax.bin   maximum water depth
result_qx.bin     final x-face unit-width discharge
result_qy.bin     final y-face unit-width discharge
```

## 8. Plot maximum water depth

```bash
python scripts/plot_results.py \
  --metadata hydraulic_inputs/metadata.npz \
  --prefix result \
  --out max_depth_rainbow.png
```

## Core equations

Water-surface elevation:

```math
\eta = z + h
```

Continuity:

```math
\frac{\partial h}{\partial t}
+
\frac{\partial q_x}{\partial x}
+
\frac{\partial q_y}{\partial y}
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

with de Almeida-style weighting:

```math
\bar q
=
\theta q_i
+
\frac{1-\theta}{2}
(q_{i-1}+q_{i+1})
```

Reference value:

```text
theta = 0.8
```

## Important limitations

This is a **research/reference implementation**, not an operational flood-warning product.

It does not currently model:

- sewer networks
- storm-drain inlet capacity
- infiltration
- curbs and small walls unless present in the DEM
- building-entry flooding
- river-stage boundary conditions
- full advective inertia

At 1 m resolution, DEM uncertainty and urban geometry can materially affect results. GSI describes DEM1A as approximately 1 m grid spacing with elevation standard deviation within 0.3 m; grid spacing is not the same as vertical accuracy.

Always perform:

- timestep-sensitivity checks
- mass-balance checks
- wet/dry checks
- boundary-condition checks
- comparison with established hydraulic software where possible

## Documentation

- Qiita draft: `docs/qiita_article.md`
- GSI download guide: `docs/data_download.md`
- Primary references: `docs/references.md`

## License

No license has been selected in this package. Choose an appropriate license before publishing the GitHub repository.
