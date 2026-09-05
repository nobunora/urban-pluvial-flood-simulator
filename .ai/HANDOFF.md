# Persistent Codex Handoff

## Workspace

- Persistent branch: `codex/persistent-workspace`
- Communication channel: one long-lived GitHub Draft PR targeting `main`
- Web ChatGPT owns implementation and repository writes on this branch.
- Local Codex is validation/reporting only and must not edit, commit, push, create PRs, or merge unless the user explicitly changes that rule.
- Do not open a new PR for each iteration.
- Keep the Draft PR open until the user explicitly requests merge or the persistent workspace is intentionally retired.

## Current repository state

- Phase 0: `validated`
- Phase 1: `validated`
- Phase 2A geographic providers: `validated`
- Phase 2B CSIS/JMA providers and API contracts: `validated`
- Phase 3: backend implementation substantially complete; `needs-fix / revalidation-pending`

Phase 2B was validated by Local Codex against exact implementation commit:

`660579bfebb5f1e275004ed0f1d0a0b4db7cb322`

Phase 3 includes the Full 1 m grid, roof-rain redistribution, rainfall resolution, filesystem run storage, HydroMT-SFINCS regular-grid model builder, local SFINCS engine resolution/runner, NetCDF result reader, normalized results, run coordinator/API, limitations metadata, and deterministic fake-E2E coverage.

The first Phase 3 exact-SHA validation against `473d1e18a485459c75c0c1d64c71480cb989afcc` returned `needs-fix`. Confirmed code-quality findings were addressed by Web ChatGPT, including exception breadth, typing, import ordering, subprocess/return-code handling, and runtime dependency declaration.

A second revalidation against `dee72373a54e7ddfe1c05060523d7e1e785d0ca7` was blocked before the Python gates because `environment.yml` pinned `scipy=1.18.1`, which was not available from conda-forge main on the Windows validation host. That pass also confirmed that `web/openapi.json` and `web/src/api/generated.ts` are stale and omit the Phase 3 run/result routes. Frontend typecheck/lint/test/build otherwise passed, and no source defect was inferred from the blocked Python environment.

Web ChatGPT has since:

- changed the conda SciPy pin to `scipy=1.18.0`, which has a conda-forge win-64 Python 3.12 build;
- changed `web/scripts/api-types.mjs` so an explicit or active conda/virtual environment is preferred over a stale repository `.venv`;
- recorded the stale generated API artifacts as the current confirmed blocking defect.

Revalidation must use the exact PR head named by the latest PR validation comment.

## Phase 3 validation environment

Do not reuse an arbitrary or stale `.venv` for Phase 3 acceptance.

The repository-pinned validation environment is `environment.yml`, which specifies Python 3.12.10, SciPy 1.18.0, and the pinned HydroMT-SFINCS source commit corresponding to `2.0.0rc3`, plus Xarray, NetCDF, platformdirs, Ruff, mypy, pytest, and the required geospatial dependencies.

For validation, create or update an isolated environment from `environment.yml` and run all Python/static/OpenAPI checks through that environment. Verify the installed HydroMT-SFINCS version before claiming Gate A/C PASS.

When invoking the frontend API generator/checker, keep the compliant environment active or set `FLOODSIM_PYTHON` explicitly to that environment's Python executable. The generator must not silently fall back to an unrelated stale `.venv`.

The runtime `requirements.txt` also declares the same pinned HydroMT-SFINCS source dependency so a normal runtime install does not silently omit the model builder dependency.

`SFINCS_BIN` remains an external local-engine requirement. Automatic SFINCS download/redistribution is intentionally prohibited while licensing/bootstrap is unresolved. If no permitted SFINCS 2.4.0 Galibier executable is available, the real-engine gate is `BLOCKED`, not `PASS` and not a reason to skip the other gates.

## Current confirmed Phase 3 blocker

`web/openapi.json` and `web/src/api/generated.ts` are not synchronized with the current FastAPI application. They must be regenerated from the current app using the pinned Python environment and `openapi-typescript`, reviewed by Web ChatGPT, and committed before final Phase 3 validation can pass.

## Remaining Phase 3 gates

1. Exact-SHA clean-worktree validation.
2. Creation of the pinned Python 3.12.10 validation environment from `environment.yml`.
3. Focused Phase 3 pytest and full pytest.
4. Ruff across the requested repository scope and mypy for `floodsim`.
5. Real `hydromt_sfincs==2.0.0rc3` regular 1 m model build using the normalized AEQD Dataset CRS and `precip_2d` component contract.
6. If a permitted `SFINCS_BIN` exists, tiny Full1m execution through real `sfincs_map.nc` read and normalized max-depth output.
7. Regenerate backend OpenAPI and `web/src/api/generated.ts` in a disposable validation worktree, prove `api:check`/frontend checks pass on the generated result, and report the exact generated diff for Web ChatGPT to commit.
8. Final Phase 3 implementation report and handoff disposition after Web ChatGPT reviews the evidence.

## Workflow correction

The earlier temporary instruction `Workflow Override — Codex Owns Implementation` is superseded.

The user identified the actual cause of the unexpectedly high token consumption: Local Codex had been running the Sol model. Local Codex has now been changed to Luna, so the repository returns to the prior workflow in which Web ChatGPT performs source changes and Local Codex performs validation/reporting only.

## Role protocol

### Web ChatGPT

1. Read this handoff and the latest relevant PR discussion.
2. Read the canonical specification for the active phase and inspect only directly relevant repository state.
3. Implement required source/test/generated-asset/documentation changes directly on `codex/persistent-workspace`.
4. Commit and push the implementation.
5. Post an exact validation request naming the commit SHA and required checks.
6. Review Local Codex's validation report and decide `validated`, `needs-fix`, `blocked`, or `spec-change-required`.
7. If validation finds defects, Web ChatGPT implements the correction and requests another validation pass.

### Local Codex

1. Read `.ai/HANDOFF.md`, `.ai/BUG_REPORT.md`, `.ai/DECISIONS.md`, `AGENTS.md`, and the latest applicable validation comment.
2. Fetch/checkout exactly the commit named by Web ChatGPT, preferably in a clean/disposable validation worktree when requested.
3. Run only the requested focused/regression/static/frontend/live checks.
4. Report exact commands and `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN`.
5. Include confirmed failures, useful logs, affected files/functions, and clearly labelled hypotheses when needed.
6. Make no repository changes, commits, pushes, branches, PRs, or merges. Temporary generated files inside a disposable validation worktree are allowed only when the active validation task explicitly requests them; restore or discard them before completing validation.

Do not infer completion from commit messages alone. Completion requires the active acceptance criteria and requested validation to pass.
