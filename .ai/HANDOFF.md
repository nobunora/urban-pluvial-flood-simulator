# Persistent Codex Handoff

## Workspace and role split

- Persistent branch: `codex/persistent-workspace`.
- Communication channel: long-lived Draft PR #12 targeting `main`.
- Keep PR #12 open, Draft, and unmerged unless the user explicitly requests merge.
- **Web ChatGPT owns substantive implementation**: source, algorithms, tests, docs, generated assets, compatibility adapters, public/API contracts, dependency changes and multi-file behavioral fixes.
- **Local Codex/Luna primarily owns validation and execution**: exact-SHA tests, runtime probes, static checks, upstream-contract investigation, root-cause analysis and reporting.
- Codex may make only a tiny isolated non-architectural correction if genuinely necessary to finish validation (obvious typo/import/test-fixture/formatting class). It must not implement features, algorithms, adapters, API changes, dependency changes or multi-file behavioral repairs.
- Any tiny Codex correction must be isolated and explicitly reported.

## Validated history

- Phase 0: validated.
- Phase 1: validated.
- Phase 2A: validated.
- Phase 2B: validated at `660579bfebb5f1e275004ed0f1d0a0b4db7cb322`.
- Phase 3 Full 1 m implementation: validated at `62dc85fa163587ea73a875c59067bcd5a8dfe79a` except that prior audits had no permitted engine available for real execution.
- Phase 4 classifier repairs at `1d189e358bef2cd0363213feff61d7ed5ef1e813`: semantic audit PASS.
- Phase 4 quadtree writer seam at `1c585d6b8e5dda63d116526779d7098f97bd03f5`: `validated-seam` in the canonical Python 3.12.10 / HydroMT-SFINCS 2.0.0rc3 environment.

## Newly available real SFINCS engine

Latest Codex execution discovered a permitted managed-local SFINCS 2.4.0 Galibier executable at:

`SFINCS_2026_01_release/SFINCS_v2.4.0_Galibier_release_exe/sfincs.exe`

It was not downloaded or installed by Codex. The next exact-head task may use this existing managed-local executable for the strongest safe tiny smoke after deterministic gates pass.

## Phase 4 latest failure and Web repair

Codex tested exact head `1aeebc4037882a44a9f04898f2528a09b8d4f342` and stopped on a substantive Gate B failure:

- flat 64x64 Adaptive case passed;
- hard building/road case failed;
- odd 33x35 padded case failed;
- both failures were deterministic `IndexError` exceptions inside pinned rc3 `refine_in_polygon()` / intermediate-level lookup;
- no Codex source correction was made.

Root cause: the repository passed multiple exact-target polygons at different refinement levels to rc3. rc3 restarts each polygon at level zero. An earlier polygon can consume every cell at a lower/intermediate level, causing a later polygon to index a level that is empty or absent.

Web ChatGPT has replaced the production polygon-driven refinement path with a staged rc3 cell-refinement path:

1. Start from the actual pinned-rc3 32 m base quadtree.
2. For each existing rc3 level in order, select a parent face only when its overlapping Full-1 m source block contains a validated classifier target finer than the parent.
3. Call pinned rc3 `QuadtreeGrid.refine_cells()` for that existing level.
4. Continue monotonically through 32 -> 16 -> 8 -> 4 -> 2 -> 1 m.
5. Re-run rc3 neighbour/UV/UGRID finalization after the staged refinement.
6. Install the resulting rc3 UGRID Dataset on the model component, then restore canonical authority-less AEQD and config `epsg=None` / correct `crsgeo`.
7. Keep classifier polygonization only as inspectable diagnostic output; do not feed those multi-level polygons into `refine_in_polygon()`.

The existing safety guard remains: no source-overlapping actual face may be coarser than any validated classifier target cell it covers.

## Current Adaptive geometry/field scope

Adaptive remains disabled by `GRID_ADAPTIVE_NOT_AVAILABLE`.

Implemented:

- fixed 1/2/4/8/16/32 m classifier hierarchy;
- hard building/road refinement and <=2 m feature buffers;
- actual pinned-rc3 quadtree geometry from a 32 m base;
- ceil-to-32 m padding with inactive outside-domain faces;
- actual `level/n/m` face mapping back to Full-1 m source indices;
- face mask/Manning aggregation;
- area-conservative face roof-rain weights;
- authority-less AEQD quadtree serialization compatibility;
- build-free `/smoke.html` Full 1 m diagnostic surface;
- source-coverage regression checks for hard-feature, odd-dimension and asymmetric domains.

Not yet implemented/enabled:

- high-resolution terrain/subgrid integration for Adaptive;
- Adaptive precipitation forcing;
- Adaptive face-result reader/normalizer;
- Full-vs-Adaptive benchmark acceptance;
- Adaptive run API enablement.

## Canonical constraints that still apply

From `docs/specs/v0.1-implementation-spec.md` §12:

- levels exactly `1, 2, 4, 8, 16, 32 m`;
- building footprint 1 m; within 2 m <=2 m;
- road surface 1 m; within 2 m <=2 m;
- no fake permanent EPSG;
- best high-resolution terrain must remain available for subgrid generation;
- Adaptive is accuracy-first and must later pass Full-vs-Adaptive benchmark thresholds before enablement.

## Next Codex task

Validate the exact SHA named by the newest PR comment. Use a clean disposable worktree and the canonical environment.

Priority:

1. Re-run the formerly failing committed Adaptive tests first and prove the rc3 `IndexError` is gone.
2. Run focused Phase 3/4 tests, full pytest, Ruff, mypy and `git diff --check`.
3. Run frontend `api:check`, typecheck, tests and build.
4. Exercise `/smoke.html` through the real FastAPI HTTP routes.
5. Independently probe flat, hard-feature, odd/padded, asymmetric, thin-road, isolated-1m and checkerboard cases.
6. Prove exact one-face source coverage, actual face size <= target, padding mask 0, road Manning 0.020, building mask 0 and roof-rain mass conservation.
7. Write/reload one actual Adaptive grid with the validated authority-less writer.
8. If deterministic gates pass, use the already-present managed-local SFINCS executable for the strongest safe tiny real-engine smoke. Do not download or install anything.

Substantive failures remain Web-owned. Codex should stop at diagnosis and minimal repro rather than implementing any algorithmic or multi-file repair.
