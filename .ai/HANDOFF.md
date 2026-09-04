# Persistent Codex Handoff

## Workspace

- Persistent branch: `codex/persistent-workspace`
- Communication channel: one long-lived GitHub Draft PR targeting `main`
- Web ChatGPT instructions are posted as PR conversation comments.
- Web ChatGPT owns implementation and repository writes on this branch.
- Local Codex is validation/reporting only and must not edit, commit, push, create PRs, or merge unless the user explicitly changes that rule.
- Do not open a new PR for each iteration.
- Do not merge the Draft PR until the full assigned task is complete and validation has passed.

## Current repository state

- Phase 0: `validated`
- Phase 1: `validated`
- Phase 2A geographic providers: `validated`
- Phase 2B: `review-pending`.
- Phase 2B first review-fix implementation commit: `a332b54ac2c00a3cb03ca7c0a72ba6d1ba81b318`.
- Web ChatGPT has taken over implementation for the remaining Phase 2B review fixes.
- Latest completed implementation before that handoff: Phase 2B plus reproducible JMA snapshots, event-backed station search, strict catalog validation, shared CSIS network policy, and canonical `/api/v1` request-validation errors.
- Phase 3+ has not been implemented.

## Current work boundary

The active implementation boundary remains Phase 2B only:

- CSIS geocoder provider + API contract;
- packaged JMA station/extreme-event catalog and rainfall catalog APIs;
- deterministic fixture-based parsing / validation / provenance;
- no simulation orchestration, Full 1 m production flow, Adaptive, result UI, or packaging.

Validation evidence is recorded in `docs/implementation/v0.1-phase2b-report.md`.
The first review-fix round reported focused checks passing (30 tests), full Python regression passing (51 passed, 1 skipped), and Ruff, mypy, and frontend generation/type/lint/test/build gates passing. Import Linter, ty, and deptry were not installed in the project environment; Import Linter also had no repository configuration.

Do not start Phase 3 until Web ChatGPT finishes the remaining Phase 2B fixes, Local Codex validates the exact resulting commit, and Web ChatGPT explicitly marks Phase 2B validated.

## Role protocol

### Web ChatGPT

1. Read this handoff and the latest relevant PR discussion.
2. Review the latest relevant diff and canonical specs.
3. Implement required changes directly on `codex/persistent-workspace`.
4. Commit/push the implementation.
5. Post an exact validation request for Local Codex.
6. Review Codex's validation report and decide `validated`, `needs-fix`, `blocked`, or `spec-change-required`.

### Local Codex

1. Fetch/pull the exact commit identified by Web ChatGPT.
2. Read `.ai/HANDOFF.md`, `.ai/BUG_REPORT.md`, `.ai/DECISIONS.md`, and the latest applicable validation instruction.
3. Run only the requested focused/regression/static/frontend/live checks.
4. Report exact commands and `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN`.
5. Include confirmed failures, useful logs, affected files/functions, and clearly labelled hypotheses if needed.
6. Make no repository changes and stop for Web ChatGPT review.

Do not infer completion from commit messages alone. Completion requires the active acceptance criteria and validation request to pass.
