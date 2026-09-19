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

The bootstrap helper auto-detects `micromamba`, `mamba`, or `conda`. If none is installed, install a conda-compatible environment manager first.

Then activate the environment, for example:

```bash
conda activate urban-pluvial-flood-phase0
```

If shell activation is unavailable, use `conda run` instead:

```bash
conda run -n urban-pluvial-flood-phase0 python -m scripts.run_local_review --check-env
```

Validate the active interpreter before review:

```bash
python -m scripts.run_local_review --check-env
```

The launcher refuses to proceed when Python or any canonical package version differs from `environment.yml`. This prevents accidental review under a partially installed Python 3.14/3.13/3.12 environment.

## Frontend requirement

A normal frontend rebuild requires Node.js **22** and `npm`. The launcher checks the Node major version before building.

## Run it

From the repository root, with the canonical environment active:

```bash
python -m scripts.run_local_review
```

The launcher:

1. validates the canonical Python environment;
2. verifies Node.js 22 when a frontend build is required;
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
