# Persistent Codex Handoff

## Single source of truth

- Persistent branch: `codex/persistent-workspace`.
- Communication channel: Draft PR #12 targeting `main`.
- Keep PR #12 open, Draft, and unmerged unless the user explicitly requests merge.
- The **newest top-level PR comment marked authoritative** supplies the exact SHA and the only active Codex task.
- Older validation/task comments are historical evidence only and must not be executed.

## Role split — strict

### Web ChatGPT is the primary repository implementation owner

Web ChatGPT performs substantive source/test/docs/config/workflow/generated-asset/dependency/API/UI implementation and repairs.

To reduce unnecessary round trips, Codex/Luna may make and push a **tiny isolated mechanical correction** discovered during host-local validation only when all of these are true:

- the intended behavior is already unambiguous;
- the change is small and local (normally one file; at most two);
- it is formatting/import/typo/quoting/path/test-fixture/launcher-glue class;
- it does not alter algorithms, hydraulic semantics, public API, dependencies, generated contracts/assets, product specification, architecture, or Adaptive behavior;
- the remote persistent branch still points to the exact task SHA before push;
- Codex records the exact diff/reason and reruns the affected check.

Anything larger or behaviorally substantive returns to Web ChatGPT.

### Codex/Luna owns only host-local execution evidence

Codex is used only for work that Web ChatGPT cannot perform on the user's local Windows validation host:

- restore/create the canonical local Python environment on that host;
- verify the already-present local SFINCS executable and its SHA-256;
- run the local launcher under the exact PR SHA;
- perform real same-origin HTTP checks against the locally running process;
- exercise external providers from the local host;
- run the strongest safe tiny Full 1 m SFINCS execution using the already-present permitted executable;
- report local filesystem/process/provider/engine behavior.

No SFINCS download, installation, copying, or redistribution is authorized.

## Current product priority

A **reviewable Full 1 m vertical slice** has priority over deeper Adaptive work.

The Full 1 m execution slice has passed local Windows validation through `COMPLETE`. By explicit user direction, the next implementation phase is now the v0.1 result-view contract already defined in the canonical product/UI specifications.

Current result-view scope:

- automatic RESULT entry after a completed Full 1 m run;
- GSI standard background map through MapLibre GL JS;
- backend-rendered maximum-depth PNG placed on exact result bounds;
- time-depth and grid-resolution result layers using the existing result APIs;
- timeline over actual output indices only;
- native backend point inspection (never sample the display PNG);
- backend depth legend;
- provider/engine provenance;
- backend-sourced limitations;
- “new analysis” returning to editable setup while retaining the previous setup values.

Still deferred:

- Adaptive enablement;
- Adaptive subgrid/forcing/result normalization;
- Full-vs-Adaptive benchmark acceptance;
- rainbow color mode until the backend exposes its canonical palette/legend contract;
- packaging/installer.

Adaptive remains disabled by `GRID_ADAPTIVE_NOT_AVAILABLE`.

## Canonical local-review environment

`environment.yml` is the only environment contract for local review and validation.

It pins Python 3.12.10 and the required GIS/HydroMT/HydroMT-SFINCS stack. `requirements.txt` is not the canonical review environment.

Web-owned repository support:

```text
python -m scripts.bootstrap_local_review
python -m scripts.run_local_review --check-env
python -m scripts.run_local_review
```

The launcher now fails early with a clear diagnostic when the active Python/package versions are not canonical, before importing Uvicorn or starting the application.

Normal frontend rebuild requires Node.js >=22.12. Node.js 24 is supported.

## Web-owned deterministic validation

`.github/workflows/local-review-ci.yml` now performs the deterministic checks Web can own without the user's local SFINCS executable:

- create `environment.yml`;
- launcher canonical-environment preflight;
- Ruff;
- mypy;
- full pytest;
- `git diff --check`;
- Node.js 24 in CI (launcher contract: Node.js >=22.12);
- `npm ci`;
- `api:check`;
- TypeScript typecheck;
- Vitest;
- Vite build;
- verify `index.html` and `smoke.html` survive the build;
- start the real FastAPI local-review launcher;
- HTTP 200 for `/`, `/smoke.html`, and health;
- Full 1 m 500 m x 500 m estimate = 250,000 cells.

Codex must not duplicate these checks merely to compensate for missing local dependencies. Use CI evidence first.

## Current implementation status

Full 1 m execution is locally validated and `local-review-ready` at the pre-result-UI baseline.

The canonical documents identify result visualization as the next incomplete v0.1 outcome:

```text
run -> read results -> display maximum flood depth on map -> inspect time-dependent depth and point values
```

Web ChatGPT has started this phase on the persistent PR:

- result metadata and native inspection APIs were already implemented in the backend;
- MapLibre 6.10.0 was already present in the frontend dependencies;
- frontend API client now exposes result metadata, inspection and layer URLs;
- RESULT mode now loads automatically after run `COMPLETE`;
- GSI standard raster tiles are the base map with attribution;
- backend-rendered result PNG is placed using exact geographic result bounds;
- maximum-depth, time-depth and grid-resolution layer selectors are implemented;
- time-depth timeline snaps to actual output indices;
- map clicks use backend native point inspection;
- backend provenance, warnings, depth legend and limitations are displayed;
- “new analysis” clears result/run state while retaining setup inputs;
- result geometry and result-panel behavior have deterministic frontend tests.

No Codex task is active while deterministic CI for the Web-owned result-view implementation is pending. After CI is green, Codex should be used only for the strongest host-local browser/SFINCS result-view smoke that Web cannot perform.

## Preserved validated history

- Phase 0: validated.
- Phase 1: validated.
- Phase 2A: validated.
- Phase 2B: validated at `660579bfebb5f1e275004ed0f1d0a0b4db7cb322`.
- Phase 3 Full 1 m implementation: validated at `62dc85fa163587ea73a875c59067bcd5a8dfe79a`.
- Phase 4 classifier semantic audit: PASS at `1d189e358bef2cd0363213feff61d7ed5ef1e813`.
- Phase 4 authority-less AEQD quadtree writer seam: `validated-seam` at `1c585d6b8e5dda63d116526779d7098f97bd03f5`.
- Former Adaptive hard-feature / odd-size / asymmetric rc3 geometry failures passed focused regression at `aa28de2a61bdbe43ad415ca8b7d1ad2cc2aace61`.

## Local SFINCS

A permitted existing SFINCS 2.4.0 Galibier executable was previously found on the validation host at:

```text
SFINCS_2026_01_release/SFINCS_v2.4.0_Galibier_release_exe/sfincs.exe
```

Codex may use this existing file only after the newest authoritative exact-SHA instruction says to do so.

## Reporting rule

For the active exact SHA, Codex should return only:

- local environment restoration result;
- exact launcher command and URL;
- local HTTP observations not already established by CI;
- external-provider stage/results;
- existing SFINCS path + SHA-256;
- Full 1 m real-engine stage/return code/log/result-file evidence;
- confirmed repository defect(s), if any, with minimal repro;
- external blockers;
- final worktree state;
- disposition: `local-review-ready | needs-web-fix | blocked-external`.

Only the tiny isolated correction class defined above may be repaired by Codex. Report every such correction with exact diff and resulting SHA. Do not resume Adaptive work unless a later authoritative comment explicitly changes priority.
