# Decisions

## Communication workflow

- Use one long-lived Draft PR as the Web ChatGPT ↔ Local Codex communication channel.
- Do not create a new PR for each iteration.
- Merge only when the user explicitly requests it and the intended body of work is complete and validated.
- The newest top-level PR comment explicitly marked authoritative is the only active exact-SHA Codex instruction. Older task comments are historical evidence only.

## Implementation / validation role split

- **Web ChatGPT is the primary implementation owner** for source, tests, docs, configuration, workflows, generated assets, dependencies and API/UI contracts.
- **Local Codex/Luna is primarily host-local validation/execution** for the user's Windows host, existing SFINCS executable, real processes, local filesystem and external-provider access.
- To reduce unnecessary round trips, Codex may commit/push a tiny isolated mechanical correction found during validation (normally one file, at most two) when behavior is unambiguous and the change is limited to formatting/import/typo/quoting/path/test-fixture/launcher-glue.
- Codex must not use that allowance for algorithms, hydraulic semantics, public APIs, dependencies, generated contracts/assets, specifications, architecture, multi-file behavioral changes or Adaptive behavior.
- Before any tiny-fix push, Codex must verify the remote persistent branch still equals the task SHA; after the fix it must report exact diff/reason/new SHA and rerun the affected check.
- Substantive defects return to Web ChatGPT.

## Review-first delivery decision

- A runnable local user-review slice takes priority over completing the entire v0.1 implementation before user feedback.
- The current review slice is **Full 1 m only**.
- Adaptive remains disabled until later acceptance work.
- The review gate covers condition input, resource estimate, Full 1 m run creation, visible run stages, cancellation and explicit limitations.
- A real SFINCS Full 1 m smoke must use only an already-permitted local executable.
- Provider or engine outages must be reported at the real stopping stage; the UI must never fake completion.

## Result-view implementation decision

- The canonical product and UI specifications explicitly make geographic result visualization part of the v0.1 end-to-end flow.
- After the Full 1 m execution path reached `COMPLETE` on Windows, the user explicitly directed implementation to proceed to the next documented phase.
- Implement result visualization before resuming Adaptive.
- Backend-rendered PNG remains the numerical/color authority; frontend MUST NOT reclassify depth values from the PNG.
- MapLibre image sources place result PNGs on exact backend metadata bounds over the GSI standard raster base map.
- Native point inspection comes from the backend inspection endpoint, not display-image sampling.
- Initial result-view implementation includes max depth, time-depth, grid-resolution, actual-index timeline, provenance and backend limitations.
- Rainbow depth mode remains deferred until the backend provides an explicit canonical palette/legend contract; do not invent a competing frontend scalar mapping.

## Generated frontend artifact workflow decision

- Committed generated OpenAPI types and `package-lock.json` remain part of the repository contract.
- Do not use a pull-request workflow that commits/pushes regenerated artifacts with the default GitHub Actions token.
- A bot-authored push can suppress or require action for downstream pull-request workflows and creates a recursive validation ownership loop.
- Web ChatGPT owns intentional generated-artifact updates; deterministic CI owns drift detection through `npm run api:check`.
- CI must validate the exact PR head without mutating it.

## Canonical environment decision

- `environment.yml` is the sole canonical Python environment for local review and validation.
- The required interpreter is Python 3.12.10 with the versions pinned in that file.
- `requirements.txt` remains useful for legacy/reference workflows but is **not** sufficient evidence that the review environment is canonical.
- `scripts/bootstrap_local_review.py` is the supported helper to create/update the canonical conda-compatible environment.
- `scripts/run_local_review.py --check-env` is the required preflight.
- The launcher must fail clearly before application imports/startup when the canonical environment is not active.
- Node.js >=22.12 is required for a normal frontend rebuild; Node.js 24 is supported.

## Review-path provider latency decision

- PLATEAU remains preferred for building/road vectors.
- A local review run must not wait indefinitely on PLATEAU CityGML acquisition.
- The review coordinator uses a 20-second total PLATEAU budget, then the existing disclosed OSM fallback.
- OSM fallback uses a 30-second budget.
- Provider retry timeouts honor the same monotonic deadline; PLATEAU file streaming is interruptible at the budget boundary.
- Cancellation must suppress fallback and remain terminal/idempotent.
- These are review-path reliability limits, not permission to silently change provider provenance or hydraulic semantics.

## Real SFINCS result-read decision

- A completed regular-grid SFINCS run is not invalid merely because active `hmax` entries are NaN when the corresponding active `h` time series is finite.
- For active cells with no finite `hmax` sample, reconstruct maximum depth from the finite `h` time outputs available in the same NetCDF.
- Preserve finite SFINCS `hmax` values where present.
- Infinite active `hmax`, non-finite active `h`, non-finite active terrain, materially negative depth, inconsistent dimensions, or unreadable NetCDF remain hard `RESULT_INVALID` failures.
- Record the count of reconstructed `hmax` cells in normalized result metadata so the fallback is explicit and auditable.

## SFINCS dry-depth normalization decision

- SFINCS 2.4.0 documents `twet_threshold=0.01 m` as the default water-depth threshold for counting a cell as flooded/wet.
- Use that same 0.01 m band only as a **dry-output normalization tolerance** for finite negative regular-grid water-depth samples.
- Finite active `h` or derived max-depth values in `[-0.01, 0)` are clipped to exactly zero before normalized product output.
- Any value below `-0.01 m` remains a hard `RESULT_INVALID` failure.
- This policy is not a claim that negative water depth is physically meaningful and is not derived from `huthresh`; it is a boundary normalization aligned with SFINCS's documented default wet-cell reporting threshold.
- Record the number of clipped time-cell depth values, clipped max-depth cells, and minimum raw active depth in normalized metadata.
- Preserve the raw `sfincs_map.nc` unchanged so every normalization decision remains auditable.

## Operational failure diagnostics decision

- Unexpected run failures must not persist only a generic `INTERNAL_RUN_FAILED` code.
- The run manifest persists the failing stage, exception type, exception message, and relative diagnostic-file path.
- `logs/failure_diagnostic.json` stores the traceback and stage-specific runtime inputs needed for local diagnosis.
- BUILDING_GRID diagnostics include analysis dimensions, elevation array shape/finite range, vector provider, and building/road feature counts.
- Invalid individual vector features (ragged, non-numeric, non-finite, or invalid geometry) are skipped consistently with the existing invalid-polygon filtering policy rather than aborting the entire Full 1 m grid.
- `scripts/diagnose_grid_run.py` is the supported host-local isolation tool for replaying BUILDING_GRID from an existing failed run without repeating SFINCS execution.

## Common vector contract decision

- Full 1 m grid construction consumes one normalized vector interface with `buildings`, `road_lines`, `road_polygons`, and provenance.
- PLATEAU may populate both road lines and polygons.
- OSM currently populates road lines only and must expose `road_polygons` as an explicit empty list.
- An empty member is preferred to provider-specific `hasattr` branching in the hydraulic grid because it preserves one stable normalized provider contract without inventing source geometry.
- Persisted relative artifact/diagnostic paths use forward-slash POSIX form regardless of host OS so manifests remain portable.

## Deterministic validation ownership

- GitHub Actions owns deterministic checks that do not require the user's private/local executable or live provider state.
- `.github/workflows/local-review-ci.yml` is the review-slice deterministic gate.
- Codex should not repeat deterministic checks solely because the local host is missing dependencies; first rely on exact-head CI evidence.
- Local Codex remains necessary for the already-present Windows SFINCS binary, local process behavior, live-provider execution, and real-engine Full 1 m smoke.

## Specification precedence

1. `docs/PRODUCT_SPEC_DRAFT.md`
2. `docs/specs/v0.1-implementation-spec.md`
3. `docs/specs/v0.1-ui-spec.md`
4. `docs/specs/v0.1-ui-implementation-spec.md`
5. Japanese translations are reference only.

## Implementation status decisions

- SFINCS v2.4.0 Galibier remains the v0.1 hydraulic engine.
- HydroMT-SFINCS 2.0.0rc3 remains pinned to source commit `82e58ee85136cf5155c92b42bb9a397869ed8035`.
- Phase 0, Phase 1, Phase 2A and Phase 2B are validated.
- Phase 3 Full 1 m implementation is validated at `62dc85fa163587ea73a875c59067bcd5a8dfe79a`.
- Phase 4 is implementation-in-progress. Adaptive stays disabled until its later canonical gates pass.
- The authority-less local AEQD CRS is canonical. Do not substitute a fake permanent EPSG.

## Preservation constraints

- Preserve validated Phase 0/1/2A/2B/3 behavior unless the active task explicitly requires change.
- Do not silently substitute providers, hydraulic engines, data semantics, CRS semantics or product assumptions.
- Do not enable Adaptive before its canonical acceptance gates are met.
