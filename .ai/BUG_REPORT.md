# Bug Report

## Current confirmed blocking bugs

- Phase 3 generated API artifacts are stale: `web/openapi.json` and `web/src/api/generated.ts` do not yet contain the Phase 3 estimate/run/cancel/events/result-metadata routes. They must be regenerated from the current FastAPI app with the repository's pinned validation environment and `openapi-typescript`, then committed by Web ChatGPT before Phase 3 can be validated.

## Current known risks / non-blocking issues

- External provider availability may change independently of the repository.
- OSM completeness varies by area and must remain disclosed as fallback data.
- SFINCS executable redistribution/bootstrap licensing remains unresolved for later packaging phases.
- A real Phase 3 SFINCS smoke remains blocked when no permitted `SFINCS_BIN` or managed-local engine is present; this is an external validation prerequisite, not a source defect.
- CodebaseMemory has intermittently returned `Transport closed`; source code and deterministic repository tests remain authoritative.

## Recently repaired validation/tooling defects

- The conda validation environment previously pinned `scipy=1.18.1`, which was not available from conda-forge main for the Windows validation host. It now pins `scipy=1.18.0`, for which a Python 3.12 win-64 build is available.
- `web/scripts/api-types.mjs` previously preferred a stale repository `.venv` even when a compliant conda/virtual environment was active. It now prefers an explicit `FLOODSIM_PYTHON`/`PYTHON`, then the active conda or virtual environment, before falling back to the repository `.venv` and PATH.

## Reporting rule

Only confirmed defects belong in the blocking-bug section. Hypotheses must be clearly labelled and must not be treated as confirmed until reproduced or supported by the current diff/source/tests.
