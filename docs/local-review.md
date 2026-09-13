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

## Run it

Prerequisites:

- the repository Python environment with `requirements.txt` installed;
- Node.js 22 with `npm` available when rebuilding the frontend;
- optionally, an existing permitted SFINCS 2.4.0 Galibier executable for real hydraulic execution.

From the repository root:

```bash
python -m scripts.run_local_review
```

The launcher rebuilds the frontend when needed, serves the real FastAPI application on `127.0.0.1:8000`, and opens the review UI at:

```text
http://127.0.0.1:8000/
```

To use an existing permitted SFINCS executable explicitly:

```bash
python -m scripts.run_local_review --sfincs-bin /path/to/sfincs
```

To serve an already-built frontend without invoking npm:

```bash
python -m scripts.run_local_review --skip-build
```

The build-free fallback diagnostic remains available at `/smoke.html`; `web/public/smoke.html` ensures a normal Vite build preserves that route.

## What counts as reviewable

A review build is acceptable before the final product when all of the following are true:

1. `/` loads the Full 1 m review UI after a normal frontend build.
2. Backend health is visible.
3. ±250 m reports 250,000 Full-1m-equivalent cells.
4. A valid Full 1 m run returns a run ID and visible stage transitions.
5. Cancellation works while a run is active.
6. Adaptive cannot be submitted.
7. If SFINCS or an external provider is unavailable, the UI reaches and displays the real failure stage instead of faking completion.
8. With an available SFINCS executable and providers, a tiny Full 1 m run is exercised end-to-end before more Adaptive work is prioritized.

This review gate is intentionally earlier than the final v0.1 acceptance gate. Product-direction feedback from this build should take priority over polishing incomplete Adaptive internals.
