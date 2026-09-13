# Bug Report

## Current confirmed blocking bugs

None currently known after the latest Web ChatGPT repairs. The new exact head still requires independent Codex validation/execution before acceptance.

## Phase 4 repairs awaiting exact-head validation

The Local Codex validation of `1d189e358bef2cd0363213feff61d7ed5ef1e813` confirmed that the repaired Adaptive classifier passes its specification audit and that the authority-less quadtree CRS failure is an upstream HydroMT-SFINCS 2.0.0rc3 writer limitation. The only repository failure in that pass was two Ruff `RUF046` diagnostics.

Web ChatGPT has now:

- removed the two redundant `int(math.ceil(...))` conversions reported by Ruff;
- added `floodsim/sfincs/quadtree_writer.py`, a quadtree-only compatibility writer for the pinned rc3 authority-less CRS case;
- kept authority-backed CRS on the ordinary rc3 writer path;
- for authority-less local AEQD, preserved exact `crs_wkt`, CF/UGRID metadata, topology, conventions, coordinate units/grid mapping, and rc3 integer casting while omitting only invalid optional `epsg=None` / `epsg_code="EPSG:None"` authority metadata;
- added real pinned-rc3 round-trip coverage in `tests/test_phase4_quadtree_writer.py`.

This compatibility seam is not accepted until Codex tests the exact new head. Adaptive remains disabled at `GRID_ADAPTIVE_NOT_AVAILABLE`.

## Confirmed upstream limitation

Pinned HydroMT-SFINCS source commit `82e58ee85136cf5155c92b42bb9a397869ed8035` (`2.0.0rc3`) cannot serialize its quadtree Dataset when the true CRS has no EPSG authority because `SfincsQuadtreeGrid.write()` assigns `None` to `mesh2d_crs.attrs["epsg"]` and writes `epsg_code="EPSG:None"` before NetCDF serialization.

Codex independently reproduced that failure and demonstrated in a disposable runtime probe that removing only those invalid optional authority attributes preserves the authority-less AEQD through pinned xugrid/rc3 WKT round-trip. Compatibility decision: `SEAM_SUPPORTED`.

## Current known risks / external blockers

- No permitted SFINCS executable is currently available on the validation host, so real-engine Phase 3/4 execution remains externally blocked. This is not a repository defect.
- Real SFINCS acceptance of the WKT-only quadtree NetCDF remains unverified until a permitted engine is available.
- The Adaptive classifier diagnostic timing was about 20.6 s on a flat 512x512 probe in the Codex environment. The specification defines no runtime acceptance threshold, so this is a performance warning rather than a current correctness failure.
- External provider availability may change independently of the repository.
- OSM completeness varies by area and must remain disclosed as fallback data.
- SFINCS executable redistribution/bootstrap licensing remains unresolved for later packaging phases.
- CodebaseMemory may be stale or unavailable; exact-SHA source, specification, and deterministic tests remain authoritative.

## Previously repaired validation/tooling defects

- Phase 3 run-mutation Content-Type handling, stale exact-path regression tests, HydroMT regular-grid CRS ownership, Ruff diagnostics, and mypy third-party import handling were repaired and accepted.
- Phase 4 classifier evidence, threshold identity, and exact projected-metric 2 m feature-buffer semantics were repaired and passed independent Codex audit at `1d189e358bef2cd0363213feff61d7ed5ef1e813`.
- The conda validation environment now pins Windows-available `scipy=1.18.0` with Python 3.12.10.
- Frontend OpenAPI generation prefers the explicit/active compliant Python environment instead of a stale repository `.venv`.
- Phase 3 generated OpenAPI/TypeScript artifacts were canonically regenerated and synchronized.

## Reporting rule

Only confirmed defects belong in the blocking-bug section. Hypotheses must be labelled and must not be treated as confirmed until reproduced or supported by current exact-SHA source/tests/runtime evidence.
