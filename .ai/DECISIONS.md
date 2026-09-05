# Decisions

## Communication workflow

- Use one long-lived Draft PR as the Web ChatGPT ↔ Local Codex communication channel.
- Do not create a new PR for each iteration.
- Web ChatGPT posts concrete executable tasks as PR conversation comments.
- Local Codex implements and validates on the same persistent working branch.
- Review the latest relevant diff instead of re-reading the whole repository.
- Merge only when the user explicitly requests it and the intended body of work is complete and validated.

## Implementation / review role split

- Web ChatGPT owns analysis, specification, repository review, acceptance decisions, and the wording of implementation tasks.
- Local Codex owns source-code edits, test edits, generated assets, implementation-time handoff updates, validation, commits, and pushes to `codex/persistent-workspace`.
- This role split is chosen because direct source editing through Web ChatGPT consumes substantially more conversation tokens than delegating coding to Local Codex.
- Therefore Web ChatGPT should normally avoid patching production source code directly. Instead it must post a precise implementation contract in the persistent Draft PR.
- PR implementation instructions should minimize interpretation by Codex and include, when applicable: objective, canonical-spec references, confirmed findings, exact required behavior, target files/symbols, in-scope work, explicit non-goals, error/edge-case behavior, acceptance criteria, required focused/regression tests, and reporting format.
- Local Codex must not silently change product semantics, providers, hydraulic assumptions, public API behavior, or phase boundaries. If a requested implementation conflicts with canonical specifications or requires a new product decision, report `spec-change-required` instead of improvising.
- Local Codex may fix confirmed defects that are clearly inside the active task contract, then run the required validation, update `.ai/HANDOFF.md` when implementation state materially changes, commit, push, and stop for Web ChatGPT review.
- Web ChatGPT reviews the latest relevant commit/diff and evidence. Follow-up fixes are communicated as another precise PR comment rather than by Web ChatGPT directly editing source code.
- This decision supersedes the temporary validation-only Local Codex role used during the end of Phase 2B.

## Specification precedence

1. `docs/PRODUCT_SPEC_DRAFT.md`
2. `docs/specs/v0.1-implementation-spec.md`
3. `docs/specs/v0.1-ui-spec.md`
4. `docs/specs/v0.1-ui-implementation-spec.md`
5. Japanese translations are reference only.

## Implementation status decisions

- SFINCS v2.4.0 Galibier remains the v0.1 hydraulic engine.
- HydroMT-SFINCS 2.0.0rc3 compatibility has been validated for required Phase 0 model forms.
- Phase 1 application skeleton/domain/API is validated.
- Phase 2 is split for reviewability:
  - Phase 2A: GSI / PLATEAU / OSM geographic providers — validated.
  - Phase 2B: CSIS geocoder + packaged JMA rainfall catalog/APIs — validated.
- Phase 3 is now permitted to begin under the canonical implementation specification.
- Phase 3 implementation is delegated to Local Codex under a strict PR task contract written and reviewed by Web ChatGPT.

## Preservation constraints

- Preserve validated Phase 0/1/2A/2B behavior unless the active task explicitly requires change.
- Do not silently substitute providers, hydraulic engines, data semantics, or product assumptions.
- Do not add functionality beyond the active canonical phase without an explicit specification decision.
