# Bug Report

## Current confirmed repository blockers

### Fresh Full 1 m run fails at BUILDING_GRID

Windows run `f2dc662c-f445-4f6d-af75-223bb8c2f16c` on exact head `017d3c0686490acfc55d20906d22434fd8c5de7e` reached:

```text
ACQUIRING_TERRAIN
ACQUIRING_VECTORS
ACQUIRING_RAINFALL
PREPROCESSING_TERRAIN
ALLOCATING_ROOF_RAIN
BUILDING_GRID
FAILED
```

The vector stage completed in 24.411 s (PLATEAU; no OSM fallback), a substantial improvement from the prior 89.349 s path. The failure occurred immediately in BUILDING_GRID before model/SFINCS creation.

The old manifest persisted only:

```text
failure_code: INTERNAL_RUN_FAILED
failing_stage: BUILDING_GRID
```

and discarded the underlying exception, so the exact grid root cause cannot be recovered from that old manifest alone.

Web repair now committed:

- persist exception type/message/diagnostic-file path in manifest;
- write atomic `logs/failure_diagnostic.json` with traceback and runtime grid-input summary;
- harden polygon/road feature conversion against ragged/non-numeric/non-finite/invalid individual vector features;
- add `scripts/diagnose_grid_run.py` to replay BUILDING_GRID from an existing run's persisted `source_refs` without repeating live vector acquisition or SFINCS;
- deterministic tests cover diagnostic persistence, malformed-feature skipping, and persisted-source-ref replay loading.

The exact substantive grid cause remains host-local until the old failed run is replayed with this new instrumentation.

## Current external / host-local validation remaining

1. Run `scripts.diagnose_grid_run` against failed run `f2dc662c-f445-4f6d-af75-223bb8c2f16c` on the Windows host.
2. If replay passes, perform one fresh Full 1 m end-to-end run and confirm `COMPLETE`.
3. If replay fails, use the new exception/traceback diagnostics to identify the precise grid defect; apply only a tiny mechanical correction locally if it is inside the authorized allowance, otherwise return the deterministic diagnostic to Web.
4. SFINCS redistribution/bootstrap licensing remains a later packaging issue. Do not download or redistribute SFINCS.

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
