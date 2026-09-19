# Bug Report

## Current confirmed repository blockers

None currently confirmed after the Web repair at `6508ac729573c3d0086ae418a09089d32e312ff1`.

Two review-path defects were confirmed and repaired in the latest cycle:

1. **Cancellation stayed at `CANCELLING` while a provider call was blocked.** Codex applied the permitted small repair at `26c2b1e6abc2db1b20bfb16d5bcc1c82d29d4ba5`, making the persisted/UI lifecycle reach terminal `CANCELLED` immediately and idempotently. Local Windows revalidation passed.
2. **Vector acquisition had no total wall-clock budget.** The live Tokyo Station review run remained in `ACQUIRING_VECTORS` for more than 90 seconds and never reached SFINCS. Web added monotonic provider deadlines, streaming PLATEAU CityGML download interruption, a 20-second PLATEAU review budget and 30-second OSM fallback budget. Exact-head deterministic CI passes with 101 tests.

## Current external / host-local blockers

Only genuinely live conditions remain to be proven:

1. current GSI / PLATEAU / OSM network availability on the Windows validation host;
2. whether the bounded PLATEAU path falls back to OSM successfully for the Tokyo Station review case;
3. execution of the already-present permitted SFINCS 2.4.0 Galibier binary;
4. generation/readability of `sfincs_map.nc` and repository result normalization;
5. later SFINCS redistribution/bootstrap licensing for packaging. Do not download or redistribute SFINCS as part of review validation.

Environment-manager absence and Node.js 24 are no longer blockers: the bootstrap helper can obtain user-local portable micromamba, and the launcher supports Node.js >=22.12.

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
