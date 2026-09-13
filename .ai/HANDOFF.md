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
- Phase 3 Full 1 m implementation: validated at `62dc85fa163587ea73a875c59067bcd5a8dfe79a`; a real-engine smoke is now possible because a permitted local executable has been found.
- Phase 4 classifier repairs at `1d189e358bef2cd0363213feff61d7ed5ef1e813`: semantic audit PASS.
- Phase 4 quadtree writer seam at `1c585d6b8e5dda63d116526779d7098f97bd03f5`: `validated-seam` in the canonical Python 3.12.10 / HydroMT-SFINCS 2.0.0rc3 environment.

## Newly available real SFINCS engine

Latest Codex execution discovered a permitted managed-local SFINCS 2.4.0 Galibier executable at:

`SFINCS_2026_01_release/SFINCS_v2.4.0_Galibier_release_exe/sfincs.exe`

It was not downloaded or installed by Codex. The next exact-head task may use this existing executable for the strongest safe tiny Full 1 m smoke after deterministic gates pass.

## Phase 4 latest failures and Web repair

### Failure at `1aeebc...`

The polygon-driven Adaptive geometry path failed because pinned rc3 restarts each refinement polygon at level zero. A prior polygon could consume an intermediate level that a later polygon then indexed. Codex stopped at diagnosis; Web replaced production polygon refinement with staged `QuadtreeGrid.refine_cells()` calls. Polygonization remains diagnostic-only.

### Failure at `0e5cbef...`

Codex then found a second rc3 integration defect in hard building/road, odd 33x35 and asymmetric 65x34 cases. Staged `refine_cells()` reached rc3 `find_lower_level_neighbors()` with an empty immediately-coarser level and rc3's `binary_search()` raised `IndexError`.

This occurs when the whole domain has already been refined past one or more globally coarser levels. In that state there is no coarser neighbor to find, but rc3 still assumes the immediately-coarser level contains cells whenever `ilev > 0`.

Web ChatGPT has now repaired the staged path without modifying or monkey-patching rc3:

1. Start with the actual pinned-rc3 32 m base quadtree.
2. Refine physical parent sizes monotonically `32 -> 16 -> 8 -> 4 -> 2 -> 1 m` using pinned rc3 `refine_cells()`.
3. Before each stage/iteration, inspect the first populated rc3 level.
4. If every globally coarser level has disappeared, promote the first populated level to level zero using the physically equivalent transform:
   - `dx/dy /= 2**leading_level`;
   - `nmax/mmax *= 2**leading_level`;
   - `level -= leading_level`.
5. Keep `n/m` indices unchanged; therefore every cell retains the same physical extent and coordinates.
6. Recompute rc3 level indices/centres after a rebase.
7. Reject any internal level gap before neighbor/UGRID finalization.
8. Derive final face resolution from the Dataset's actual rebased base `dx`, not from an assumed permanent 32 m level zero.
9. Keep the existing invariant that no source-overlapping actual face may be coarser than any classifier target cell beneath it.
10. Restore canonical authority-less AEQD and config `epsg=None` / correct `crsgeo` after installing the rc3 Dataset.

No substantive Codex repair was made. The new exact head requires independent validation.

## Current Adaptive geometry/field scope

Adaptive remains disabled by `GRID_ADAPTIVE_NOT_AVAILABLE`.

Implemented:

- fixed 1/2/4/8/16/32 m classifier hierarchy;
- hard building/road refinement and <=2 m feature buffers;
- actual pinned-rc3 staged quadtree geometry;
- geometry-preserving rebase when globally leading levels become empty;
- ceil-to-32 m original analysis padding with inactive outside-domain faces;
- actual `level/n/m` face mapping back to Full-1 m source indices;
- face mask/Manning aggregation;
- area-conservative face roof-rain weights;
- authority-less AEQD quadtree serialization compatibility;
- build-free `/smoke.html` Full 1 m diagnostic surface;
- exact source-coverage regression checks for hard-feature, odd-dimension and asymmetric domains.

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

Validate the exact SHA named by the newest PR comment in a clean disposable worktree using the canonical environment.

Priority:

1. Re-run `tests/test_phase4_adaptive_quadtree.py` first and prove both prior rc3 `IndexError` classes are gone.
2. Specifically audit the geometry-preserving leading-level rebase: before/after physical coordinates must match, `n/m` must remain valid, and final base `dx/nmax/mmax` must describe the same physical padded extent.
3. Run focused Phase 3/4 tests, full pytest, Ruff, mypy and `git diff --check`.
4. Independently probe flat, hard-feature, odd/padded, asymmetric, thin-road, isolated-1m, checkerboard and all-domain-finer cases.
5. Prove exact one-face source coverage, actual face size <= target, padding mask 0, road Manning 0.020, building mask 0 and roof-rain mass conservation.
6. Write/reload one actual Adaptive grid with the validated authority-less writer.
7. Run frontend checks and exercise `/smoke.html` through real FastAPI routes.
8. If deterministic gates pass, use the already-present managed-local SFINCS executable for the strongest safe tiny **Full 1 m** real-engine smoke. Adaptive engine E2E is still out of scope.

Substantive failures remain Web-owned. Codex should stop at diagnosis and minimal repro rather than implementing any algorithmic or multi-file repair.
