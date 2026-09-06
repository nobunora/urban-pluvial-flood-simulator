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

Phase 4 Adaptive is `implementation-in-progress`. Adaptive remains rejected by the existing `GRID_ADAPTIVE_NOT_AVAILABLE` boundary and must not be enabled yet.

The first Phase 4 foundation SHA `a17ff7b7f013ff7672e22da419a34e497d30d3d2` added:

- fixed `1, 2, 4, 8, 16, 32 m` hierarchy;
- provisional canonical RMSE/max-residual thresholds;
- deterministic plane-fit terrain diagnostics;
- building/road hard-refinement foundation;
- 2:1 balancing;
- resolution/refinement diagnostics and cell-count reduction diagnostics;
- preservation of the normalized Full 1 m road mask.

Local Codex audited that SHA and returned `needs-fix`:

- Gate A exact SHA/delta: PASS;
- Gate B tests/static: PASS;
- Gate C Adaptive classifier audit: FAIL;
- Gate D independent rc3 quadtree blocker runtime reproduction: BLOCKED in that turn;
- Gate E compatibility-seam investigation: PASS;
- Gate F quadtree/subgrid/result reconnaissance: PASS.

## Phase 4 classifier defects repaired by Web

Web ChatGPT has now repaired the three confirmed Gate C defects:

1. **Required terrain evidence** — candidate metrics now compute local curvature, strict interior depression/ridge connectivity evidence, and deterministic D8 flow-accumulation concentration in addition to plane RMSE/max residual. The canonical spec defines no numeric gating thresholds for curvature/connectivity/flow, so Web did not invent any.
2. **Threshold identity** — identity is now a deterministic SHA-256-derived identity over the actual threshold maps, so custom threshold configurations cannot masquerade as the default configuration.
3. **Feature buffer** — the §12.2 `within 2 m` rule is now evaluated in projected metric space between normalized 1 m source-cell footprints. Building/road source cells remain exactly 1 m; buffer cells may be 1 m or 2 m but never coarser than 2 m.

Focused Phase 4 regression tests were expanded to cover those repairs. These Web repairs require exact-head Codex validation before acceptance.

## Quadtree authority-less CRS blocker

Pinned HydroMT-SFINCS source commit:

`82e58ee85136cf5155c92b42bb9a397869ed8035` (`2.0.0rc3`)

The pinned rc3 `SfincsQuadtreeGrid.write()` path:

- converts the UGRID object to a Dataset with full `crs_wkt`;
- calls `self.crs.to_epsg()`;
- adds `mesh2d_crs.attrs["epsg"]` and `epsg_code`;
- writes NetCDF.

The canonical local AEQD CRS has no EPSG authority, so `to_epsg()` is `None` and the current writer attempts invalid authority metadata (`epsg=None`, `EPSG:None`). Source evidence indicates this is an upstream rc3 authority-less-CRS limitation, not permission to invent a fake EPSG.

The recommended compatibility direction is a **repository-owned, quadtree-only writer adapter** that preserves rc3 Dataset preparation and exact WKT/CF/UGRID metadata while omitting only invalid optional EPSG authority attributes. Do not alter the regular Full 1 m writer and do not globally monkey-patch Xarray.

Web has deliberately not implemented this private-rc3 adapter yet because the previous Codex audit did not independently complete the runtime reproduction/round-trip probe. The next Codex task must reproduce the exact failure and prove that pinned rc3 reconstructs the authority-less AEQD from `crs_wkt` when the invalid EPSG attributes are absent. After that evidence, Web implements the adapter.

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

1. verify exact SHA, clean status, and Web-only delta;
2. run focused Phase 4 tests, Phase 4+3 tests, full pytest, Ruff, mypy, and `git diff --check`;
3. adversarially validate the repaired classifier, especially custom threshold identity, projected-metric <=2 m buffer, candidate connectivity/flow evidence, odd dimensions, partial blocks, isolated/checkerboard features, and 2:1 balance;
4. independently reproduce the pinned rc3 quadtree authority-less AEQD write failure at runtime;
5. in a disposable diagnostic only, remove the invalid optional EPSG authority attrs while retaining exact `crs_wkt`, write the NetCDF, and prove pinned rc3/xugrid can read the exact AEQD CRS back;
6. report whether that WKT-only round trip is sufficient evidence for Web to implement the quadtree-only adapter;
7. continue reconnaissance for actual refinement geometry, mask/Manning faces, area-conservative roof-rain aggregation, subgrid creation, and face-based result normalization;
8. do not implement the compatibility adapter or other substantive Phase 4 features. Only tiny local validation corrections are allowed under the current role split, and any such correction must be isolated and explicitly reported.

## External engine rule

Do not automatically download SFINCS. If no permitted `SFINCS_BIN`, PATH executable, or managed-local executable exists, report the real-engine gate as `BLOCKED` and continue all non-engine validation.

Do not infer completion from commit messages. Completion requires exact-head evidence reviewed by Web ChatGPT.
