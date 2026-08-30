# Urban Pluvial Flood Simulator — Product Specification Draft

> Status: Draft
>
> This document defines **what the product should do**, **what v0.1 will not do**, and **what the project intentionally will never claim or replace**.
>
> It is written for both human readers and future detailed implementation specifications. Each chapter is intentionally kept to one conceptual unit and ends with a scope check.

---

# 0. How to read this document

## Purpose

This specification is the source of truth for product scope before detailed implementation design.

The document separates four categories explicitly:

1. **Do now** — required for v0.1.
2. **Do later** — intentionally deferred, but architecturally anticipated.
3. **Do not do now** — outside v0.1 and not required for acceptance.
4. **Permanent non-goal** — the project should not become or claim this in the future.

Requirements use stable IDs such as `UI-001`, `DATA-003`, and `SIM-010`. A later implementation specification should reference these IDs rather than restating product intent.

## Human readability rule

Each chapter should answer one question only.

The preferred reading pattern is:

```text
Why does this chapter exist?
↓
What was decided?
↓
What must the implementation provide?
↓
What is explicitly outside scope?
↓
How do we know the chapter still matches the product goal?
```

## Detail boundary

This document may define:

- observable product behavior;
- data contracts at a conceptual level;
- mandatory validation and warnings;
- required external providers;
- acceptance criteria.

This document should not define:

- class names;
- exact function signatures;
- thread models;
- internal file serialization unless externally observable;
- GUI framework selection;
- detailed SFINCS file-writing implementation.

Those belong in the later detailed implementation specification.

### Chapter check

- Target alignment: **Yes** — keeps the document usable by humans and implementation agents.
- Do now: use requirement IDs and explicit scope labels.
- Do later: derive detailed implementation specifications from these IDs.
- Permanent non-goal: do not mix product decisions and low-level code decisions in the same document.

---

# 1. Product goal and target users

## Purpose

Define the product before defining features.

## Product goal

`Urban Pluvial Flood Simulator` allows a person to select an arbitrary location in Japan and run a high-resolution pluvial-flood scenario with minimal setup.

The intended experience is:

```text
Search address or move map
↓
Select analysis area
↓
Select rainfall scenario
↓
Select accuracy mode
↓
Run
↓
View maximum depth and time evolution on the map
```

The user should not need to manually download DEM files, CityGML, create SFINCS input files, or understand GIS file formats.

## Target users

Primary users:

- people who want to understand flood behavior around their home or workplace;
- students and educators;
- technically interested non-specialists;
- engineers who want a rapid screening model;
- developers who want reproducible Japanese urban test areas.

The UI must remain understandable without prior knowledge of SFINCS, CityGML, DEM tiles, or hydraulic equations.

## Product positioning

The product is a **scenario simulator**, not an official warning system.

The initial product answers questions such as:

> What might the surface-water distribution look like here if rainfall comparable to a historical extreme event occurred?

It does not answer:

> Will my house definitely flood tomorrow?

## Requirements

- `PROD-001`: A first-time user shall be able to create an analysis without preparing GIS source files manually.
- `PROD-002`: The default workflow shall expose only decisions a non-specialist can reasonably understand: location, area, rainfall, and accuracy mode.
- `PROD-003`: Advanced hydraulic details may be shown as expandable information, but shall not be required to start a run.
- `PROD-004`: Every result view shall state that the output is a numerical scenario and not official evacuation or flood-warning information.

## Permanent non-goals

The project shall never:

- present results as official flood warnings or evacuation orders;
- guarantee property-level safety or damage outcomes;
- hide significant modelling omissions from the user;
- imply deterministic certainty from uncertain terrain, rainfall, or boundary data;
- bypass source-data licensing, attribution, authentication, or usage restrictions.

### Chapter check

- Target alignment: **Yes** — prioritizes broad accessibility and rapid local simulation.
- Do now: scenario simulator for arbitrary Japanese locations.
- Do later: richer forecasting inputs may be added without changing the product identity.
- Permanent non-goal: replacing government disaster information or making guaranteed safety claims.

---

# 2. v0.1 end-to-end user flow

## Purpose

Define the minimum complete product, rather than a collection of disconnected utilities.

## Required flow

A v0.1 run is complete only when the following sequence can be performed from one application workflow:

```text
1. Start application
2. Search address or position map
3. Select area
4. Select rainfall scenario
5. Select Full 1 m or Adaptive mode
6. Review limitations and estimated resource use
7. Start analysis
8. Automatically acquire terrain and urban data
9. Generate SFINCS model
10. Execute SFINCS
11. Read results
12. Display flood depth on map
```

## Requirements

- `FLOW-001`: No manual GSI or PLATEAU file preparation shall be required in the default flow.
- `FLOW-002`: Data acquisition, preprocessing, model generation, solver execution, and result loading shall be coordinated by the application.
- `FLOW-003`: Failure shall be reported at the stage where it occurred, using user-facing language.
- `FLOW-004`: The application shall retain enough manifest information to reproduce which external datasets and engine version were used.
- `FLOW-005`: Re-running the same area shall reuse valid cached source/preprocessed data where possible.

## Not required in v0.1

- cloud accounts;
- project collaboration;
- batch runs of hundreds of scenarios;
- real-time forecast automation;
- sewer-network coupling.

### Chapter check

- Target alignment: **Yes** — defines “almost no setup” as an end-to-end requirement.
- Do now: complete local workflow from map selection to visualization.
- Do later: large batch/cloud workflows.
- Permanent non-goal: none added here.

---

# 3. Location search and analysis-area UI

## Purpose

Keep geographic setup simple enough for a non-GIS user.

## Map interaction

The main screen shall contain:

- a map;
- an address/location search field;
- an analysis-area selector;
- rainfall selection;
- accuracy selection;
- run control.

## Address and coordinate search

- `UI-001`: The user shall be able to search for a Japanese address or place name.
- `UI-002`: The user shall be able to enter latitude/longitude directly.
- `UI-003`: Selecting a result shall move the map and set the candidate analysis center.
- `UI-004`: Geocoding shall be provider-abstracted because provider terms and availability may change.

## Area selection modes

Two modes are required.

### Center-radius preset

The user selects a center and one of:

- ±250 m;
- ±500 m;
- ±1000 m;
- ±2000 m.

This produces square areas of approximately:

- 0.5 km × 0.5 km;
- 1 km × 1 km;
- 2 km × 2 km;
- 4 km × 4 km.

### Rectangle selection

The user draws an arbitrary rectangle on the map.

During selection, show:

- width;
- height;
- area.

## Resource preview

Before run, the UI shall show an estimate of:

- computational cells;
- memory demand;
- expected disk usage category;
- a qualitative runtime class such as small / medium / heavy.

Exact time estimates are not required because hardware and solver behavior vary significantly.

### Chapter check

- Target alignment: **Yes** — geographic selection requires no GIS knowledge.
- Do now: address search, coordinate entry, presets, rectangle.
- Do later: polygon areas and administrative-boundary selection.
- Permanent non-goal: none added here.

---

# 4. External geographic data

## Purpose

Define authoritative default sources while keeping provider-specific behavior replaceable.

## Elevation source

The default elevation source is the public GSI elevation-tile service.

Provider priority:

```text
DEM1A
↓
DEM5A
↓
DEM5B
↓
DEM5C
↓
DEM10B
```

GSI documents this same high-to-low-resolution fallback concept for elevation lookup. The application shall record which source contributed to each processed area.

Reference:

- https://maps.gsi.go.jp/development/elevation.html

## Urban geometry source

The first-choice building/transportation provider is Project PLATEAU.

PLATEAU's distribution API supports spatial CityGML lookup and filtering by feature type such as `bldg` and `tran`.

References:

- https://docs.plateauview.mlit.go.jp/api/rest/
- https://docs.plateauview.mlit.go.jp/api/rest/operations/datacatalogcitygmlconditions/

The PLATEAU API is documented as a trial service and may change without notice. Therefore provider handling shall remain isolated behind a data-provider boundary.

## Vector fallback

If PLATEAU does not provide usable building geometry for the selected area, v0.1 may use the existing OpenStreetMap fallback.

The UI/manifest must disclose the actual provider used.

## Requirements

- `DATA-001`: GSI elevation acquisition shall be automatic in the normal workflow.
- `DATA-002`: PLATEAU shall be the first-choice building/road source.
- `DATA-003`: Provider and source resolution shall be recorded in the run manifest.
- `DATA-004`: Source-data caches shall be keyed so stale and current data are distinguishable.
- `DATA-005`: External API changes shall not require changes to the hydraulic-engine interface.
- `DATA-006`: Attribution required by source terms shall be displayed or packaged with results as appropriate.

## Not required in v0.1

- user-selected arbitrary GIS providers;
- cadastral/property-boundary datasets;
- private commercial map data.

### Chapter check

- Target alignment: **Yes** — Japanese public data is acquired without manual preparation.
- Do now: GSI + PLATEAU first, OSM fallback.
- Do later: additional providers if they materially improve coverage or reliability.
- Permanent non-goal: bypassing source terms or hiding provenance.

---

# 5. Hydraulic engine: SFINCS

## Purpose

Fix one recommended engine for v0.1 so the first product is simple and testable.

## Decision

v0.1 shall use **SFINCS** as the only user-visible hydraulic engine.

SFINCS is selected because it combines:

- pluvial/Rain-on-Grid modelling;
- high computational performance;
- quadtree support;
- subgrid tables using high-resolution elevation information;
- an actively maintained open-source codebase.

SFINCS documents subgrid tables as a way to calculate on coarser hydraulic grids while retaining high-resolution elevation information for water-level/volume and momentum-related relationships.

References:

- https://github.com/Deltares/SFINCS
- https://sfincs.readthedocs.io/en/latest/input.html
- https://sfincs.readthedocs.io/en/latest/developments.html

## Engine abstraction

Internally, the product shall still have an engine boundary so another engine can be added later.

The boundary conceptually provides:

```text
prepared terrain + geometry + rainfall
        ↓
engine adapter
        ↓
engine-specific model files
        ↓
run engine
        ↓
normalized result dataset
```

## Requirements

- `ENG-001`: v0.1 shall support SFINCS only in the main UI.
- `ENG-002`: SFINCS-specific input/output handling shall not leak into UI or data-acquisition modules.
- `ENG-003`: Results shall be normalized into product-level concepts such as maximum depth, depth-by-time, and velocity when available.
- `ENG-004`: The manifest shall record SFINCS version and engine package identity.
- `ENG-005`: Engine failure output shall be preserved for debugging while the UI presents a concise failure reason.

## Distribution policy

The source code of SFINCS is GPL-3.0 and permits commercial use, distribution, and modification under GPL conditions.

The project shall not depend on redistributing a separately licensed official precompiled executable where redistribution is prohibited.

Preferred v0.1 distribution choices are:

1. build SFINCS from its GPL source in the project's release/CI process and distribute it while satisfying GPL source obligations; or
2. provide a bootstrap installer that acquires a permitted engine package without bypassing license/terms.

The exact release mechanism shall be finalized in the implementation specification after a license/compliance review.

## Alternatives considered

### HEC-RAS 2D

Strong engineering reference and useful comparison target, but less suitable for this near-zero-setup, cross-platform automated workflow.

### ANUGA

Full shallow-water finite-volume model with attractive licensing, but less directly aligned with the raster/subgrid/quadtree workflow targeted here.

### LISFLOOD-FP

Hydraulically close to the previous native Local-Inertial implementation, but the current SFINCS ecosystem is a better fit for automated modern preprocessing and subgrid use.

### BG_Flood

Technically interesting future comparison because of GPU/quadtree approaches, but not selected as the v0.1 primary engine.

### Chapter check

- Target alignment: **Yes** — one engine minimizes setup and decision burden while supporting adaptive high-resolution modelling.
- Do now: SFINCS only.
- Do later: optional alternative engine adapters for validation or specialized use.
- Permanent non-goal: forcing users to understand engine-specific input files for normal use.

---

# 6. Accuracy modes and grid strategy

## Purpose

Provide a simple user choice while keeping the default philosophy accuracy-first.

## User-visible modes

Only two modes are required in v0.1:

### High accuracy — Full 1 m

The requested domain is represented using a nominal 1 m hydraulic grid wherever the available data and SFINCS configuration permit.

This is the reference/benchmark mode.

### Automatic optimization — Adaptive

The model starts from an accuracy-first assumption and coarsens only where high resolution is unlikely to add meaningful hydraulic information.

The intended quadtree sequence is:

```text
1 m → 2 m → 4 m → 8 m → 16 m → 32 m
```

## Adaptive principle

The algorithm shall **not** begin by assigning coarse resolution solely from land-use categories.

Instead:

> A region may be coarsened only when the available terrain and feature evidence indicate that finer hydraulic cells are unlikely to materially improve surface-flow representation.

Potential refinement evidence includes:

- PLATEAU buildings;
- roads and transportation corridors;
- elevation variance;
- slope;
- curvature;
- flow accumulation / valley structure;
- narrow channels;
- embankment-like linear terrain;
- user-designated critical regions.

## Initial expected behavior

Typical outcomes, not hard-coded guarantees:

| Environment | Expected hydraulic resolution |
|---|---:|
| building boundaries | 1 m |
| important roads / narrow urban flow paths | 1–2 m |
| general urban open space | 2–4 m |
| simple parking areas / parks | 4–8 m |
| simple agricultural fields | 8–16 m |
| hydraulically simple mountain slopes | 16–32 m |
| valleys, channels, roads in mountains | refine again as needed |

## Subgrid rule

Coarsening hydraulic cells shall not imply intentionally discarding the best available source DEM.

Where supported by SFINCS preprocessing, high-resolution terrain shall be used to derive subgrid information for coarser hydraulic cells.

Conceptually:

```text
16 m hydraulic cell
+
best available high-resolution terrain
↓
subgrid storage / wet fraction / conveyance relationships
```

## Buildings

Buildings shall not be treated as “safe to coarsen” merely because subgrid terrain exists.

Where usable building footprints are available:

- building boundaries shall trigger high refinement;
- building obstruction shall be represented explicitly in the generated hydraulic model where feasible;
- the implementation shall avoid creating false hydraulic connectivity through a building footprint.

## Requirements

- `GRID-001`: Full mode shall provide a reproducible 1 m reference configuration.
- `GRID-002`: Adaptive mode shall use the power-of-two refinement hierarchy from 1 to 32 m unless SFINCS constraints require an equivalent compatible hierarchy.
- `GRID-003`: Adaptive refinement shall be accuracy-first, not simply land-use-first.
- `GRID-004`: Building and narrow-flow-path evidence shall prevent inappropriate coarsening.
- `GRID-005`: Adaptive generation shall report the final cell counts by level.
- `GRID-006`: The UI shall display the reduction from 1 m equivalent cells to actual adaptive cells.
- `GRID-007`: A future implementation specification shall define quantitative coarsening thresholds and their validation dataset; this product specification intentionally does not fix those thresholds yet.

## Acceptance concept

Adaptive mode is not considered successful merely because it is faster.

It must be validated against Full 1 m reference runs on representative areas, comparing at least:

- maximum-depth field error;
- flooded-area difference above selected thresholds;
- mass/volume behavior;
- important local flow-path changes;
- runtime and memory savings.

### Chapter check

- Target alignment: **Yes** — default philosophy is maximum useful precision, with computation removed only where precision has little value.
- Do now: Full 1 m + Adaptive 1/2/4/8/16/32 m concept with subgrid use.
- Do later: automatic threshold tuning from a larger benchmark corpus.
- Permanent non-goal: coarse resolution chosen only to make benchmark numbers look faster.

---

# 7. Rainfall scenarios and historical events

## Purpose

Let non-specialists create meaningful scenarios without manually constructing rainfall time series.

## User-visible rainfall choices

v0.1 shall provide three conceptual entry points:

1. **Historical rainfall**
2. **Custom constant rainfall**
3. **Advanced time series**

## Historical rainfall

The application shall allow users to choose a relevant observation station and historical extreme/ranked rainfall scenario.

The product may show examples such as:

- maximum 1-hour precipitation;
- extreme multi-hour or daily precipitation where a defensible dataset is available;
- event date;
- observation station;
- distance between analysis center and observation station.

## Two historical-event modes

### Equivalent uniform event

Example:

```text
100 mm observed over 1 hour
→ 100 mm/h for 1 hour over the model domain
```

This is intentionally a hypothetical spatially uniform scenario.

The UI must label it as such.

### Observed temporal profile

Where usable historical sub-daily observations can be obtained, the application may reproduce the observed temporal hyetograph rather than distributing the total uniformly.

JMA's historical-data download service provides past observations and CSV output, and the data may include quality/homogeneity metadata. JMA also documents request-volume limits and that historical data can be revised.

References:

- https://www.data.jma.go.jp/risk/obsdl/
- https://www.data.jma.go.jp/risk/obsdl/top/help3

## Data-access policy

v0.1 shall not aggressively scrape JMA on every UI operation.

Preferred architecture:

```text
small locally packaged/cached station + ranking catalog
+
on-demand acquisition of the selected event time series
+
local cache
```

The exact acquisition implementation shall be designed to respect JMA service limits and terms.

## Custom rainfall

Required simple inputs:

- rainfall intensity in mm/h;
- duration.

Advanced input may support a time series.

## Spatial rainfall assumption in v0.1

Rainfall is spatially uniform across the selected domain:

```text
R(x, y, t) = R(t)
```

This limitation must be shown to the user.

## Requirements

- `RAIN-001`: v0.1 shall support constant intensity + duration.
- `RAIN-002`: v0.1 shall expose historical extreme/ranked scenarios where source data can be reliably prepared.
- `RAIN-003`: Historical scenarios shall display observation station and event metadata.
- `RAIN-004`: Equivalent-uniform and observed-time-profile scenarios shall be clearly distinguished.
- `RAIN-005`: Missing/quality-limited observation data shall not silently become zero rainfall.
- `RAIN-006`: Rainfall input provenance shall be stored in the run manifest.

## Not required in v0.1

- radar rainfall fields;
- XRAIN spatial grids;
- forecast nowcasting;
- ensemble rainfall forecasts.

These are future candidates because they would materially improve actual forecasting capability.

### Chapter check

- Target alignment: **Yes** — historical extremes make the simulator understandable and personally relevant.
- Do now: historical presets, constant rainfall, optional observed temporal profile where practical.
- Do later: spatial/forecast rainfall.
- Permanent non-goal: presenting a historical scenario as a prediction that the same spatial rainfall pattern will occur locally.

---

# 8. Roof rainfall and mass conservation

## Purpose

Define a deliberate treatment for rainfall falling on building footprints.

## Decision

v0.1 shall **not discard rainfall merely because a cell is occupied by a building**.

Rainfall volume falling on roof/building footprint areas shall be redistributed to eligible ground cells near the building boundary so that rainfall mass is conserved, subject to numerical tolerance.

Conceptually:

```text
roof rainfall volume
↓
remove from blocked building surface cells
↓
redistribute to eligible perimeter ground cells
↓
total rainfall volume remains unchanged
```

This is a modelling approximation of roof runoff, not a detailed gutter/downpipe model.

## Requirements

- `MASS-001`: Roof-rainfall preprocessing shall conserve rainfall volume to a documented numerical tolerance.
- `MASS-002`: The redistribution method shall not place runoff inside inactive/blocked building cells.
- `MASS-003`: A mass-balance diagnostic shall be recorded for each generated model.
- `MASS-004`: The UI/documentation shall state that roof drainage direction, gutters, downpipes, and sewer connections are not modelled in v0.1.

## Future relationship to sewers

When sewer/drain information is added in the future, roof runoff may be routed to explicit drains or network nodes where supported by data.

The v0.1 redistribution mechanism therefore belongs behind a replaceable `surface runoff allocation` concept, not hard-wired into the UI.

### Chapter check

- Target alignment: **Yes** — avoids a systematic loss of rainfall while retaining a simple surface model.
- Do now: mass-conserving perimeter redistribution.
- Do later: route roofs to explicit drainage assets when trustworthy data exists.
- Permanent non-goal: claiming that perimeter redistribution reproduces real individual-building drainage plumbing.

---

# 9. Explicitly omitted physics and infrastructure

## Purpose

Prevent users from interpreting the simulation as more complete than it is.

This chapter is mandatory product behavior, not optional documentation.

## v0.1 does not model

### Infiltration

No soil infiltration is subtracted in v0.1.

Effect:

- more rainfall remains available as surface water than in reality where infiltration occurs;
- results can therefore be conservative/overestimating in permeable areas, though other omissions can act in other directions.

Status: **deferred future candidate**.

### Sewer networks and storm drains

v0.1 does not model:

- underground sewer pipes;
- storm-drain inlet capacity;
- manholes;
- surcharge from sewers back to the surface;
- pumps;
- combined/sanitary network behavior.

Status: **planned future extension**, when reliable public or user-provided data can be supported.

### Detailed gutters and very small drainage structures

v0.1 does not explicitly resolve every:

- curb;
- roadside gutter;
- grate;
- small wall;
- driveway lip;
- private drainage structure.

Features present in the source elevation may influence terrain indirectly, but this is not equivalent to an explicit asset model.

Status: **future improvement where defensible data exists**.

### Building interior flooding

Buildings are hydraulic obstacles in the surface model. v0.1 does not model water entering and moving through individual building interiors.

Status: **not in v0.1; future scope undecided**.

### Spatially varying rainfall

v0.1 assumes uniform rainfall over the analysis area.

Status: **future candidate**.

### River and coastal boundary coupling

v0.1 is focused on pluvial surface-water scenarios. It does not initially provide a complete river-stage, tidal, coastal-surge, or compound-flood workflow.

Status: **future specialized extension**, not required for core pluvial use.

### Operational forecast assimilation

v0.1 does not assimilate live observations or continuously issue future flood predictions.

Status: **future product category**, only if sufficient data quality and validation are achieved.

## Mandatory user warning

A visible limitation notice shall be present:

- before the user starts a simulation;
- in the result view;
- in exported result metadata.

Minimum meaning:

> This simulation does not currently account for infiltration, sewer/drain capacity, or other omitted infrastructure and physics. Results are scenario calculations and are not official flood forecasts or evacuation information.

The exact UI wording may be refined for readability but shall not weaken the meaning.

## Requirements

- `LIMIT-001`: The limitation notice shall be continuously discoverable in the primary result UI, not hidden only in documentation.
- `LIMIT-002`: A user shall not be able to export a result without the manifest retaining the model limitations/version.
- `LIMIT-003`: UI language shall avoid describing v0.1 output as a validated property-level forecast.
- `LIMIT-004`: Infiltration shall be explicitly set to “not modelled” rather than assumed silently.
- `LIMIT-005`: Sewer/drainage shall be explicitly set to “not modelled” in v0.1.

## Permanent non-goals

Even if future versions add more physics, the product shall not:

- claim absolute flood certainty;
- replace official warnings;
- suppress uncertainty and omitted-process information.

### Chapter check

- Target alignment: **Yes** — accessibility is not allowed to come at the cost of misleading users.
- Do now: explicit warning for infiltration, sewers, drainage, rainfall uniformity, and scenario nature.
- Do later: infiltration/sewers/spatial rain if data and validation support them.
- Permanent non-goal: certainty claims and official-warning substitution.

---

# 10. SFINCS installation and near-zero setup

## Purpose

Ensure that choosing an external engine does not recreate a complex setup burden for users.

## Desired experience

For a normal binary release:

```text
download application
↓
start application
↓
engine check
↓
if missing, acquire/install a compatible SFINCS engine package
↓
run
```

Users should not be required to manually understand Fortran compilers, NetCDF setup, or SFINCS model files.

## Source users

Source builds shall remain supported for developers and advanced users.

## Engine package policy

- `DIST-001`: The application shall verify the SFINCS engine version before a run.
- `DIST-002`: Engine acquisition shall verify integrity, e.g. with a published cryptographic checksum.
- `DIST-003`: The engine's applicable license and corresponding source availability shall be accessible from the application/release documentation.
- `DIST-004`: The bootstrap process shall not automate around login, license acceptance, or access restrictions in ways forbidden by the upstream provider.
- `DIST-005`: A precompiled application release should be provided for at least Windows x64 when the build system is mature enough.
- `DIST-006`: Linux x64 is a desired v0.1/v0.x release target if release automation is practical.

## Browser direction

Running SFINCS directly in the browser is not a v0.1 requirement.

A future browser edition may use:

```text
browser UI
↓
service API
↓
server-side preprocessing + SFINCS worker
↓
result tiles/data
```

This remains separate from the local zero-setup application goal.

### Chapter check

- Target alignment: **Yes** — external engine choice remains invisible to normal users.
- Do now: bootstrap/version/integrity architecture and straightforward local binary distribution.
- Do later: browser service and broader platform packaging.
- Permanent non-goal: circumventing upstream license/access restrictions.

---

# 11. Results and visualization

## Purpose

Return understandable flood information, not raw solver files.

## Minimum result layers

### Maximum water depth

This is the default result layer.

The viewer shall support a clearly labeled depth color scale.

### Time-dependent water depth

A time slider shall allow inspection of water depth as the event progresses when SFINCS output is configured at suitable intervals.

### Point inspection

Clicking a map location should show, where available:

- maximum depth;
- time of maximum depth;
- depth at current timeline position;
- terrain elevation;
- velocity or discharge-derived metric if reliably available.

## Adaptive-grid transparency

Adaptive runs shall allow the user to inspect the generated computational resolution map.

This is important because the product explicitly claims to preserve fine resolution where it matters.

## Comparison support

The normalized result format shall permit Full 1 m and Adaptive runs to be compared using the same viewer/data tools.

## Requirements

- `RES-001`: Maximum depth shall be displayed on a geographic map.
- `RES-002`: Result legends shall include units.
- `RES-003`: The user shall be able to see the analysis boundary and data/engine metadata.
- `RES-004`: Adaptive result views shall expose the hydraulic-grid resolution map.
- `RES-005`: Limitations shall remain visible/discoverable on the result screen.
- `RES-006`: Raw SFINCS outputs may be retained for expert use, but are not the primary user interface.

### Chapter check

- Target alignment: **Yes** — results are understandable without hydraulic software expertise.
- Do now: max depth, time view where available, point inspection, grid-resolution overlay.
- Do later: richer velocity/animation/export tools.
- Permanent non-goal: presenting unqualified solver numbers without units/provenance.

---

# 12. Reproducibility, caching, and manifests

## Purpose

A simulation should remain explainable after external source data changes.

## Run manifest

Each run shall record at least:

```text
analysis geometry
coordinate reference information
terrain providers and resolutions
PLATEAU/OSM provider information
source-data timestamps or dataset identifiers where obtainable
rainfall source and scenario definition
accuracy mode
adaptive grid summary
SFINCS version/build identity
application version
known model limitations
```

## Caching

Cache categories may include:

- GSI tiles;
- PLATEAU files;
- OSM responses;
- processed terrain;
- adaptive/subgrid products;
- rainfall catalogs/time series;
- engine package.

Cache reuse must not obscure provenance.

## Requirements

- `REP-001`: Every result shall have a machine-readable manifest.
- `REP-002`: Cache hits shall produce equivalent processed inputs to a fresh acquisition of the same pinned source version, subject to upstream data changes when using “latest” endpoints.
- `REP-003`: When a source is inherently “latest”, the manifest shall record enough information to identify what was obtained at run time where possible.
- `REP-004`: A project/run shall be reopenable without re-entering its basic configuration.

### Chapter check

- Target alignment: **Yes** — simple use remains scientifically inspectable.
- Do now: cache + manifest + reopen basic run metadata.
- Do later: formal archival bundles and reproducibility locks.
- Permanent non-goal: untraceable results with unknown source versions.

---

# 13. Validation and acceptance strategy

## Purpose

Define what “works” means before detailed implementation begins.

## Three validation layers

### A. Data correctness

Verify:

- GSI elevation decoding and orientation;
- coordinate transforms;
- PLATEAU building position/orientation;
- road geometry;
- missing-data fallback;
- roof-rainfall mass conservation.

### B. Engine integration correctness

Verify:

- generated SFINCS model opens/runs successfully;
- engine version is detected;
- output can be read and normalized;
- failures are surfaced cleanly;
- dry/no-data/blocked areas are handled as designed.

### C. Hydraulic usefulness

Compare:

```text
Full 1 m reference
vs
Adaptive
```

on several representative classes:

- dense urban blocks;
- suburban roads and detached buildings;
- large parking/open urban area;
- park/field;
- agricultural area;
- mountainous slope with valley/road.

## Adaptive acceptance metrics

The detailed implementation specification shall define numerical thresholds, but must include at least:

- flooded-area agreement at selected depth thresholds;
- maximum-depth error distribution;
- important-flow-path preservation;
- mass balance;
- runtime;
- memory;
- cell-count reduction.

A configuration that achieves large speedup but materially changes important urban flow paths shall fail validation.

## Product acceptance scenario

At minimum, one v0.1 release candidate shall demonstrate:

```text
launch app
→ search location
→ choose ±500 m
→ choose a historical rainfall scenario
→ choose Adaptive
→ run automatic data acquisition
→ generate and run SFINCS
→ display maximum depth
```

No manual GIS download or SFINCS input editing may be required.

## Requirements

- `VAL-001`: Automated unit tests shall cover deterministic conversion/math logic.
- `VAL-002`: Network integration tests shall be separate from offline unit tests.
- `VAL-003`: A SFINCS smoke test shall be part of release validation.
- `VAL-004`: Adaptive mode shall be benchmarked against Full 1 m before being advertised as the recommended mode.
- `VAL-005`: Known validation gaps shall be documented in the release notes/spec status.

### Chapter check

- Target alignment: **Yes** — speed optimization is subordinate to meaningful hydraulic agreement.
- Do now: data, engine, and Full-vs-Adaptive validation.
- Do later: broader calibration against observed inundation events.
- Permanent non-goal: treating successful program execution as proof of hydraulic accuracy.

---

# 14. Future extensions

## Purpose

Reserve architectural space without expanding v0.1 scope.

## Planned / high-value future extensions

### Sewer and storm-drain coupling

Desired future model concepts:

```text
surface
↕
inlets / manholes
↕
1D drainage network
↕
outfalls / pumps
```

No v0.1 implementation is required.

### Infiltration

Future support may include spatially varying infiltration/land-surface parameters.

### Spatial and forecast rainfall

Potential future data:

- radar rainfall;
- XRAIN;
- nowcast products;
- numerical weather prediction;
- ensembles.

### River/coastal/compound flooding

Possible specialized workflows may add boundary water levels and other flood sources.

### Browser service

A hosted web experience may execute SFINCS server-side while retaining the same product-level model definition.

### Alternative engines

Engine adapters may later support comparison/reference engines, but this shall not complicate the v0.1 UI.

## Future scope rule

A future feature shall be added only if it advances at least one primary goal:

- improves physical usefulness;
- improves accessibility;
- improves coverage;
- improves reproducibility;
- reduces computational cost without unacceptable accuracy loss.

Features should not be added only because the underlying engine supports them.

### Chapter check

- Target alignment: **Yes** — future work is tied to user and modelling value.
- Do now: reserve interfaces and manifest concepts only.
- Do later: sewer, infiltration, spatial rainfall, browser, specialized boundaries.
- Permanent non-goal: feature accumulation without a demonstrated product benefit.

---

# 15. Detailed implementation specification handoff

## Purpose

Make this product specification directly convertible into a low-level implementation plan without forcing the implementer to rediscover intent.

## Rule

The later detailed implementation specification shall be organized by requirement IDs from this document.

For each implementation unit, it should define:

```text
Requirement IDs
Purpose
Inputs
Outputs
External dependencies
Data structures
State transitions
Error cases
Fallback behavior
Logging/diagnostics
Security/licensing constraints
Unit tests
Integration tests
Acceptance condition
Explicitly not implemented
```

## Recommended implementation-spec modules

1. `App shell and project state`
2. `Map and geocoding`
3. `Area geometry`
4. `GSI elevation provider`
5. `PLATEAU provider`
6. `OSM fallback provider`
7. `Terrain processing`
8. `Adaptive grid classifier`
9. `SFINCS subgrid/model writer`
10. `Building obstruction + roof rainfall allocation`
11. `Rainfall catalog and JMA event importer`
12. `SFINCS engine bootstrap and runner`
13. `Result normalization`
14. `Map visualization`
15. `Manifest/cache/project persistence`
16. `Validation harness`

## Low-context implementation rule

Each detailed implementation task should be independently understandable from no more than:

- its own module specification;
- referenced requirement IDs;
- explicitly listed upstream/downstream data contracts.

Do not require the implementer to remember architecture from several unrelated chapters.

## Change-control rule

If an implementation choice conflicts with a product requirement:

1. do not silently change behavior;
2. record the conflict;
3. update this product specification first if the product decision genuinely changes.

### Chapter check

- Target alignment: **Yes** — supports human developers and low-context implementation agents.
- Do now: stable IDs, clear module boundaries, acceptance criteria.
- Do later: write the actual detailed implementation specification.
- Permanent non-goal: implementation-by-guessing from chat history.

---

# 16. Total specification check

## Goal check

### Can a non-specialist understand the primary workflow?

**Yes.** The normal decisions are location, area, rainfall, and accuracy mode.

### Does the design minimize setup?

**Yes.** GSI/PLATEAU acquisition and SFINCS model generation are automated; SFINCS installation is intended to be bootstrapped or packaged compliantly.

### Is accuracy the default priority?

**Yes.** Full 1 m is the reference, and Adaptive is allowed to coarsen only where evidence indicates little hydraulic benefit from finer cells.

### Does Adaptive preserve high-resolution terrain information?

**Yes by design.** Coarse hydraulic cells should use high-resolution source terrain through SFINCS subgrid preprocessing where appropriate.

### Are buildings and roads protected from careless coarsening?

**Yes.** Buildings and important narrow urban flow paths are explicit refinement evidence.

### Can users reproduce meaningful historical-rainfall scenarios?

**Yes.** The design includes JMA-based historical scenarios, while distinguishing equivalent-uniform rainfall from observed temporal profiles.

### Are important omissions visible?

**Yes.** Infiltration, sewer/drain capacity, small drainage structures, uniform rainfall, building interiors, and other omitted processes are explicitly listed and must remain visible in the UI/results.

### Is rainfall mass on roofs intentionally handled?

**Yes.** v0.1 uses mass-conserving redistribution to eligible perimeter ground cells.

### Does the architecture allow future sewer information?

**Yes.** It is deferred but recognized as a future surface/drainage coupling extension.

### Is SFINCS replaceable later without burdening the initial UI?

**Yes.** An internal engine boundary is required, while SFINCS remains the only v0.1 user-visible engine.

### Is the document usable as input to a much more detailed implementation specification?

**Yes.** Stable requirement IDs, module boundaries, acceptance criteria, and scope categories are included.

## v0.1 scope summary

### Do now

- address/coordinate search;
- map-based rectangle and ±250/500/1000/2000 m area selection;
- automatic GSI terrain acquisition;
- PLATEAU-first building/road acquisition with disclosed fallback;
- SFINCS engine integration;
- Full 1 m mode;
- accuracy-first Adaptive mode;
- SFINCS subgrid usage for suitable coarse cells;
- historical rainfall scenarios + custom rainfall;
- spatially uniform rainfall;
- mass-conserving roof-rainfall redistribution;
- explicit limitation warnings;
- maximum depth visualization;
- manifests, caching, and validation against Full 1 m.

### Do later

- infiltration;
- sewer/storm-drain network coupling;
- radar/XRAIN/spatial rainfall;
- operational forecast data;
- river/coastal compound workflows;
- browser-hosted execution;
- alternative hydraulic engines;
- broader observed-event calibration.

### Do not do in v0.1

- manual-GIS-first UX;
- requiring users to construct SFINCS input files;
- property-level damage guarantees;
- detailed building interiors;
- explicit individual curb/gutter/grate networks;
- live warning issuance.

### Permanent non-goals

- replacing official flood warnings or evacuation information;
- claiming deterministic certainty or guaranteed safety;
- hiding modelling limitations or data provenance;
- bypassing external licensing/access restrictions;
- optimizing runtime at the expense of known material hydraulic errors.

## Final assessment

The specification remains aligned with the stated product target:

> **Make arbitrary-location pluvial-flood scenario simulation accessible to ordinary users, while preserving as much useful spatial accuracy as practical and automating the Japanese public-data + SFINCS workflow.**
