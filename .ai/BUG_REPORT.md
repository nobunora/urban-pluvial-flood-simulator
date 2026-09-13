# Bug Report

## Current confirmed blocking bugs

None currently known after the latest Web ChatGPT staged-refinement repair. The new exact head still requires independent Codex validation/execution before acceptance.

## Latest confirmed Phase 4 defect and Web repair

Codex validation of `1aeebc4037882a44a9f04898f2528a09b8d4f342` reproduced a deterministic Adaptive geometry failure in two committed tests:

- hard building/road actual-quadtree mapping;
- odd 33x35 padded-domain mapping.

Both failed inside pinned HydroMT-SFINCS 2.0.0rc3 `QuadtreeGrid.refine_in_polygon()` because classifier-derived polygons with different refinement levels are processed independently and each polygon restarts at level zero. Earlier polygons can consume every cell at an intermediate level, after which a later polygon indexes an empty/nonexistent level and raises `IndexError`.

Web ChatGPT repaired this integration path by:

- keeping classifier polygonization only as an inspectable diagnostic artifact;
- building the actual rc3 quadtree with the pinned rc3 `QuadtreeGrid` engine;
- refining existing rc3 cells explicitly and monotonically by level `32 -> 16 -> 8 -> 4 -> 2 -> 1 m` using `refine_cells()`;
- selecting each parent for refinement only when its overlapping Full-1 m source block contains a validated classifier target finer than that parent;
- preserving rc3 neighbour/topology finalization, authority-less AEQD replacement, mask/Manning mapping and rain-mass conservation guards;
- adding asymmetric-domain and exact source-coverage regression checks.

This is a substantive Web-owned repair and is pending exact-head Codex execution. Adaptive remains disabled at `GRID_ADAPTIVE_NOT_AVAILABLE`.

## Validated authority-less CRS writer limitation

Pinned HydroMT-SFINCS source commit `82e58ee85136cf5155c92b42bb9a397869ed8035` (`2.0.0rc3`) cannot serialize its quadtree Dataset when the true CRS has no EPSG authority because `SfincsQuadtreeGrid.write()` assigns `None` to `mesh2d_crs.attrs["epsg"]` and writes `epsg_code="EPSG:None"` before NetCDF serialization.

Codex independently reproduced that failure and demonstrated that removing only those invalid optional authority attributes preserves the authority-less AEQD through pinned xugrid/rc3 WKT round-trip. The repository compatibility writer at `1c585d6b8e5dda63d116526779d7098f97bd03f5` is validated as `validated-seam`.

## Current known risks / external dependencies

- A permitted managed-local SFINCS 2.4.0 Galibier executable was discovered by Codex at `SFINCS_2026_01_release/SFINCS_v2.4.0_Galibier_release_exe/sfincs.exe`. Real-engine execution is therefore no longer blocked by executable absence, but the newly repaired exact head has not yet been exercised against it.
- The Adaptive classifier diagnostic timing was about 20.6 s on a flat 512x512 probe in the Codex environment. The specification defines no runtime acceptance threshold, so this is a performance warning rather than a correctness failure.
- External provider availability may change independently of the repository.
- OSM completeness varies by area and must remain disclosed as fallback data.
- SFINCS executable redistribution/bootstrap licensing remains unresolved for later packaging phases even though a validation-host executable exists.
- CodebaseMemory may be stale or unavailable; exact-SHA source, specification, and deterministic tests remain authoritative.

## Previously repaired validation/tooling defects

- Phase 3 run-mutation Content-Type handling, stale exact-path regression tests, HydroMT regular-grid CRS ownership, Ruff diagnostics, and mypy third-party import handling were repaired and accepted.
- Phase 4 classifier evidence, threshold identity, and exact projected-metric 2 m feature-buffer semantics were repaired and passed independent Codex audit at `1d189e358bef2cd0363213feff61d7ed5ef1e813`.
- The quadtree authority-less CRS writer seam was independently validated at `1c585d6b8e5dda63d116526779d7098f97bd03f5`.
- The conda validation environment pins Windows-available `scipy=1.18.0` with Python 3.12.10.
- Frontend OpenAPI generation prefers the explicit/active compliant Python environment instead of a stale repository `.venv`.
- Phase 3 generated OpenAPI/TypeScript artifacts were canonically regenerated and synchronized.

## Reporting rule

Only confirmed defects belong in the blocking-bug section. Hypotheses must be labelled and must not be treated as confirmed until reproduced or supported by current exact-SHA source/tests/runtime evidence.
