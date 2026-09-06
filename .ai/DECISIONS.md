# Decisions

## Communication workflow

- Use one long-lived Draft PR as the Web ChatGPT ↔ Local Codex communication channel.
- Do not create a new PR for each iteration.
- Web ChatGPT may post implementation/review/validation instructions as PR conversation comments.
- Review the latest relevant diff instead of re-reading the whole repository.
- Merge only when the user explicitly requests it and the intended body of work is complete and validated.

## Implementation / validation role split

- **Web ChatGPT is the primary implementation owner** for source, tests, generated assets, documentation, handoff files, commits, and pushes to `codex/persistent-workspace`.
- **Local Codex (Luna) is primarily an audit / execution / validation / defect-investigation agent.** It should spend most of its work on reproducing runtime behavior, running focused/full checks, inspecting upstream contracts, and reporting root causes.
- Local Codex may make only **small, local, non-architectural corrections** discovered while validating, such as an obvious typo/import/test-fixture/formatting correction that does not change a public contract, algorithm, dependency choice, generated API surface, or phase scope.
- Any substantive feature implementation, algorithm change, compatibility adapter, public/API contract change, dependency change, generated-asset regeneration, or multi-file behavioral repair remains Web ChatGPT-owned.
- If a tiny Codex correction is made, it must be isolated, explicitly reported, and independently reviewable; Codex must not use that allowance to take over implementation.
- Local Codex must not create a new PR, merge, or broaden scope unless the user explicitly authorizes it.
- After Web ChatGPT pushes a substantive commit, Local Codex runs the requested checks against the exact named commit and reports `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN` with useful diagnostics.
- This decision supersedes the earlier stricter validation-only rule and the much older `Workflow Override — Codex Owns Implementation` rule. Web ChatGPT remains the normal coding path; the user explicitly allowed only minor Codex fixes while keeping validation/execution as Codex's main role.

## Specification precedence

1. `docs/PRODUCT_SPEC_DRAFT.md`
2. `docs/specs/v0.1-implementation-spec.md`
3. `docs/specs/v0.1-ui-spec.md`
4. `docs/specs/v0.1-ui-implementation-spec.md`
5. Japanese translations are reference only.

## Implementation status decisions

- SFINCS v2.4.0 Galibier remains the v0.1 hydraulic engine.
- HydroMT-SFINCS 2.0.0rc3 remains exactly pinned for v0.1 compatibility work.
- Phase 1 application skeleton/domain/API is validated.
- Phase 2 is split for reviewability:
  - Phase 2A: GSI / PLATEAU / OSM geographic providers — validated.
  - Phase 2B: CSIS geocoder + packaged JMA rainfall catalog/APIs — validated.
- Phase 3 implementation is validated at `62dc85fa163587ea73a875c59067bcd5a8dfe79a`; only the external real-SFINCS executable smoke remains blocked when no permitted engine is installed.
- Phase 4 Adaptive implementation is in progress. Adaptive must remain disabled until classifier, quadtree/subgrid, result normalization, and Full-vs-Adaptive acceptance gates are validated.

## Adaptive implementation interpretations

- The §12.2 `within 2 m` building/road buffer is evaluated in projected metric space against the normalized 1 m source-cell footprints. Direct feature cells remain 1 m; buffer cells may be 1 m or 2 m but must never be coarser than 2 m.
- §12.3 requires curvature, local depression/ridge connectivity evidence, and flow-accumulation concentration evidence to be computed for candidate blocks. The specification does not define numeric coarsening thresholds for those three indicators, so the implementation must not invent new gating thresholds without a specification decision.
- Threshold configuration identity must identify the actual threshold values, not only the algorithm family name.
- Authority-less local AEQD CRS semantics must be preserved for Adaptive. A fake permanent EPSG is prohibited.

## Preservation constraints

- Preserve validated Phase 0/1/2A/2B/3 behavior unless the active task explicitly requires change.
- Do not silently substitute providers, hydraulic engines, data semantics, CRS semantics, or product assumptions.
- Do not add functionality beyond the active canonical phase without an explicit specification decision.
