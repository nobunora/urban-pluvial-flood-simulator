# Decisions

## Communication workflow

- Use one long-lived Draft PR as the Web ChatGPT ↔ Local Codex communication channel.
- Do not create a new PR for each iteration.
- Web ChatGPT posts concrete executable tasks as PR conversation comments.
- Local Codex pushes commits to the same working branch.
- Review the latest relevant diff instead of re-reading the whole repository.
- Merge only when the full assigned task is complete and validation passes.

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
- Phase 2 is intentionally split for reviewability:
  - Phase 2A: GSI / PLATEAU / OSM geographic providers — validated.
  - Phase 2B: CSIS geocoder + packaged JMA rainfall catalog/APIs.
- Phase 3 may not start until Phase 2B review is complete and the persistent workflow explicitly authorizes it.

## Preservation constraints

- Preserve existing validated Phase 0/1/2A behavior unless the active task explicitly requires change.
- Do not silently substitute providers, hydraulic engines, data semantics, or product assumptions.
- Do not add Phase 3+ functionality while implementing Phase 2B.
