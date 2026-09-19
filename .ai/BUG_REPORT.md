# Bug Report

## Current confirmed repository blockers

None currently confirmed for the Full 1 m local-review slice.

The latest Codex run at `d33e4708b5c91e7ef607fe1fc6ce8be7cb63af9e` was blocked because the validation host no longer had the canonical Python 3.12.10 environment. Ruff passed; mypy/pytest could not run because host Python 3.14.3 lacked the pinned GIS/HydroMT packages. This is an environment-availability condition, not evidence of a source defect.

Web-side mitigation is now committed:

- `environment.yml` is explicitly the sole canonical review environment;
- `scripts/bootstrap_local_review.py` creates/updates it with conda/mamba/micromamba;
- `scripts/run_local_review.py` performs exact Python/package preflight before importing Uvicorn;
- Node.js 22 is checked before frontend builds;
- `docs/local-review.md` and README use the canonical setup path;
- deterministic local-review validation runs in GitHub Actions.

## Current external / host-local blockers

These cannot be fully resolved by repository edits:

1. The user's Windows validation host must have a conda-compatible environment manager available so the canonical environment can be restored.
2. Real provider calls depend on current external network/provider availability.
3. Real SFINCS validation depends on the already-present permitted local executable remaining accessible.
4. SFINCS redistribution/bootstrap licensing remains unresolved for later packaging; do not download or redistribute it as part of review validation.

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
