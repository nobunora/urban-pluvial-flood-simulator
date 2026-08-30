# Detailed Implementation Specification Template

> Status: Template
>
> Use this document when converting `PRODUCT_SPEC_DRAFT.md` into implementation-ready specifications.
>
> The goal is to make each implementation unit understandable without relying on long-term memory of unrelated modules or prior chat history.

---

# 1. Writing rule

One implementation specification should cover **one cohesive responsibility**.

Bad unit:

```text
Implement data downloads, SFINCS execution, UI and result rendering.
```

Good units:

```text
GSI elevation acquisition
PLATEAU building acquisition
Adaptive grid generation
SFINCS model writer
SFINCS process runner
Result normalization
```

Each unit shall reference requirement IDs from `PRODUCT_SPEC_DRAFT.md`.

---

# 2. Mandatory header

Use the following header for every unit.

```markdown
# <Module name>

## Related product requirements

- DATA-001
- DATA-003

## Purpose

One paragraph describing why this module exists.

## In scope

- ...

## Not implemented in this module

- ...

## Future extension points

- ...

## Permanent non-goals

- ...
```

The `Not implemented` section is mandatory even when it contains only one item.

---

# 3. Inputs and outputs

Always define inputs before describing processing.

```markdown
## Inputs

### Input A

Type:
Required/optional:
Units:
Coordinate system:
Validation:
Source:

## Outputs

### Output A

Type:
Units:
Coordinate system:
Persistence:
Consumer:
```

Do not use phrases such as “same as before”, “existing object”, or “usual format” without an explicit reference.

---

# 4. Normal processing

Write the normal path as a short numbered sequence.

```markdown
## Normal flow

1. Validate bounding box.
2. Determine required source tiles.
3. Check cache.
4. Download missing tiles.
5. Validate response.
6. Decode elevation.
7. Mosaic.
8. Reproject.
9. Write processed output and manifest metadata.
```

Keep each step to one action where practical.

---

# 5. State and persistence

If a module stores state, define it explicitly.

```markdown
## State

### Cache state

- key:
- value:
- invalidation condition:
- versioning rule:

### Project state

- field:
- default:
- serialization:
```

If the module is stateless, say so.

---

# 6. Errors and fallback

Every external-data or engine module must include an error table.

```markdown
## Error handling

| Condition | Detection | User-facing result | Internal action | Retry |
|---|---|---|---|---|
| timeout | ... | ... | ... | yes |
| 404/no coverage | ... | ... | ... | no |
| malformed data | ... | ... | ... | no |
```

Fallbacks must never be silent when they affect physical accuracy or data provenance.

---

# 7. Numerical and physical assumptions

Modules that change hydraulic meaning must state assumptions separately from software behavior.

Example:

```markdown
## Physical assumptions

- rainfall is spatially uniform;
- infiltration is not modelled;
- roof rainfall is redistributed with mass conservation;
- building interior storage is not modelled.
```

Do not bury physical assumptions inside implementation notes.

---

# 8. External dependencies

For every external dependency, record:

```markdown
## External dependencies

### Dependency name

Purpose:
Official documentation:
Version policy:
License/terms note:
Network required:
Fallback:
```

For unstable/trial APIs, explicitly define a compatibility boundary.

---

# 9. Tests

Each implementation unit must define tests before implementation begins.

```markdown
## Unit tests

### TEST-<module>-001

Given:
When:
Then:

## Integration tests

### TEST-<module>-INT-001

Environment:
Given:
When:
Then:
Expected artifacts:

## Failure tests

### TEST-<module>-ERR-001

Given:
When:
Then:
```

Numerical modules shall define tolerances rather than using vague words such as “close”.

---

# 10. Acceptance criteria

Acceptance criteria must be observable.

Bad:

```text
Works correctly.
```

Good:

```text
For the fixture dataset, decoded elevations match the expected array within 0.01 m and row 0 corresponds to the documented geographic orientation.
```

If a threshold is not yet decided, mark it explicitly:

```text
TBD-PRODUCT-DECISION
```

Do not invent a threshold simply to complete the document.

---

# 11. Logging and diagnostics

For data, grid, engine and rainfall modules, define diagnostic output.

Minimum useful diagnostics include:

- provider used;
- dataset/version identifier where available;
- input bounds;
- grid/cell counts;
- fallback use;
- mass-balance checks;
- engine version;
- elapsed stage timing for diagnostics;
- failure detail for developers.

User-facing logs and developer logs may have different verbosity.

---

# 12. Security, privacy and licensing

Each network/data module shall answer:

- Does it send user-selected coordinates to an external provider?
- Are addresses stored?
- Are cached files shareable?
- Is attribution required?
- Can binaries/data be redistributed?
- Does authentication exist?
- Are rate limits or service restrictions documented?

Do not automate around authentication or license acceptance restrictions.

---

# 13. Module completion check

End every module specification with this checklist.

```markdown
## Module check

- [ ] Product requirement IDs are listed.
- [ ] In-scope behavior is explicit.
- [ ] Not-implemented behavior is explicit.
- [ ] Future extension points are explicit.
- [ ] Permanent non-goals are explicit where applicable.
- [ ] Inputs and outputs are fully defined.
- [ ] Units and coordinate systems are defined.
- [ ] Normal path is defined.
- [ ] Error/fallback paths are defined.
- [ ] External dependencies and terms are identified.
- [ ] Physical assumptions are visible.
- [ ] Unit/integration/failure tests are specified.
- [ ] Acceptance criteria are observable.
- [ ] The module can be implemented without relying on unrelated chat history.
```

---

# 14. Recommended specification order

Write detailed implementation specifications in this order so downstream modules can reference stable upstream contracts:

1. Project state and common geometry types
2. Map/geocoding and analysis-area model
3. GSI elevation provider
4. PLATEAU provider
5. OSM fallback provider
6. Terrain normalization/cache
7. Rainfall scenario model
8. Roof rainfall allocation
9. Adaptive grid classifier
10. SFINCS model/subgrid writer
11. SFINCS engine bootstrap
12. SFINCS runner
13. Result normalization
14. Visualization
15. Manifest/project persistence
16. End-to-end validation harness

Do not start the UI implementation specification by inventing data structures that should be owned by upstream domain modules.
