# Persistent Codex Handoff

## Workspace

- Persistent branch: `codex/persistent-workspace`
- Communication channel: one long-lived GitHub Draft PR targeting `main`
- Web ChatGPT owns implementation and repository writes on this branch.
- Local Codex is audit/validation/execution/diagnostics/reporting only and must not edit, commit, push, create PRs, or merge unless the user explicitly changes that rule.
- Do not open a new PR for each iteration.
- Keep the Draft PR open until the user explicitly requests merge or the persistent workspace is intentionally retired.

## Current repository state

- Phase 0: `validated`
- Phase 1: `validated`
- Phase 2A geographic providers: `validated`
- Phase 2B CSIS/JMA providers and API contracts: `validated`
- Phase 3: backend implementation substantially complete; Web fixes applied; `exact-head audit/revalidation pending`

Phase 2B was validated by Local Codex against exact implementation commit:

`660579bfebb5f1e275004ed0f1d0a0b4db7cb322`

Phase 3 includes the Full 1 m grid, roof-rain redistribution, rainfall resolution, filesystem run storage, HydroMT-SFINCS regular-grid model builder, local SFINCS engine resolution/runner, NetCDF result reader, normalized results, run coordinator/API, limitations metadata, and deterministic fake-E2E coverage.

## Phase 3 validation history

The first Phase 3 exact-SHA validation against `473d1e18a485459c75c0c1d64c71480cb989afcc` returned `needs-fix`. Confirmed code-quality findings were addressed by Web ChatGPT, including exception breadth, typing, import ordering, subprocess/return-code handling, and runtime dependency declaration.

A second revalidation against `dee72373a54e7ddfe1c05060523d7e1e785d0ca7` was blocked before the Python gates because `environment.yml` pinned `scipy=1.18.1`, which was not available from conda-forge main on the Windows validation host. That pass also confirmed that `web/openapi.json` and `web/src/api/generated.ts` were stale and omitted the Phase 3 run/result routes. Frontend typecheck/lint/test/build otherwise passed, and no source defect was inferred from the blocked Python environment.

Web ChatGPT then:

- changed the conda SciPy pin to `scipy=1.18.0` while retaining Python 3.12.10 and the rest of the pinned validation stack;
- changed `web/scripts/api-types.mjs` so an explicit or active conda/virtual environment is preferred over a stale repository `.venv`;
- regenerated and committed `web/openapi.json` and `web/src/api/generated.ts` from the current FastAPI application using Python 3.12.10, repository runtime requirements, Node 22, `npm ci`, `npm run api:generate`, and `npm run api:check`;
- verified that the generated OpenAPI and TypeScript contain `/api/v1/estimate`, `/api/v1/runs`, `/api/v1/runs/{run_id}`, `/api/v1/runs/{run_id}/cancel`, `/api/v1/runs/{run_id}/events`, and `/api/v1/runs/{run_id}/result-metadata`;
- removed the temporary generation helper after the canonical artifacts were committed.

Generated artifact SHA-256 values at canonical regeneration:

- `web/openapi.json`: `b9036afa1e1b864e60f4aeb6b2bbb8883c7fc28308fe8e2eb873cdcb970adb79`
- `web/src/api/generated.ts`: `48b3728d9d8e664f46a5a716c6118732315801707526f42cf0ef8362ed9d0e94`

The third exact-head acceptance pass against `0c114e4c462bada39a9aaf89bb0448c119d9a29f` used a fresh compliant Python 3.12.10 environment with the pinned HydroMT-SFINCS 2.0.0rc3 source commit. Results were:

- Gate A exact SHA/environment: `PASS`;
- Gate B pytest/Ruff/mypy: `FAIL`;
- Gate C real HydroMT-SFINCS build: `FAIL`;
- Gate D real SFINCS Full1m smoke: `BLOCKED` because no permitted local SFINCS executable was available;
- Gate E committed OpenAPI/frontend: `PASS`;
- Gate F invariants: `FAIL` due to the confirmed Gate B/C defects.

The confirmed repository findings from that pass were:

1. run mutation `Content-Type: text/plain` returned 400 instead of the intended 415 because FastAPI body parsing occurred before the endpoint-level media-type guard;
2. two older regression tests used exact OpenAPI path-set equality and therefore rejected legitimate Phase 3 routes;
3. Ruff reported seven diagnostics, including one intentional broad exception at the top-level background-run boundary;
4. mypy reported the untyped third-party `hydromt_sfincs` import;
5. the real rc3 model build retained temporary `grid.epsg=4326`, so `model.grid.crs` resolved to EPSG:4326 even though the Dataset carried the correct local AEQD CRS.

Web ChatGPT has applied the fixes for all confirmed repository findings:

- the runs router now performs JSON media-type enforcement in a custom `APIRoute` before FastAPI body parsing;
- Phase 2 regression tests now assert their required paths are a subset, preserving forward compatibility while still protecting Phase 2 contracts;
- the HydroMT rc3 builder now synchronizes the normalized AEQD Dataset CRS with `model.grid.epsg=None`, `config.epsg=None`, and the correct `crsgeo` value before asserting `model.grid.crs` and writing the model;
- the untyped rc3 import has a narrowly scoped mypy ignore;
- all seven reported Ruff findings were addressed with semantic-preserving changes; the broad worker-boundary exception is locally documented and suppressed only at that boundary;
- an accidental oversized edit to `run_coordinator.py` made during the Web repair was detected immediately and fully restored to the previous validated blob before applying only the intended two-line lint annotation.

These Web fixes are **not yet accepted**. Local Codex must audit and execute the exact PR head named by the latest PR validation comment and investigate any remaining defect without modifying the repository.

## Phase 3 validation environment

Do not reuse an arbitrary or stale `.venv` for Phase 3 acceptance.

The repository-pinned validation environment is `environment.yml`, which specifies Python 3.12.10, SciPy 1.18.0, and the pinned HydroMT-SFINCS source commit corresponding to `2.0.0rc3`, plus Xarray, NetCDF, platformdirs, Ruff, mypy, pytest, and the required geospatial dependencies.

For validation, create or verify an isolated environment from `environment.yml` and run all Python/static/OpenAPI checks through that environment. Verify the installed HydroMT-SFINCS version/source commit before claiming Gate A/C PASS.

When invoking frontend API tooling, keep the compliant environment active or set `FLOODSIM_PYTHON` explicitly to that environment's Python executable. The generator must not silently fall back to an unrelated stale `.venv`.

The runtime `requirements.txt` also declares the same pinned HydroMT-SFINCS source dependency so a normal runtime install does not silently omit the model builder dependency.

`SFINCS_BIN` remains an external local-engine requirement. Automatic SFINCS download/redistribution is intentionally prohibited while licensing/bootstrap is unresolved. If no permitted SFINCS 2.4.0 Galibier executable is available, the real-engine gate is `BLOCKED`, not `PASS`, and it must not prevent the other gates from running.

## Current confirmed Phase 3 blockers

No currently known repository defect remains after the Web fixes, but this is not an acceptance claim. Exact-head Codex audit/revalidation is required. A missing permitted SFINCS executable may externally block only the real-engine smoke gate.

## Remaining Phase 3 gates

1. Exact-SHA clean-worktree audit against the SHA in the latest PR validation comment.
2. Verify the pinned Python 3.12.10 environment and package/source versions.
3. Focused Phase 3 pytest and full pytest.
4. Ruff across `floodsim tests scripts` and mypy for `floodsim`.
5. Audit the Web changes for unintended semantic regressions, especially the pre-body JSON route guard and the HydroMT rc3 CRS ownership fix.
6. Real `hydromt_sfincs==2.0.0rc3` regular 1 m model build using normalized AEQD CRS and `precip_2d`; verify Dataset CRS, `grid.epsg`, config EPSG/`crsgeo`, generated SFINCS input, model write, mask/Manning, rainfall mass conservation, and build report.
7. If a permitted `SFINCS_BIN` exists, execute tiny Full1m through real `sfincs_map.nc` read and normalized max-depth output; otherwise report only that gate as `BLOCKED`.
8. Prove committed OpenAPI/generated TypeScript remain synchronized with `npm run api:check`, then frontend typecheck/lint/test/build.
9. Investigate every failure to root cause and report exact command, file/line/symbol, minimal reproduction, logs, and whether it is a confirmed repository defect, external blocker, or hypothesis. Do not fix it locally.
10. Final Phase 3 implementation report and durable disposition only after Web ChatGPT reviews the exact-head audit evidence.

## Workflow correction

The earlier temporary instruction `Workflow Override — Codex Owns Implementation` is superseded.

The user identified the actual cause of the unexpectedly high token consumption: Local Codex had been running the Sol model. Local Codex has now been changed to Luna, so the repository uses the workflow in which Web ChatGPT performs all source changes and Local Codex performs audit/validation/execution/diagnostics only.

## Role protocol

### Web ChatGPT

1. Read this handoff and the latest relevant PR discussion.
2. Read the canonical specification for the active phase and inspect only directly relevant repository state.
3. Implement required source/test/generated-asset/documentation changes directly on `codex/persistent-workspace`.
4. Commit and push the implementation.
5. Post an exact-SHA audit/validation request naming the required checks and runtime investigation scope.
6. Review Local Codex's report and decide `validated`, `needs-fix`, `blocked`, or `spec-change-required`.
7. If validation finds defects, Web ChatGPT implements the correction and requests another audit pass.

### Local Codex

1. Read `.ai/HANDOFF.md`, `.ai/BUG_REPORT.md`, `.ai/DECISIONS.md`, `AGENTS.md`, and the latest applicable PR audit comment.
2. Fetch/checkout exactly the commit named by Web ChatGPT, preferably in a clean/disposable validation worktree.
3. Audit source changes, execute the requested focused/regression/static/frontend/live checks, and investigate failures to root cause.
4. Report exact commands and `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN` with useful diagnostics.
5. Separate confirmed defects, external/environment blockers, warnings, and hypotheses.
6. Make no repository changes, commits, pushes, branches, PRs, or merges. Temporary generated files in a disposable validation worktree are allowed only when explicitly requested and must be discarded before completion.

Do not infer completion from commit messages alone. Completion requires the active acceptance criteria and requested audit/validation to pass.
