# Bug Report

## Current confirmed repository blockers

None currently confirmed after the Web repair at `8803df9d86631378018ef36d939ef8bb51605032`.

The latest live Windows run exposed and isolated two substantive repository defects, both now repaired by Web:

1. **PLATEAU review budget not enforced through CityGML parsing/cache work.** The run spent 89.349 s in `ACQUIRING_VECTORS` despite a 20-second policy. Deadline checks now cover cache reads, catalog processing, CityGML parsing/geometry loops, and output writing; OSM's 30-second budget likewise covers response/cache parsing and geometry processing.
2. **Completed real SFINCS output rejected at `READING_RESULTS`.** SFINCS returned 0 and produced a readable 500×500 `sfincs_map.nc`, but most active `hmax` values were NaN while active `h` remained finite. The reader now reconstructs only missing active `hmax` cells from finite `h` time output and records the reconstruction count in metadata. Infinite `hmax` and other invalid active fields remain hard failures.

A follow-up read of the same real artifact exposed one finite active depth sample at -0.0016127867 m. Codex made a temporary 1 cm clip under the tiny-fix allowance. Web reviewed that change against SFINCS 2.4.0 documentation and retained the 0.01 m magnitude specifically because it matches the engine's default `twet_threshold` for flooded/wet classification. The finalized reader preserves the raw NetCDF, clips only finite values in the dry band, rejects values below -0.01 m, and reports clipping diagnostics in normalized metadata.

The newest exact-head CI result is authoritative once green.

## Current external / host-local validation remaining

No external blocker was observed in the last run: GSI, PLATEAU and SFINCS all responded, and SFINCS completed successfully.

The only remaining proof needed is a fresh Windows run at the repaired exact SHA to verify:

1. PLATEAU either finishes within budget or exits to OSM rather than spending ~89 s in vector acquisition;
2. the real SFINCS output proceeds through `READING_RESULTS` and normalization;
3. final run state becomes `COMPLETE` and result metadata exposes the reconstructed-`hmax` diagnostic when applicable.

SFINCS redistribution/bootstrap licensing remains a later packaging issue. Do not download or redistribute SFINCS during review validation.

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
