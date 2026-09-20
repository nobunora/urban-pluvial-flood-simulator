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

Review scope:

- location / area / rainfall input;
- Full 1 m resource estimate;
- run creation;
- visible run stages;
- cancellation;
- honest provider/engine failure state;
- real tiny Full 1 m execution when providers and the permitted SFINCS executable are available.

Deferred until user review:

- Adaptive enablement;
- Adaptive subgrid/forcing/result normalization;
- Full-vs-Adaptive benchmark acceptance;
- final result-map UX;
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

## Current local-review status

Latest Windows validation on `017d3c0686490acfc55d20906d22434fd8c5de7e` proved the finalized result-reader policies against the previous real SFINCS artifact:

- previous `sfincs_map.nc` reader + normalizer: PASS;
- raw minimum active depth: -0.0016127867 m;
- one near-zero negative depth value clipped and audited;
- 129,934 missing active `hmax` cells reconstructed;
- normalized global max depth: 1.7509006262 m.

A fresh Tokyo Station Full 1 m run then exposed a new repository failure:

- vector acquisition improved from the former 89.349 s to 24.411 s;
- PLATEAU completed; OSM fallback was not used;
- run advanced through rainfall/terrain/roof stages;
- `BUILDING_GRID` failed immediately with generic `INTERNAL_RUN_FAILED`;
- no model/SFINCS files were created;
- the old manifest contract discarded the underlying exception type/message.

Web has now addressed every repository-side issue that can be fixed without the missing host exception:

- manifest persists `failure_exception_type`, `failure_message`, and `failure_diagnostic_file`;
- every unexpected worker failure writes `logs/failure_diagnostic.json` with stage, exception, traceback, elevation shape/range and vector provider/counts;
- Full 1 m vector rasterization now skips ragged, non-numeric, non-finite and invalid individual geometry features rather than letting one malformed feature abort the grid;
- `scripts/diagnose_grid_run.py <run-id>` replays only BUILDING_GRID from an existing run's persisted config/source refs plus the normal elevation cache, avoiding another vector/SFINCS cycle while isolating the grid defect.

The next Codex cycle must first replay the previous failed run `f2dc662c-f445-4f6d-af75-223bb8c2f16c` with the diagnostic script. If it now passes, continue directly to one fresh end-to-end run. If it still fails, the new diagnostic contains the exact root cause; a tiny mechanical fix may be applied in the same cycle when permitted.

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
