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
- Phase 3: validated at `62dc85fa163587ea73a875c59067bcd5a8dfe79a`; real SFINCS execution remains externally blocked only because no permitted executable is installed.
- Phase 4 classifier repairs at `1d189e358bef2cd0363213feff61d7ed5ef1e813`: semantic audit PASS.
- Phase 4 quadtree writer seam at `1c585d6b8e5dda63d116526779d7098f97bd03f5`: **validated-seam** in a fresh canonical environment.
  - Python 3.12.10 / pinned HydroMT-SFINCS 2.0.0rc3 commit `82e58ee85136cf5155c92b42bb9a397869ed8035`.
  - mypy PASS: no issues in 40 source files.
  - focused Phase 3/4 tests PASS: 20 passed.
  - Ruff PASS and `git diff --check` PASS.
  - authority-less AEQD WKT-only writer round trip, mask/Manning preservation and authority-backed delegation all passed in prior execution probes.
  - real SFINCS remains externally BLOCKED because no permitted engine executable is available.

## Phase 4 current Web-owned slice

Adaptive remains disabled by `GRID_ADAPTIVE_NOT_AVAILABLE`.

Web has now added:

- `floodsim/sfincs/adaptive_quadtree.py`
- `tests/test_phase4_adaptive_quadtree.py`

This slice converts the validated classifier to actual pinned-rc3 quadtree geometry and normalized face fields:

1. **Classifier -> rc3 refinement geometry**
   - 32 m base grid.
   - `refinement_level = log2(32 / target_size)` for target sizes 16/8/4/2/1 m.
   - classifier masks are polygonized in projected coordinates.
   - polygons are contracted by `1e-7 m` only to avoid rc3's boundary-touch `intersects()` rule spuriously refining the neighbouring cell; this is a compatibility/numerical seam, not a hydraulic threshold.
   - rc3 may refine additional sibling/transition faces where required by quadtree topology; it must never leave a face coarser than the validated classifier target over the source area.

2. **Actual rc3 quadtree creation**
   - uses the rc3-required temporary integer EPSG only during `create()`.
   - immediately replaces topology CRS with the canonical local authority-less CRS.
   - keeps config `epsg=None` and true `crsgeo`.
   - base dimensions use ceil-to-32 m padding; padding faces are inactive and excluded from source-area/rainfall mass.

3. **Face mask / Manning mapping**
   - maps each actual rc3 face back to exact aligned Full-1 m source indices using rc3 `level`, `n`, and `m` fields.
   - rejects any face that is coarser than any validated classifier target cell it covers.
   - outside padding -> mask 0.
   - active/outflow source semantics are preserved on represented faces.
   - Manning is aggregated over active source cells; direct road cells remain 1 m under the validated hard-refinement rule.

4. **Area-conservative roof-rain aggregation**
   - face rain weight = sum of source 1 m rain weights covered by the face / full quadtree face area.
   - padding contributes zero.
   - total `sum(face_weight * face_area)` must equal the Full-1 m weighted source area within strict deterministic tolerance.
   - the rain-weight field is returned as model-building data but is not yet wired into Adaptive precipitation forcing in this slice.

5. **Tests added**
   - flat 64x64 -> exactly four 32 m base faces.
   - actual rc3 hard building/road mapping -> 1 m faces, building mask 0, road Manning 0.020.
   - every source-overlapping rc3 face must be no coarser than the classifier target beneath it.
   - odd 33x35 domain -> 64x64 padded base extent, zero-overlap padding inactive, edge source cells remain 1 m, rain mass conserved.

## Canonical constraints that still apply

From `docs/specs/v0.1-implementation-spec.md` §12:

- levels exactly `1, 2, 4, 8, 16, 32 m`;
- building footprint 1 m; within 2 m <=2 m;
- road surface 1 m; within 2 m <=2 m;
- no fake permanent EPSG;
- best high-resolution terrain must remain available for subgrid generation;
- Adaptive is accuracy-first and must later pass Full-vs-Adaptive benchmark thresholds before enablement.

## Next Codex task

The newest PR comment names the exact SHA to validate. Codex should:

- use a clean disposable worktree and the now-working fresh canonical environment policy;
- verify exact Web delta and no unrelated files;
- run new Adaptive-quadtree tests plus prior Phase 4/3 tests, full pytest, Ruff, mypy and `git diff --check`;
- independently inspect refinement geometry and actual rc3 face mapping;
- adversarially check flat, hard-feature, odd-dimension/padding, transition and mass-conservation cases;
- verify actual face resolution never exceeds the classifier target over source cells;
- verify direct building/road semantics and padded inactive faces;
- verify roof-rain area conservation numerically from actual rc3 faces;
- keep Adaptive disabled and do not implement subgrid/forcing/result/API work;
- do not download SFINCS; if no permitted engine exists, report the engine gate as externally BLOCKED.

Substantive fixes remain Web-owned. After this slice validates, Web will implement high-resolution terrain/subgrid creation, Adaptive precipitation forcing and then face-based result normalization/benchmarking.
