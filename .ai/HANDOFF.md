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
- Phase 3 has not been implemented yet.

Phase 2B was validated by Local Codex against exact implementation commit:

`660579bfebb5f1e275004ed0f1d0a0b4db7cb322`

Final validation evidence:

- focused pytest: PASS — 38 passed, 2 warnings;
- full pytest: PASS — 59 passed, 1 skipped, 2 warnings;
- Ruff: PASS — zero diagnostics / zero `I001` findings;
- mypy: PASS — 22 source files;
- JMA packaged sanity: PASS — 1,286 stations, 60 events, ranks 1..10, durations `{10, 60, 1440}`;
- EOL contract: PASS for `web/index.html`, `web/openapi.json`, `web/src/api/generated.ts`, and `floodsim/static/index.html`;
- frontend `npm ci`, `api:check`, typecheck, lint, Vitest, and Vite build: PASS;
- repository cleanliness after normal Windows build: PASS.

## Next allowed phase

Phase 3 may now begin under `docs/specs/v0.1-implementation-spec.md` §22.

Web ChatGPT will implement Phase 3 directly on `codex/persistent-workspace` after reviewing the canonical Phase 3 contract and directly relevant repository state.

Local Codex must not implement Phase 3. It must wait until Web ChatGPT posts a validation request naming an exact commit SHA, then run only the requested checks and report results.

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
6. Make no repository changes, commits, pushes, branches, PRs, or merges.

Do not infer completion from commit messages alone. Completion requires the active acceptance criteria and requested validation to pass.
