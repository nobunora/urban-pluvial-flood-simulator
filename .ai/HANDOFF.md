# Persistent Codex Handoff

## Workspace

- Persistent branch: `codex/persistent-workspace`
- Communication channel: one long-lived GitHub Draft PR targeting `main`
- Web ChatGPT owns analysis, specification, review, acceptance decisions, and PR task wording.
- Local Codex owns implementation, source/test/generated-asset edits, validation, commits, and pushes to the persistent branch.
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

Phase 3 implementation is delegated to Local Codex. Web ChatGPT must first read the canonical Phase 3 contract and post a precise `## Codex Task` comment in PR #12. Codex must implement only that contract, run the required tests, push to `codex/persistent-workspace`, and stop for review.

Do not assume Phase 3 scope from memory. The latest applicable PR task comment plus canonical specifications define the executable contract.

## Why implementation is delegated to Codex

Direct source-level editing through Web ChatGPT was found to consume substantially more conversation tokens. To keep the workflow efficient, Web ChatGPT should normally not patch production source code itself. Instead it should spend tokens on high-value analysis, specification, review, and very explicit PR instructions, while Local Codex performs the code changes and local validation.

## Role protocol

### Web ChatGPT

1. Read this handoff and the latest relevant PR discussion.
2. Read the canonical specification for the active phase and inspect only the directly relevant repository state.
3. Post a strict implementation contract to PR #12. Include objective, confirmed findings, exact required behavior, target files/symbols when known, scope boundaries, explicit non-goals, acceptance criteria, required tests, and reporting format.
4. Do not normally edit production source code directly.
5. After Codex pushes, review the latest relevant commit/diff and validation evidence.
6. If corrections are needed, post another precise PR comment; do not patch source directly unless the user explicitly changes this workflow or an exceptional repository-control fix is required.
7. Decide `validated`, `needs-fix`, `blocked`, or `spec-change-required` from evidence.

### Local Codex

1. Read `.ai/HANDOFF.md`, `.ai/BUG_REPORT.md`, `.ai/DECISIONS.md`, `AGENTS.md`, and the latest applicable PR task comment.
2. Inspect only the repository areas needed to execute that contract.
3. Implement the requested code/test/generated-asset changes on `codex/persistent-workspace`.
4. Preserve validated Phase 0/1/2A/2B behavior unless explicitly authorized otherwise.
5. If the task conflicts with canonical specifications or requires a product/architecture decision not already made, stop and report `spec-change-required` with evidence.
6. Run focused tests first, then all required regression/static/frontend/live checks specified by the task.
7. Update `.ai/HANDOFF.md` when implementation state materially changes; update `.ai/BUG_REPORT.md` or `.ai/DECISIONS.md` only when their documented criteria are met.
8. Commit and push to `codex/persistent-workspace`.
9. Report the exact commit SHA, changed files, implementation summary, exact checks/results, remaining risks/blockers, and disposition recommendation.
10. Stop for Web ChatGPT review. Do not begin the next phase independently and do not merge PR #12.

Do not infer completion from commit messages alone. Completion requires the active acceptance criteria and validation request to pass.
