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
- Latest completed implementation: GSI / PLATEAU / OSM application provider integration, including arbitrary rectangles and typed fallback/provenance behavior.
- Phase 2B has not been implemented.
- Phase 3+ has not been implemented.

## Current work boundary

The next implementation work is Phase 2B only:

- CSIS geocoder provider + API contract;
- packaged JMA station/extreme-event catalog and rainfall catalog APIs;
- deterministic fixture-based parsing / validation / provenance;
- no simulation orchestration, Full 1 m production flow, Adaptive, result UI, or packaging.

The exact task instructions are supplied in the Draft PR conversation, not by creating a new instruction commit for every iteration.

## Review protocol

After each Local Codex push:

1. Read this handoff file.
2. Read `.ai/BUG_REPORT.md` and `.ai/DECISIONS.md`.
3. Review the latest relevant commit/diff only.
4. Run or verify only the focused tests needed for the current task, then the required regression gates.
5. Update this handoff file when the implementation state materially changes.

Do not infer completion from commit messages alone. Completion requires the acceptance criteria in the active PR task comment to pass.
