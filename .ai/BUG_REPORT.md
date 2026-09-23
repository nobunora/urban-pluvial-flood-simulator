# Bug Report

## Current confirmed repository blockers

None currently confirmed after the OSM vector-contract repair and diagnostic-path portability repair.

### Latest repaired BUILDING_GRID defect

Windows replay proved the prior persisted OSM source refs build a valid 250,000-cell Full 1 m grid. A fresh run then failed with:

```text
AttributeError: 'OsmVectors' object has no attribute 'road_polygons'
```

This was a common-contract omission, not a hydraulic algorithm issue. OSM continues to provide road lines only; `OsmVectors.road_polygons` now explicitly returns an empty list so the Full 1 m grid can consume both PLATEAU and OSM through the same interface.

The two Codex repair commits were:

- `855076c7ba2f4dfaf81ee7c5ecb5acce2b45b9b2` — expose the empty OSM road-polygon contract;
- `67e0cb330c128aa9276d7c4802a002ee550106a3` — repair the focused regression-test placement.

A broader Windows focused run then exposed a diagnostic-path portability mismatch:

```text
expected: logs/failure_diagnostic.json
actual:   logs\\failure_diagnostic.json
```

Web repaired this by persisting diagnostic paths as POSIX-style relative paths on all operating systems.

## Current external / host-local validation remaining

Only one fresh Windows end-to-end Full 1 m run remains to prove the current exact head reaches `COMPLETE`:

1. live provider acquisition;
2. BUILDING_GRID with either PLATEAU or OSM;
3. model build;
4. existing permitted SFINCS execution;
5. real NetCDF reader;
6. normalization;
7. final `COMPLETE` state.

If a new failure occurs, the manifest + `failure_diagnostic.json` contract must preserve the exact exception and traceback. SFINCS redistribution/bootstrap licensing remains a later packaging issue.

## Local working-tree warning

The latest Codex report observed a pre-existing user change in the primary worktree:

```text
M floodsim/static/index.html
```

Validation correctly used a clean detached worktree and did not touch that change. Before user review, do not discard it automatically. Use a clean worktree or deliberately reconcile the user change so the browser UI corresponds to the exact PR SHA.

## Previously repaired relevant defects

### Local review build removed `/smoke.html`

A normal Vite build previously deleted the committed build-free diagnostic page. Web moved/preserved it through `web/public/smoke.html`; the launcher now verifies both `index.html` and `smoke.html` after a build.

### Local review launcher Ruff `I001`

The launcher initially had import-order/blank-line formatting failures. Web repaired them; Codex later confirmed:

```text
python -m ruff check floodsim tests scripts
# PASS
```

### Adaptive rc3 geometry failures

Two pinned-rc3 geometry failure classes were repaired by Web:

- polygon refinement consuming intermediate levels;
- staged refinement calling lower-level neighbor logic after globally leading levels became empty.

Focused Adaptive regression passed at `aa28de2a61bdbe43ad415ca8b7d1ad2cc2aace61`. Adaptive remains disabled and is not the current review priority.

### Authority-less AEQD writer limitation

Pinned HydroMT-SFINCS rc3 serializes invalid optional EPSG metadata for authority-less CRS. The repository-owned quadtree writer seam removes only invalid `epsg=None` / `EPSG:None` metadata while preserving WKT/CF/UGRID semantics. It was validated at `1c585d6b8e5dda63d116526779d7098f97bd03f5`.

## Reporting rule

Only reproducible exact-SHA repository defects belong in the blocking section. Missing local tools/environments, provider outages and engine availability must be classified separately as host/external blockers.
