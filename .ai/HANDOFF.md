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
- Phase 2B: `validation-pending` after Web ChatGPT implemented the remaining review fixes and additional generator-contract hardening.
- Phase 2B first review-fix implementation commit: `a332b54ac2c00a3cb03ca7c0a72ba6d1ba81b318`.
- Web ChatGPT corrected the canonical station-search semantics, JMA top-ten parsing, event station coordinates, event/catalog cross-validation, packaged event coverage, generator behavior, API event typing, tests, snapshot documentation, Phase 2B report, OpenAPI JSON, and generated TypeScript DTOs.
- A later audit found two additional Phase 2B generator gaps: arbitrary HTTPS provenance/source URLs were accepted, and a missing required rainfall-duration row could silently produce a partial catalog. Web ChatGPT fixed both and added `tests/test_phase2b_generator_contracts.py`.
- Phase 3+ has not been implemented.

## Current work boundary

The active implementation boundary remains Phase 2B only:

- CSIS geocoder provider + API contract;
- packaged JMA station/extreme-event catalog and rainfall catalog APIs;
- deterministic fixture/snapshot parsing, validation, provenance, and generated API contracts;
- no simulation orchestration, Full 1 m production flow, Adaptive, result UI, or packaging.

Current JMA event/generator semantics:

- nearest-station search considers all 1,286 packaged precipitation-capable stations;
- a station may return an empty extremes list when its ranking events are not packaged;
- the two fixed ranking snapshots each contribute 30 events: 10-minute, 1-hour, and daily rainfall × ranks 1..10;
- the statistics-period column is never parsed as rank 11;
- each event carries station coordinates and they must match the station catalog;
- fixed snapshot generation must reproduce both committed catalog JSON documents exactly as parsed JSON content;
- maintenance generation accepts only official HTTPS `jma.go.jp` hosts for recorded/fetched station and ranking sources;
- every ranking source must expose recognized 10-minute, 1-hour, and daily rainfall rows or catalog generation fails explicitly.

Generated API artifacts remain:

- `web/openapi.json`
- `web/src/api/generated.ts`

Local Codex must now validate the exact branch head identified in the latest PR validation comment. Do not start Phase 3 until that validation passes and Web ChatGPT explicitly changes Phase 2B to `validated`.

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
