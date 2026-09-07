# Decisions

## Communication workflow

- Use one long-lived Draft PR as the Web ChatGPT ↔ Local Codex communication channel.
- Do not create a new PR for each iteration.
- Web ChatGPT may post implementation/review/validation instructions as PR conversation comments.
- Review the latest relevant diff instead of re-reading the whole repository.
- Merge only when the user explicitly requests it and the intended body of work is complete and validated.

## Implementation / validation role split

- Web ChatGPT is the primary implementation owner for substantive source, tests, generated assets, documentation, handoff files, commits, and pushes to `codex/persistent-workspace`.
- Local Codex (Luna) is primarily responsible for validation, execution tests, runtime diagnostics, upstream-contract investigation, and defect reporting.
- Local Codex may make only very small, isolated, non-architectural corrections discovered during validation, such as an obvious typo/import/test-fixture/formatting correction.
- Local Codex must not implement or redesign algorithms, compatibility adapters, public/API behavior, dependencies, generated assets, or multi-file behavioral fixes unless the user explicitly expands that permission.
- Any tiny Codex correction must be isolated in a minimal commit and reported with exact diff/reason.
- After Web ChatGPT pushes a substantive implementation commit, Local Codex runs the requested checks against the exact named commit and reports `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN` with useful diagnostics.
- Confirmed defects requiring substantive changes return to Web ChatGPT for implementation.
- This decision supersedes earlier workflow text assigning primary implementation to Local Codex.

## Specification precedence

1. `docs/PRODUCT_SPEC_DRAFT.md`
2. `docs/specs/v0.1-implementation-spec.md`
3. `docs/specs/v0.1-ui-spec.md`
4. `docs/specs/v0.1-ui-implementation-spec.md`
5. Japanese translations are reference only.

## Implementation status decisions

- SFINCS v2.4.0 Galibier remains the v0.1 hydraulic engine.
- HydroMT-SFINCS 2.0.0rc3 remains pinned to source commit `82e58ee85136cf5155c92b42bb9a397869ed8035`.
- Phase 0, Phase 1, Phase 2A, and Phase 2B are validated.
- Phase 3 implementation is validated at `62dc85fa163587ea73a875c59067bcd5a8dfe79a`; real SFINCS execution remains externally blocked if no permitted executable is available.
- Phase 4 is implementation-in-progress. Adaptive stays disabled until quadtree/subgrid construction, result normalization, benchmark acceptance, and required engine validation are complete.
- The authority-less local AEQD CRS is canonical. Do not substitute a fake permanent EPSG.
- Runtime evidence supports a repository-owned, quadtree-only compatibility seam for pinned rc3 that preserves full WKT/CF/UGRID metadata and omits only invalid optional `epsg=None` / `epsg_code="EPSG:None"` metadata.

## Preservation constraints

- Preserve validated Phase 0/1/2A/2B/3 behavior unless the active task explicitly requires change.
- Do not silently substitute providers, hydraulic engines, data semantics, CRS semantics, or product assumptions.
- Do not enable Adaptive before its canonical acceptance gates are met.
