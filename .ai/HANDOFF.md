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

Phase 2B was validated by Local Codex against exact commit:

`660579bfebb5f1e275004ed0f1d0a0b4db7cb322`

Final validation evidence:

- focused pytest: PASS — 38 passed, 2 warnings;
- full pytest: PASS — 59 passed, 1 skipped, 2 warnings;
- Ruff: PASS — zero diagnostics / zero `I001` findings;
- mypy: PASS — 22 source files;
- JMA packaged sanity: PASS — 1,286 stations, 60 events, ranks 1..10, durations `{10, 60, 1440}`;
- EOL contract: PASS for `web/index.html`, `web/openapi.json`, `web/src/api/generated.ts`, and `floodsim/static/index.html`;
- frontend `npm ci`, `api:check`, typecheck, lint, Vitest, and Vite build: PASS;
- repository cleanliness after normal Windows build: PASS — `git diff --exit-code`, `git diff --cached --exit-code`, and `git status --short` were clean;
- previous live CSIS/JMA contract smokes remain applicable because the final import/EOL-only fixes did not change provider transport/parser behavior.

Phase 2B implementation includes:

- CSIS Simple Geocoding provider + `/api/v1/geocode`;
- nationwide packaged precipitation-capable JMA station catalog;
- deterministic packaged extreme-rainfall events from fixed official JMA ranking snapshots;
- rainfall station/extreme/event APIs;
- historical-uniform rainfall conversion helper;
- deterministic OpenAPI and generated frontend DTO contracts;
- official-JMA source restrictions and fail-closed ranking-duration validation;
- cross-platform generated-artifact EOL stability.

## Next allowed phase

Phase 3 may now begin under `docs/specs/v0.1-implementation-spec.md` §22.

Web ChatGPT must implement Phase 3. Local Codex must not implement it; Local Codex only runs the exact validation commands requested after Web ChatGPT pushes a Phase 3 implementation commit.

Do not assume Phase 3 scope from memory. Web ChatGPT must read the canonical Phase 3 contract and post a new validation task after implementation.

## Role protocol

### Web ChatGPT

1. Read this handoff and the latest relevant PR discussion.
2. Read the canonical specification for the active phase.
3. Implement required changes directly on `codex/persistent-workspace`.
4. Commit/push the implementation.
5. Post an exact validation request for Local Codex.
6. Review Codex's validation report and decide `validated`, `needs-fix`, `blocked`, or `spec-change-required`.

### Local Codex

1. Fetch the exact commit identified by Web ChatGPT into a clean/disposable validation worktree if requested.
2. Read `.ai/HANDOFF.md`, `.ai/BUG_REPORT.md`, `.ai/DECISIONS.md`, and the latest applicable validation instruction.
3. Run only the requested checks.
4. Report exact commands and `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN`.
5. Include confirmed failures, useful logs, affected files/functions, and clearly labelled hypotheses if needed.
6. Make no repository changes, commits, pushes, branches, PRs, or merges.

Do not infer completion from commit messages alone. Completion requires the active acceptance criteria and validation request to pass.
