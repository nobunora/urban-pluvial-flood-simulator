# Persistent Codex Handoff

## Workspace and role split

- Persistent branch: `codex/persistent-workspace`.
- Communication channel: one long-lived Draft PR #12 targeting `main`.
- Keep PR #12 open, Draft, and unmerged unless the user explicitly requests merge.
- **Web ChatGPT is the primary implementation owner** for substantive source/test/docs/generated-asset changes and repository writes.
- **Local Codex (Luna) is primarily responsible for audit, execution tests, validation, runtime diagnostics, upstream-contract investigation, and reporting.**
- Local Codex may make only small, local, non-architectural corrections discovered during validation (for example an obvious typo/import/test-fixture/formatting correction). It must not implement features, algorithms, compatibility adapters, public/API changes, dependency changes, generated API changes, or multi-file behavioral repairs unless the user explicitly expands that permission.
- Any tiny Codex correction must be isolated and explicitly reported. Web remains the normal coding path.

## Validated phases

- Phase 0: `validated`.
- Phase 1: `validated`.
- Phase 2A geographic providers: `validated`.
- Phase 2B CSIS/JMA providers and API contracts: `validated` at `660579bfebb5f1e275004ed0f1d0a0b4db7cb322`.
- Phase 3: implementation `validated` at `62dc85fa163587ea73a875c59067bcd5a8dfe79a`.
  - Gates A/B/C/E/F passed in the exact-head audit.
  - Real SFINCS Gate D remains externally blocked only because no permitted local SFINCS executable is installed.
  - No known Phase 3 repository defect remains.

## Phase 4 status

Phase 4 Adaptive is `implementation-in-progress / exact-head validation pending`. Adaptive remains rejected by the existing `GRID_ADAPTIVE_NOT_AVAILABLE` boundary and must not be enabled yet.

The first Phase 4 foundation SHA `a17ff7b7f013ff7672e22da419a34e497d30d3d2` introduced the fixed 1/2/4/8/16/32 m classifier hierarchy, terrain-fit thresholds, hard-feature refinement foundation, 2:1 balancing, diagnostics, and Full 1 m road-mask preservation.

Local Codex audited that foundation and found three classifier defects. Web repaired them at `1d189e358bef2cd0363213feff61d7ed5ef1e813`:

1. required candidate curvature / depression-ridge connectivity / flow-accumulation evidence is now computed without inventing unspecified gating thresholds;
2. threshold identity now hashes the actual threshold configuration;
3. the `within 2 m` building/road rule now uses projected Euclidean source-cell footprint distance, keeps direct features at 1 m, and constrains the buffer to <=2 m rather than forcing it all to 1 m.

## Latest Codex validation at `1d189e...`

- Gate A exact SHA/delta: PASS.
- Gate B tests/static/performance diagnostic: FAIL only because of two Ruff `RUF046` diagnostics.
- Gate C repaired classifier audit: PASS.
- Gate D independent unmodified rc3 authority-less quadtree failure reproduction: PASS.
- Gate E WKT-only round-trip probe: PASS.
- Gate F next-slice reconnaissance: PASS.
- Compatibility decision: `SEAM_SUPPORTED`.
- Real SFINCS execution: BLOCKED because no permitted local executable is available.

Deterministic tests otherwise passed: 7 Phase 4 tests, 18 Phase 4+3 tests, 79 full tests, and mypy. Codex made no source correction.

## Web repairs after that audit

Web ChatGPT has now:

- removed the two redundant `int(math.ceil(...))` calls reported by Ruff;
- added `floodsim/sfincs/quadtree_writer.py` as a repository-owned, quadtree-only compatibility seam for the pinned HydroMT-SFINCS 2.0.0rc3 authority-less CRS bug;
- added `tests/test_phase4_quadtree_writer.py` with both authority-backed delegation coverage and a real pinned-rc3 authority-less AEQD WKT-only round-trip test.

The compatibility writer behavior is intentionally narrow:

- if `crs.to_epsg()` returns an integer, delegate to the ordinary rc3 `SfincsQuadtreeGrid.write(..., data_vars=[])` path;
- if the true quadtree CRS is authority-less, preserve full `crs_wkt`, CF/UGRID metadata, topology, conventions, coordinate units/grid mapping and rc3 integer casting;
- omit only invalid optional `epsg=None` / `epsg_code="EPSG:None"` authority metadata;
- keep model config `epsg=None` and the true projected `crsgeo` state;
- do not alter the regular Full 1 m writer and do not globally monkey-patch Xarray.

This new source is not accepted until Local Codex executes the latest exact head named in the newest PR comment.

## Canonical Adaptive constraints to preserve

From `docs/specs/v0.1-implementation-spec.md` §12:

- levels exactly `1, 2, 4, 8, 16, 32 m`;
- building intersection: 1 m;
- within 2 m of building: <=2 m;
- road surface: 1 m;
- within 2 m of road: <=2 m;
- narrow channel/major concentrated flow path, when identified: <=2 m;
- plane residual thresholds remain the canonical provisional table;
- curvature, local depression/ridge connectivity, and flow-accumulation concentration evidence must be computed;
- best available high-resolution terrain must remain available for subgrid generation;
- diagnostics include cell counts, total/equivalent cells, reduction ratio, refinement reasons, resolution layer, and threshold configuration identity;
- no fake permanent EPSG may replace the canonical local AEQD.

Canonical Full-vs-Adaptive benchmark thresholds include flooded-area IoU at depth >=0.05 m >=0.90, wet-cell median max-depth error <=0.03 m, p95 <=0.10 m, final surface-water-volume relative difference <=2%, unchanged important-flow-path connectivity class, and fewer Adaptive cells in the open-area class. No numeric runtime/memory threshold is fixed.

## Next required Codex validation/execution pass

Use the exact SHA named by the latest PR comment. In a disposable/clean worktree and the pinned Python 3.12.10 / HydroMT-SFINCS rc3 environment:

1. verify exact SHA, clean status, and the Web delta after `1d189e...`;
2. run `tests/test_phase4.py`, `tests/test_phase4_quadtree_writer.py`, Phase 4+3 focused tests, full pytest, Ruff, mypy, and `git diff --check`;
3. prove the two previous Ruff diagnostics are gone;
4. execute the real pinned-rc3 authority-less AEQD round-trip test and independently inspect the written NetCDF for exact/equivalent WKT, absent false EPSG metadata, topology/face count/refinement-level preservation, node coordinate units/grid mapping, and `qtrfile`/config semantics;
5. verify authority-backed CRS delegates to the ordinary rc3 writer path;
6. confirm the compatibility adapter does not affect Phase 3 regular-grid behavior and Adaptive remains disabled;
7. if any permitted SFINCS executable exists, run the strongest safe tiny quadtree acceptance possible; otherwise report the real-engine gate as BLOCKED and do not download anything;
8. investigate failures to root cause. Substantive fixes stay Web-owned; only tiny isolated corrections are allowed under the current role split.

## External engine rule

Do not automatically download SFINCS. If no permitted `SFINCS_BIN`, PATH executable, or managed-local executable exists, report the real-engine gate as `BLOCKED` and continue all non-engine validation.

Do not infer completion from commit messages. Completion requires exact-head evidence reviewed by Web ChatGPT.
