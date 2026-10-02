# Water magic variant specification

> Status: Draft — catalog and engine forcing validation required before Ready.
>
> Contract shape: standard
>
> Canonical file/language: English; `water-magic-variant-spec.ja.md` is the Japanese reference.
>
> Parent/source-of-truth: existing v0.1 product and UI specifications apply to terrain, grids, execution and native results. This contract overrides sample selection and forcing only in the water magic variant.
>
> Date: 2026-10-02 JST. Baseline: `3fea888773575b288033faa2f67e12ee645609cb`.

## Goal

Choose water magic, preview its placement and footprint on a real map, then simulate the injected water spreading across terrain during casting and a subsequent relaxation period.

## Scope

- A separate variant originating from the frozen main baseline; documentation only in this iteration.
- Replace historical sample-condition selection with a magic catalog and shape-specific controls.
- Local nonnegative water injection with explicit volume, footprint and duration; existing terrain acquisition, progress and result viewing.
- Initial implementation proposal: one cast per run, stationary footprint, no background rainfall, Full 1 m execution. Other supported regular grids require separate validation; Adaptive remains disabled.

## Non-goals

- Modifying or merging into the original main product; changing GitHub branch protection or deploying a website.
- Inventing the spell catalog or attributing invented values to the linked discussion.
- Jet momentum, projectile flight, pressure damage, erosion, magic barriers, water removal, moving sources or simultaneous casts in the initial version.
- Assuming a relaxation period makes the solution reach equilibrium.

## Requirements / Invariants

- WM-01: preserve the exact baseline with tag `baseline/main-before-water-magic-2026-10-02`. Develop on `codex/water-magic-spec` in `C:/VSC/urban-pluvial-flood-simulator-water-magic`. This is a Git branch/worktree variant, not a separately created GitHub repository fork. The original checkout and main receive no feature edits. Subsequent main changes do not alter the recorded baseline.
- WM-02: catalog entries require stable ID, revision, Japanese name, description, illustration reference, footprint kind, supported controls, defaults, bounds, quantity definition, duration and approximation notice. Catalog membership and physical defaults remain blocked pending the discussion content.
- WM-03: selecting a spell initially places its anchor at the current visible map center. Persist that location; panning/zooming must not silently move it. Provide explicit “place at map center” and position adjustment. Analysis-domain geometry and casting geometry are separate.
- WM-04: render a decorative magic illustration and the actual injection footprint as distinct map layers. Illustration scale cannot determine injection area. Keep terrain and analysis boundary visible. Show a direction arrow where applicable. A simple symbolic illustration is allowed when an asset is unavailable, with an accessible text label.
- WM-05: shape controls must have numeric equivalents: disk radius; sector radius/opening angle/bearing; oriented rectangle length/width/bearing; polygon vertex edit/undo/reset. These are supported geometry proposals, not a confirmed spell list. Show only controls applicable to the selected spell. Distances use metres; bearing is clockwise from true north, independent of map rotation. A rectangle starts at its anchor and extends along its bearing, centered across its width.
- WM-06: display total injected volume in m³, duration in seconds, average discharge in m³/s, effective injection area in m² and equivalent source depth/rate. A catalog expressed as a rate must resolve to a volume before execution; volume is not silently scaled when footprint changes.
- WM-07: use nonnegative, spatially local forcing; zero outside the injection support and after casting ends. Do not approximate local forcing by a domain-wide average. Initial time profile is constant discharge over `[0, T_cast)`; later profiles require explicit normalized definitions.
- WM-08: simulation end is `T_end = T_cast + T_relax`, with positive finite casting duration and nonnegative finite relaxation duration. Show and persist both durations and their sum. Relaxation is an editable fixed observation period in the initial proposal; no unvalidated automatic equilibrium rule.
- WM-09: freeze all inputs and the resolved footprint when execution starts. Changing setup or selecting a spell invalidates an older preview. Returning to setup retains editable values; rerunning creates a new run identity.
- WM-10: in results distinguish casting from relaxation, keep the footprint available as a toggle, and reuse native depth/velocity/timeline/point inspection. Maximum results cover the entire simulation. Never depict preview artwork as calculated inundation.
- WM-11: persist catalog revision, resolved values, coordinates/CRS, geometry, forcing profile/hash, source-volume report, baseline, grid and engine provenance. Imported magic runs restore placement without substituting current defaults. Legacy rain archives remain identified as rain results.
- WM-12: short spells require a new verified forcing/output-time policy. Preserve observations at start, casting end and simulation end, and enough samples during casting to resolve its effect. Any engine quantization must be displayed before execution; do not silently round a subminute spell to one minute.

## Affected Interfaces / Contracts

Current baseline evidence:

| Boundary | Observed constraint | Required review |
| --- | --- | --- |
| `web/src/dev/SmokeApp.tsx` | “サンプルまたは読込み”, historical ranking and sample dialog | Replace catalog/selection in variant; retain separately labelled archive import |
| `floodsim/domain/run_config.py` | Required `rainfall` discriminated union; extra fields forbidden | Versioned magic configuration; do not insert unsupported fields into legacy schema |
| `floodsim/domain/rainfall.py` | `meteorological_spatial_mode` is `uniform`; constant rain duration is integer minutes and intensity <=500 mm/h | Separate local source and second-based time contracts; do not reuse rainfall limits as magic limits |
| `floodsim/orchestration/rainfall_resolution.py` | Resolves temporal rainfall profiles | Separate casting end from total simulation end |
| `floodsim/sfincs/model_builder.py` | Builds `precip_2d(time,y,x)` from temporal rate times `grid.rain_weight`; writes `sfincs_netampr.nc` | Confirm engine interpolation, zero cutoff, active-cell placement and roof redistribution semantics |
| same builder, `derive_output_interval_seconds` | Existing output policy has a whole-minute lower bound | Validate short-duration source/output support before Ready |

These observations are source reads, not proof that the new forcing works in the real engine. Production code is unchanged in this draft. Exact API names, schema version and affected tests belong to subsequent repository review. Optional query helpers are not prerequisites.

## Approved Tools / Implementation Constraints

Use existing map, backend, grid and SFINCS boundaries where validated. No new dependency is approved by this draft. Before code changes, perform targeted CodebaseMemory CLI queries when available, verify against source, and stop operation-owned processes afterwards. Do not enable persistent MCP registration or refresh the graph for this documentation-only change.

## Inputs and Outputs

Proposed logical inputs (not yet public API field names): catalog ID/revision; anchor WGS84 longitude/latitude; geometry; total volume; casting seconds; relaxation seconds; grid/domain settings. Project geometry to the run's metre-based CRS before area calculations; geographic degrees are never metres.

Define eligible cell source areas `a_i` by intersecting the footprint with water-accepting computational cells. Let `A = sum(a_i) > 0`, cell area `A_i`, volume `V`, and constant discharge `Q = V / T_cast`. Then cell source depth rate is `r_i = Q * a_i / (A * A_i)` m/s; precipitation-equivalent rate is `r_i * 3,600,000` mm/h. Hence `sum(r_i * A_i) = Q`. Partial-cell intersections must be retained; a footprint smaller than a cell must not vanish through center-point rasterization.

The backend is authoritative for eligible areas, CRS and volume validation. Initial policy proposal: reject footprints extending outside the domain rather than clipping silently. Inactive/impermeable source locations must report requested and eligible area and the redistribution policy before execution; explicit confirmation of any changed effective footprint is required. Roof routing must not duplicate or lose water. A wholly ineligible footprint is rejected. The eligibility/routing policy is an unresolved readiness gate.

Persist geometry, source values, casting cutoff, zero-source relaxation, generated forcing checksum, expected and actual integrated source volumes. Result outputs retain native result contracts, additionally carrying magic metadata and phase boundaries.

## State / Normal Flow

`SETUP -> MAGIC_SELECTED -> PLACEMENT_EDITING -> READY -> RUNNING -> RESULT`, with failed/canceled runs reported using existing orchestration states. These are logical UI states, not proposed new backend enum values.

1. Choose map/domain and a spell.
2. Place at current map center; preview artwork and injection footprint.
3. Adjust position, direction/range, volume and durations; backend validates effective footprint and budget.
4. Confirm the visible resolved parameters and start analysis.
5. Build localized forcing, run casting plus relaxation, then open native results.
6. Replay actual output times; inspect water depth/velocity and casting/relaxation phase.

## Errors / Fallbacks / Stop Conditions

Reject NaN/infinite/negative values, nonpositive volume/duration, invalid polygons, out-of-domain footprints, zero eligible area, unsupported catalog revisions and run budgets exceeding verified limits. All limits must be declared in the catalog/engine capability contract before Ready.

Missing artwork permits a labelled symbolic preview. Missing forcing support, excessive source rates or incompatible time sampling must block execution with an actionable explanation, never substitute uniform rainfall or clamp the quantity. Boundary overflow/loss and numerical failure must be reported. Unresolved geometry, interpolation, roof routing or physical semantics require `spec-change-required` before implementation readiness.

## Physical / Numerical Assumptions

Magic is approximated as addition of water mass to a shallow-water terrain solver. Direction rotates the injection footprint; it does not inject horizontal momentum. Magic requiring jet momentum cannot be labelled physically reproduced by this model. Infiltration, roughness, roof handling and open/closed boundaries use explicitly recorded model settings; changing them requires separate review. Relaxation may retain pooled water, particularly with closed boundaries.

Time discretization must conserve the prescribed source volume across casting cutoff: inspect the generated file and real engine behavior, since endpoint sampling alone does not prove zero tail or step semantics. Do not adopt an epsilon cutoff without an error budget. Grid resolution, very large local depth/rate and forcing-memory growth require budget checks and refinement/convergence evidence. Sparse or factored forcing is allowed only if physically equivalent to the declared source.

## Acceptance Criteria

- AC-01: baseline tag resolves to the recorded main SHA; isolated variant differs only by specifications at this stage.
- AC-02: spell selection places artwork and footprint at map center; map navigation preserves location; explicit recentering moves it. Numeric direction/range agrees with map handles, including a rotated map.
- AC-03: invalid geometry/values and unsupported physical spells cannot execute; missing artwork leaves an operable labelled preview.
- AC-04: requested/generated source volume relative error <=`1e-6` in float64 geometric/time integration; serialized engine forcing <=`1e-4`. Outside support and throughout relaxation the defined source is zero. Exact integration must use the verified engine interpolation convention.
- AC-05: source-only, flat, closed, no-loss test conserves final stored water to <=1% of injected volume; a zero-source control produces no water. These are proposed acceptance tolerances requiring repository review, not passed results.
- AC-06: disk, directional sector/rectangle and partial-cell fixtures prove area/rotation; invalid/outside/ineligible cases prove rejection or explicit routing disclosure. Engine-backed runs show terrain-driven spreading and no unintended relaxation injection.
- AC-07: a proposed short-duration fixture (5 seconds casting plus 60 seconds relaxation) observes casting end and subsequent spread without minute rounding; if unsupported, this blocks Ready and requires revising capability/scope.
- AC-08: export/import reproduces resolved placement, quantity, durations and catalog revision. Legacy rain results retain their identity. Native depth/velocity inspection and all existing retained result controls remain functional.

## Validation

This iteration: documentation structure, links, baseline identity, bounded diff and `git diff --check`; no hydraulic or browser-product acceptance is claimed.

Before Ready: obtain source discussion, complete catalog and limits, settle source eligibility/roof handling, query relevant symbols/callers/tests on demand, and verify pinned engine forcing/time behavior against primary documentation and a tiny real-engine experiment.

Before implementation acceptance: applicable independent quality checks before focused tests; geometry/time/mass unit tests; generated forcing inspection; API/schema/archive integration; tiny real SFINCS source-only and terrain runs; browser selection/placement/direction/timeline/return/import flows; regression of retained results. Use the canonical `urban-pluvial-flood-phase0` interpreter for Python checks. Record exact versions, SHA, commands, exit status and artifacts. Full-suite/build/release gates follow repository policy when implementation exists.

## Completion Criteria

- [ ] Discussion content is captured with confirmed spell definitions and revisions.
- [ ] Product defaults, bounds, relaxation presets and source eligibility are decided.
- [ ] Engine localization, cutoff, output times and volume acceptance are demonstrated.
- [ ] Repository review resolves schema/UI/result compatibility and defines implementation tasks.
- [ ] User review accepts the resulting contract; then status may become Ready.

Creating this draft completes the present documentation task; the checklist describes future implementation readiness.

## Required Repository Tools

`git`, `rg`, repository-native documentation checks. CodebaseMemory CLI only for necessary future code investigation; no persistent server. Real engine and browser are required for eventual product acceptance, not for creating this draft.

## Risks / Rollback

Concentrated volume may cause high local depth, small stable timesteps and large forcing arrays. Unverified interpolation may leak source into relaxation. Mask/roof transformations may change effective placement. Check each before Ready. Keep the original variant and baseline independently addressable; investigate defects before considering rollback. No deployment or original-product migration is included.

## Open Questions

1. The conversation at https://chatgpt.com/c/6abdb38d-8f90-83e9-9cfe-af76e33518cc was inaccessible: public retrieval returned a login page, Chrome navigation/DOM retrieval timed out. Which exact spells, quantities and durations were agreed?
2. Are any agreed spells momentum-driven, moving, removing water or barrier-producing, requiring another model/scope?
3. Which catalog presets/bounds and relaxation defaults should be offered?
4. What source placement/roof routing policy preserves both the intended footprint and mass?
5. Does the pinned engine faithfully support the proposed short-time forcing/output contract, and what validated execution limits apply?
6. Does “fork” require a separately named GitHub repository in addition to the branch/worktree created here? Destination/ownership/name were not specified; no new GitHub repository is created by this draft.
