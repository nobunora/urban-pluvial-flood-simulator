# Local review build

The project deliberately keeps a runnable review slice available before the full v0.1 feature set is complete.

## Current review scope

The local review build is intentionally **Full 1 m only**. It exposes the user flow that needs product review now:

- latitude / longitude input;
- preset square analysis area;
- constant rainfall intensity and duration;
- Full 1 m resource estimate;
- run creation;
- run stage / state polling;
- cancellation;
- stable user-visible limitations.

Adaptive, the final result map, installer/packaging, sewer/drainage, infiltration, river/tide coupling and production release polish are not part of this review slice yet.

## Canonical environment

The local review application and validation use one canonical environment: `environment.yml`.

Do **not** use an arbitrary system Python or treat `requirements.txt` as the review-environment contract. The required environment is named:

```text
urban-pluvial-flood-phase0
```

It pins Python 3.12.10, the GIS/HydroMT stack, HydroMT-SFINCS rc3, FastAPI/Uvicorn, and the validation tools used by CI.

### Create or restore it

From the repository root, using any existing Python capable of running the standard library:

```bash
python -m scripts.bootstrap_local_review
```

The bootstrap helper auto-detects `micromamba`, `mamba`, or `conda`. If none is installed, it downloads the official portable micromamba archive into the user's local application-data directory and uses it without administrator rights or shell initialization.

The helper verifies the created environment automatically. Shell activation is optional. It prints the exact manager path and a `manager run -n ...` command that works without activation.

To bootstrap and immediately launch the review build in one operation:

```bash
python -m scripts.bootstrap_local_review --run-review -- --no-browser --port 8765
```

To pass an existing SFINCS executable at the same time:

```powershell
python -m scripts.bootstrap_local_review --run-review -- --no-browser --port 8765 --sfincs-bin "C:\path\to\sfincs.exe"
```

If you deliberately do not want the helper to download portable micromamba, add `--no-bootstrap-manager`.

The launcher refuses to proceed when Python or any canonical package version differs from `environment.yml`. This prevents accidental review under a partially installed Python 3.14/3.13/3.12 environment.

## Frontend requirement

A normal frontend rebuild requires Node.js **>=22.12** and `npm`. Node.js 24 is supported. The launcher checks the full Node version before building.

## Run it

From the repository root, with the canonical environment active:

```bash
python -m scripts.run_local_review
```

The launcher:

1. validates the canonical Python environment;
2. verifies Node.js >=22.12 when a frontend build is required;
3. runs `npm ci` when `node_modules` is absent;
4. runs `npm run build`;
5. verifies both `floodsim/static/index.html` and `floodsim/static/smoke.html` exist;
6. starts the real FastAPI application on `127.0.0.1:8000`;
7. opens the review UI.

Review URL:

```text
http://127.0.0.1:8000/
```

To use an existing permitted SFINCS 2.4.0 Galibier executable explicitly:

```bash
python -m scripts.run_local_review --sfincs-bin /path/to/sfincs
```

On Windows:

```powershell
python -m scripts.run_local_review --sfincs-bin "C:\path\to\sfincs.exe"
```

To serve an already-built frontend without invoking npm:

```bash
python -m scripts.run_local_review --skip-build
```

The build-free fallback diagnostic remains available at `/smoke.html`; `web/public/smoke.html` ensures a normal Vite build preserves that route.

## Live vector acquisition behavior

The review path is deliberately bounded so a slow provider cannot hold the UI indefinitely before SFINCS:

- PLATEAU remains the preferred vector provider;
- PLATEAU receives a 20-second total acquisition budget for a review run;
- if that budget expires or PLATEAU returns a normal provider error, acquisition falls back to OpenStreetMap;
- OSM fallback receives a 30-second budget;
- cancellation prevents starting the fallback and terminates the user-visible run immediately.

These limits are review-path reliability controls; provider provenance and fallback warnings are still recorded so the user can see which vector source was actually used.

## Real SFINCS result handling

A successful SFINCS run may leave `hmax` missing (NaN) on active cells while the regular `h` time series is finite. The review reader handles this explicitly:

- finite SFINCS `hmax` values are preserved;
- an active cell with no finite `hmax` is reconstructed from the maximum finite `h` value available for that cell;
- the reconstructed-cell count is recorded in result metadata;
- infinite `hmax`, non-finite active `h`, non-finite active terrain, inconsistent grid shapes, or materially negative depth still fail the result contract.

This prevents a completed engine run from being rejected solely because SFINCS omitted `hmax` for otherwise valid active cells, while keeping corrupt output rejection strict.

## Near-zero negative SFINCS depth

SFINCS 2.4.0 defines a default `twet_threshold` of 0.01 m for deciding whether a cell counts as flooded/wet. The local-review reader uses the same magnitude as a transparent dry-output normalization band:

- finite active depth values from -0.01 m up to (but not including) 0 m are normalized to 0 m;
- values below -0.01 m are rejected as materially negative;
- the raw `sfincs_map.nc` is never changed;
- normalized metadata records `negative_depth_clipped_values`, `negative_max_depth_clipped_cells`, and `min_raw_active_depth_m`.

This is intentionally separate from SFINCS `huthresh` (the flow-depth limiter) and keeps the original engine output available for audit.

## Diagnosing a failed BUILDING_GRID stage

Unexpected worker failures are persisted for review instead of being reduced to only `INTERNAL_RUN_FAILED`.

The failed run's `manifest.json` records:

- `failing_stage`;
- `failure_code`;
- `failure_exception_type`;
- `failure_message`;
- `failure_diagnostic_file`.

The diagnostic JSON under `logs/` includes the traceback plus elevation/vector input summaries.

To isolate BUILDING_GRID from an existing run without redoing vector acquisition or SFINCS, run:

```bash
python -m scripts.diagnose_grid_run <run-id>
```

For example:

```text
python -m scripts.diagnose_grid_run f2dc662c-f445-4f6d-af75-223bb8c2f16c
```

The command reuses the persisted run config and `source_refs`, uses the normal elevation cache path, writes `logs/grid_replay_diagnostic.json`, and reports building/road counts plus grid/roof-allocation diagnostics.

## Normalized vector provider contract

The Full 1 m grid receives one provider-neutral vector structure:

- `buildings`;
- `road_lines`;
- `road_polygons`;
- provenance.

PLATEAU can supply road polygons. The OSM fallback currently supplies road lines only, so its `road_polygons` collection is explicitly empty. This avoids provider-specific branching in grid construction and does not invent polygon geometry.

Persisted manifest paths such as `logs/failure_diagnostic.json` always use forward slashes, including on Windows, so run artifacts remain portable across tools and platforms.

## Working-tree safety

Before user review, run:

```bash
git status --short
```

Do not discard user changes automatically. In particular, a locally modified `floodsim/static/index.html` can cause the browser to display UI that does not match the PR head. Use a clean worktree or deliberately preserve/reconcile the local change before reviewing the PR build.

## What counts as reviewable

A review build is acceptable before the final product when all of the following are true:

1. canonical environment preflight passes;
2. deterministic Python/TypeScript/frontend CI gates pass;
3. `/` loads the Full 1 m review UI after a normal frontend build;
4. `/smoke.html` remains HTTP 200 after that build;
5. backend health is visible;
6. ±250 m reports 250,000 Full-1m-equivalent cells;
7. a valid Full 1 m run returns a run ID and visible stage transitions;
8. cancellation works while a run is active;
9. Adaptive cannot be submitted;
10. if SFINCS or an external provider is unavailable, the UI reaches and displays the real failure stage instead of faking completion;
11. with an available SFINCS executable and providers, a tiny Full 1 m run is exercised end-to-end before more Adaptive work is prioritized.

This review gate is intentionally earlier than the final v0.1 acceptance gate. Product-direction feedback from this build should take priority over polishing incomplete Adaptive internals.
