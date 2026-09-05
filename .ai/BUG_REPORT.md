# Bug Report

## Current confirmed blocking bugs

None currently known after the latest Web ChatGPT fixes. The fixes are **not accepted yet**; Local Codex must audit and execute them against the exact head named in the latest PR validation comment.

## Current known risks / non-blocking issues

- External provider availability may change independently of the repository.
- OSM completeness varies by area and must remain disclosed as fallback data.
- SFINCS executable redistribution/bootstrap licensing remains unresolved for later packaging phases.
- A real Phase 3 SFINCS smoke remains blocked when no permitted `SFINCS_BIN` or managed-local engine is present; this is an external validation prerequisite, not a source defect.
- CodebaseMemory has intermittently returned `Transport closed`; source code and deterministic repository tests remain authoritative.

## Recently repaired / awaiting exact-head revalidation

The Local Codex acceptance pass for `0c114e4c462bada39a9aaf89bb0448c119d9a29f` confirmed the following repository defects. Web ChatGPT owns and has applied the corrections; Local Codex must verify them without editing:

- Run-mutation `Content-Type` checking occurred after FastAPI body parsing, so `text/plain` could return 400 before the intended 415 contract. The runs router now uses a custom `APIRoute` boundary that rejects non-JSON POST requests before body parsing.
- Two Phase 1/2 regression tests incorrectly required the OpenAPI path set to equal the Phase 2 path set exactly, rejecting legitimate Phase 3 routes. They now require the validated Phase 2 paths as a subset.
- HydroMT-SFINCS rc3 kept the temporary initialization EPSG in `model.grid.epsg` even after `config.epsg` was cleared, causing `model.grid.crs` to resolve to EPSG:4326 instead of the normalized local AEQD Dataset CRS. The builder now synchronizes Dataset CRS, `grid.epsg=None`, `config.epsg=None`, and `crsgeo` before the CRS assertion and model write.
- The rc3 package lacks a `py.typed` marker; the targeted import is now explicitly marked `# type: ignore[import-untyped]` rather than disabling mypy more broadly.
- The seven reported Ruff diagnostics were addressed with semantic-preserving simplifications, and the intentional broad exception at the top-level run-worker boundary is locally documented and suppressed only at that boundary.

## Previously repaired validation/tooling defects

- The conda validation environment previously pinned `scipy=1.18.1`, which was not available from conda-forge main for the Windows validation host. It now pins `scipy=1.18.0`, for which a Python 3.12 win-64 build is available.
- `web/scripts/api-types.mjs` previously preferred a stale repository `.venv` even when a compliant conda/virtual environment was active. It now prefers an explicit `FLOODSIM_PYTHON`/`PYTHON`, then the active conda or virtual environment, before falling back to the repository `.venv` and PATH.
- Phase 3 generated API artifacts were stale. Web ChatGPT regenerated them using Python 3.12.10, the repository runtime requirements, Node 22, `npm ci`, `npm run api:generate`, and `npm run api:check`. The committed artifacts contain the Phase 3 estimate/run/cancel/events/result-metadata routes. Generated SHA-256 values at regeneration were `b9036afa1e1b864e60f4aeb6b2bbb8883c7fc28308fe8e2eb873cdcb970adb79` for `web/openapi.json` and `48b3728d9d8e664f46a5a716c6118732315801707526f42cf0ef8362ed9d0e94` for `web/src/api/generated.ts`.

## Reporting rule

Only confirmed defects belong in the blocking-bug section. Hypotheses must be clearly labelled and must not be treated as confirmed until reproduced or supported by the current diff/source/tests.
