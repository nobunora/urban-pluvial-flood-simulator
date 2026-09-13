# Bug Report

## Current confirmed blocking bugs

None currently known after the latest Web ChatGPT empty-leading-level repair. The new exact head still requires independent Codex validation/execution before acceptance.

## Latest confirmed Phase 4 defects and Web repairs

### 1. Multi-polygon rc3 intermediate-level failure

Codex validation of `1aeebc4037882a44a9f04898f2528a09b8d4f342` reproduced deterministic Adaptive geometry failures in hard building/road and odd 33x35 cases. The repository passed multiple exact-target polygons at different refinement depths to pinned HydroMT-SFINCS 2.0.0rc3. rc3 restarts every polygon at level zero; an earlier polygon can consume an intermediate level that a later polygon then indexes, causing `IndexError`.

Web removed polygon-driven production refinement and moved actual geometry to staged rc3 `refine_cells()` calls. Classifier polygonization remains diagnostic-only.

### 2. Empty immediately-coarser level in staged refinement

Codex then validated exact head `0e5cbefb80da104bb7d55c3aed18fe92c14cd88d` and reproduced a second deterministic failure in hard building/road, odd 33x35, and asymmetric 65x34 cases. `refine_cells()` calls rc3 `find_lower_level_neighbors()` whenever `ilev > 0`. If the whole domain has already been refined past the immediately coarser level, that level is empty; rc3 passes an empty `nm_level` into its `binary_search()` helper and raises `IndexError`.

This is not a hydraulic ambiguity: when all cells at the coarser level have disappeared globally, there can be no neighbor at that level.

Web ChatGPT repaired the integration without monkey-patching rc3:

- actual refinement remains staged and uses pinned rc3 `QuadtreeGrid.refine_cells()`;
- before each physical refinement size, if every globally coarser level has disappeared, the first populated level is promoted to level zero;
- the equivalent transform divides builder `dx/dy` by `2**leading_level`, multiplies `nmax/mmax` by the same factor, and subtracts the leading level from all cell levels;
- `n/m` indices and physical cell coordinates remain unchanged by this transform;
- internal level gaps are rejected before rc3 neighbor/UGRID finalization;
- face resolution is now derived from the rc3 Dataset's actual base `dx`, so rebased hierarchies still map exactly to the canonical `1/2/4/8/16/32 m` sizes.

The committed hard-feature, odd/padded, and asymmetric tests are the primary regression for both rc3 failures. Adaptive remains disabled at `GRID_ADAPTIVE_NOT_AVAILABLE` pending exact-head validation.

## Validated authority-less CRS writer limitation

Pinned HydroMT-SFINCS source commit `82e58ee85136cf5155c92b42bb9a397869ed8035` (`2.0.0rc3`) cannot serialize its quadtree Dataset when the true CRS has no EPSG authority because `SfincsQuadtreeGrid.write()` assigns `None` to `mesh2d_crs.attrs["epsg"]` and writes `epsg_code="EPSG:None"` before NetCDF serialization.

Codex independently reproduced that failure and demonstrated that removing only those invalid optional authority attributes preserves the authority-less AEQD through pinned xugrid/rc3 WKT round-trip. The repository compatibility writer at `1c585d6b8e5dda63d116526779d7098f97bd03f5` is validated as `validated-seam`.

## Current known risks / external dependencies

- A permitted managed-local SFINCS 2.4.0 Galibier executable was discovered by Codex at `SFINCS_2026_01_release/SFINCS_v2.4.0_Galibier_release_exe/sfincs.exe`. No download or installation was performed. Real-engine smoke is pending deterministic exact-head gates.
- The Adaptive classifier diagnostic timing was about 20.6 s on a flat 512x512 probe in the Codex environment. The specification defines no runtime acceptance threshold, so this remains a performance warning rather than a correctness failure.
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
