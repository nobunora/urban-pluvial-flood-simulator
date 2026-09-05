# Bug Report

## Current confirmed blocking bugs

None.

## Current known risks / non-blocking issues

- External provider availability may change independently of the repository.
- OSM completeness varies by area and must remain disclosed as fallback data.
- SFINCS executable redistribution/bootstrap licensing remains unresolved for later packaging phases.
- A real Phase 3 SFINCS smoke remains blocked when no permitted `SFINCS_BIN` or managed-local engine is present; this is an external validation prerequisite, not a source defect.
- CodebaseMemory has intermittently returned `Transport closed`; source code and deterministic repository tests remain authoritative.

## Recently repaired validation/tooling defects

- The conda validation environment previously pinned `scipy=1.18.1`, which was not available from conda-forge main for the Windows validation host. It now pins `scipy=1.18.0`, for which a Python 3.12 win-64 build is available.
- `web/scripts/api-types.mjs` previously preferred a stale repository `.venv` even when a compliant conda/virtual environment was active. It now prefers an explicit `FLOODSIM_PYTHON`/`PYTHON`, then the active conda or virtual environment, before falling back to the repository `.venv` and PATH.
- Phase 3 generated API artifacts were stale. Web ChatGPT regenerated them using Python 3.12.10, the repository runtime requirements, Node 22, `npm ci`, `npm run api:generate`, and `npm run api:check`. The committed artifacts now contain the Phase 3 estimate/run/cancel/events/result-metadata routes. Generated SHA-256 values at regeneration were `b9036afa1e1b864e60f4aeb6b2bbb8883c7fc28308fe8e2eb873cdcb970adb79` for `web/openapi.json` and `48b3728d9d8e664f46a5a716c6118732315801707526f42cf0ef8362ed9d0e94` for `web/src/api/generated.ts`.

## Reporting rule

Only confirmed defects belong in the blocking-bug section. Hypotheses must be clearly labelled and must not be treated as confirmed until reproduced or supported by the current diff/source/tests.
