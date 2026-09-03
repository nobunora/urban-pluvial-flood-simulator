# Persistent Codex Handoff

## Workspace

- Persistent branch: `codex/persistent-workspace`
- Communication channel: one long-lived GitHub Draft PR targeting `main`
- Web ChatGPT instructions are posted as PR conversation comments.
- Local Codex pushes implementation commits to this same branch.
- Do not open a new PR for each iteration.
- Do not merge the Draft PR until the full assigned task is complete and validation has passed.

## Current repository state

- Phase 0: `validated`
- Phase 1: `validated`
- Phase 2A geographic providers: `validated`
- Phase 2B: `review-pending`; review fixes pass locally and await Draft PR #12 review.
- Phase 2B review-fix implementation commit: `a332b54ac2c00a3cb03ca7c0a72ba6d1ba81b318`.
- Latest completed implementation: Phase 2B plus reproducible JMA snapshots,
  event-backed station search, strict catalog validation, shared CSIS network
  policy, and canonical `/api/v1` request-validation errors.
- Phase 3+ has not been implemented.

## Current work boundary

The completed implementation boundary was Phase 2B only:

- CSIS geocoder provider + API contract;
- packaged JMA station/extreme-event catalog and rainfall catalog APIs;
- deterministic fixture-based parsing / validation / provenance;
- no simulation orchestration, Full 1 m production flow, Adaptive, result UI, or packaging.

Validation evidence is recorded in `docs/implementation/v0.1-phase2b-report.md`.
Focused checks pass (30 tests); full Python regression passes (51 passed,
1 skipped); Ruff, mypy, and all frontend generation/type/lint/test/build gates
pass. Import Linter, ty, and deptry are not installed in the project environment;
Import Linter also has no repository configuration.
Do not start Phase 3 until the Phase 2B Draft PR review is complete and the
persistent workflow explicitly authorizes the next phase.

The exact task instructions are supplied in the Draft PR conversation, not by creating a new instruction commit for every iteration.

## Review protocol

After each Local Codex push:

1. Read this handoff file.
2. Read `.ai/BUG_REPORT.md` and `.ai/DECISIONS.md`.
3. Review the latest relevant commit/diff only.
4. Run or verify only the focused tests needed for the current task, then the required regression gates.
5. Update this handoff file when the implementation state materially changes.

Do not infer completion from commit messages alone. Completion requires the acceptance criteria in the active PR task comment to pass.
