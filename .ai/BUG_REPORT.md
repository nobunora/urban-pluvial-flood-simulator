# Bug Report

## Current confirmed blocking bugs

- Phase 4 quadtree serialization remains blocked in pinned HydroMT-SFINCS 2.0.0rc3 when the canonical local AEQD CRS has no EPSG authority. `SfincsQuadtreeGrid.write()` assigns `crs.to_epsg()` (`None`) to `mesh2d_crs.attrs["epsg"]` and constructs `epsg_code="EPSG:None"`; the final NetCDF write rejects the `None` attribute. Adaptive remains disabled. The recommended direction is a repository-owned quadtree-only compatibility adapter that preserves `crs_wkt` and omits only invalid authority metadata, but independent runtime reproduction/round-trip evidence is still required before Web implements that private-rc3 compatibility seam.

## Phase 4 classifier findings repaired by Web; awaiting exact-head validation

The exact-SHA audit of `a17ff7b7f013ff7672e22da419a34e497d30d3d2` found three repository defects in the Adaptive foundation. Web ChatGPT has corrected them and added focused regression coverage:

1. Candidate terrain evidence omitted required local depression/ridge connectivity and flow-accumulation concentration indicators. Candidate metrics now compute those indicators, while curvature/connectivity/flow evidence remains diagnostic because the canonical specification does not define numeric gating thresholds for them.
2. Threshold identity was a static algorithm label even for caller-supplied threshold maps. Identity is now a deterministic SHA-256-derived value over the actual RMSE/max-residual configuration.
3. The `within 2 m` building/road buffer used a Chebyshev two-cell approximation and forced the entire buffer to 1 m. It now uses projected Euclidean distance between normalized 1 m source-cell footprints; feature cells remain exactly 1 m and buffer cells are constrained to at most 2 m as required by §12.2.

These repairs are not accepted until Local Codex validates the exact head named in the latest PR audit comment.

## Current known risks / non-blocking issues

- No permitted SFINCS executable is currently available on the validation host, so real-engine Phase 3/4 execution remains externally blocked. This is not a repository defect.
- Real SFINCS acceptance of an authority-less WKT-only quadtree NetCDF remains unverified until a permitted engine is available.
- External provider availability may change independently of the repository.
- OSM completeness varies by area and must remain disclosed as fallback data.
- SFINCS executable redistribution/bootstrap licensing remains unresolved for later packaging phases.
- CodebaseMemory may be stale or unavailable; exact-SHA source, specification, and deterministic tests remain authoritative.

## Previously repaired validation/tooling defects

- Phase 3 run-mutation Content-Type handling, stale exact-path regression tests, HydroMT regular-grid CRS ownership, Ruff diagnostics, and mypy third-party import handling were repaired and accepted.
- The conda validation environment now pins Windows-available `scipy=1.18.0` with Python 3.12.10.
- Frontend OpenAPI generation prefers the explicit/active compliant Python environment instead of a stale repository `.venv`.
- Phase 3 generated OpenAPI/TypeScript artifacts were canonically regenerated and synchronized.

## Reporting rule

Only confirmed defects belong in the blocking-bug section. Hypotheses must be labelled and must not be treated as confirmed until reproduced or supported by the current exact-SHA source/tests/runtime evidence.
