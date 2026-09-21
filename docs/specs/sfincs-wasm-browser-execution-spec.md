# Browser-side SFINCS WebAssembly Execution Specification

> Status: Draft
>
> Contract shape: standard
>
> Canonical file/language: English
>
> Parent/source-of-truth specification: `docs/PRODUCT_SPEC_DRAFT.md` for current product behavior. This document defines a future execution/distribution architecture and does not override current validated Full 1 m or future Adaptive behavior until explicitly promoted.
>
> Intended implementation-agent context/capability: Product/architecture planning first. Detailed implementation work is intentionally deferred until Adaptive is completed and validated.

## Goal

Provide a browser-based SFINCS execution path in which a user can open the public web application, configure and run an urban pluvial flood simulation without installing a native executable, while the hydraulic calculation consumes the user's local CPU rather than the public server's CPU.

The target experience is:

```text
Open URL
  -> prepare/input simulation data
  -> load precompiled SFINCS WebAssembly
  -> run calculation in the browser
  -> display progress and results
```

The public server should primarily serve static application assets, WebAssembly binaries, metadata, and required data/cache responses. It should not be the default hydraulic-computation host.

## Scope

This specification covers the future product and runtime architecture for:

- a minimal SFINCS-derived solver build compiled to WebAssembly;
- delivery of a precompiled `.wasm` binary to the browser;
- browser-local hydraulic execution using the user's CPU;
- execution outside the UI main thread;
- future multi-threaded browser execution where supported;
- source/build traceability for distributed binaries;
- compatibility with the existing React/MapLibre user experience;
- a migration path from the current FastAPI -> Python -> native `sfincs.exe` execution model.

The intended target architecture is:

```text
Public web host
  |
  +-- HTML / CSS / JavaScript
  +-- application assets
  +-- sfincs.wasm
  +-- worker bootstrap
  +-- data/cache endpoints as required
          |
          v
Browser
  |
  +-- React / MapLibre UI
  +-- Web Worker
  |     |
  |     +-- precompiled SFINCS-WASM
  |     +-- simulation memory
  |     +-- progress/cancellation bridge
  |
  +-- optional shared memory / WASM threads
          |
          v
User CPU
```

## Non-goals

The following are explicitly outside the current specification:

- implementing SFINCS-WASM now;
- defining the detailed Fortran-to-WASM toolchain now;
- selecting exact SFINCS source files now;
- defining the final JS/WASM ABI now;
- defining exact TypedArray layouts now;
- defining exact worker message schemas now;
- adding a GitHub Actions WASM build workflow now;
- enabling or changing Adaptive-grid behavior;
- replacing or redesigning current hydraulic physics;
- changing rainfall, terrain, building-mask, roughness, boundary, or result semantics;
- redistributing Deltares-provided precompiled SFINCS executables;
- requiring end users to compile SFINCS or WebAssembly;
- requiring end users to install Python, Docker, a browser extension, a native messaging host, or a local SFINCS executable.

A detailed implementation specification MUST NOT be authored as an authoritative implementation contract until Adaptive is completed and validated.

## Requirements / Invariants

### WASM-REQ-001 — Precompiled delivery

End users MUST receive an already compiled WebAssembly binary. Normal user execution MUST NOT require compilation in the browser.

Expected runtime flow:

```text
source/build system
  -> precompiled sfincs.wasm
  -> web distribution
  -> browser download/cache
  -> browser execution
```

### WASM-REQ-002 — Browser-local computation

Hydraulic time stepping MUST execute on the user's device when the WASM path is selected.

The public application server MUST NOT be the normal CPU host for the SFINCS calculation in this architecture.

### WASM-REQ-003 — No native installation requirement

The normal browser flow MUST NOT require users to install or manually launch:

- `sfincs.exe`;
- Python;
- Docker;
- a browser extension;
- a native helper application;
- a native messaging host.

### WASM-REQ-004 — UI isolation

Long-running hydraulic execution MUST NOT run synchronously on the browser UI/main thread.

The architecture MUST provide a worker-based execution boundary so that, during a run, the application can continue to support at least:

- progress presentation;
- cancellation requests;
- UI rendering;
- map interaction where practical;
- failure reporting.

### WASM-REQ-005 — Parallel execution capability

The design SHOULD permit multi-core execution where supported by the browser and selected WASM toolchain.

If shared-memory WASM threads are used, deployment MUST satisfy the browser security/isolation requirements needed for shared memory, including appropriate cross-origin isolation policy.

Single-thread execution MAY remain as a compatibility fallback if explicitly defined by the later implementation specification.

### WASM-REQ-006 — Minimal solver target

The WASM build SHOULD contain only the SFINCS functionality needed by this product, subject to correctness and maintainability.

The presently expected minimum functional set is:

- regular Full 1 m grid support;
- future accepted Adaptive support when this architecture is implemented;
- terrain elevation;
- building mask / obstacle treatment;
- Manning roughness;
- rainfall forcing;
- product-defined outer-boundary policy;
- time stepping;
- water-depth time series;
- maximum water depth;
- u/v velocity output;
- progress;
- cancellation;
- CPU parallelism where supported.

Features not required by the product SHOULD remain excluded from the minimal build unless later requirements add them.

Candidate exclusions include, subject to source/dependency analysis:

- unrelated wave functionality;
- wind forcing;
- salinity;
- temperature;
- sediment;
- morphology;
- unrelated external coupling;
- unused output formats.

The later implementation specification must determine the exact dependency closure. This document does not authorize deleting source modules based on assumption alone.

### WASM-REQ-007 — File-I/O minimization

The future implementation SHOULD minimize browser-side dependence on desktop-style filesystem I/O.

Where practical, simulation inputs SHOULD be passed through an explicit memory-oriented interface rather than requiring native-style NetCDF/HDF5 file workflows inside the browser.

Candidate mechanisms include:

- TypedArray;
- WebAssembly linear memory;
- SharedArrayBuffer where applicable;
- OPFS/cache only where persistence is materially useful.

Exact formats and interfaces are deferred.

### WASM-REQ-008 — Numerical equivalence

The WASM solver MUST preserve the accepted SFINCS/product hydraulic semantics.

Migration to WASM MUST NOT silently alter:

- rainfall forcing;
- terrain interpretation;
- building obstacle semantics;
- roughness;
- boundary policy;
- wet/dry treatment;
- depth normalization;
- velocity semantics;
- result validity rules.

The detailed implementation specification must define deterministic comparison tests between an accepted native reference path and WASM results, including explicit numerical tolerances.

### WASM-REQ-009 — Existing UI continuity

The browser-local execution architecture SHOULD preserve the current high-level product flow and RESULT capabilities unless a separate product requirement changes them.

The migration SHOULD keep the frontend responsible for user interaction and visualization while replacing the hydraulic execution location.

Conceptually:

```text
Current:
Browser -> FastAPI -> Python -> native sfincs.exe -> server/local host CPU

Target:
Browser -> Web Worker -> sfincs.wasm -> user CPU
```

### WASM-REQ-010 — Build traceability

Every distributed WASM build MUST be traceable to its source and build inputs.

At minimum, release/build metadata must identify:

- upstream SFINCS source revision;
- product repository revision;
- applied modifications/patches;
- build-system revision;
- compiler/toolchain version;
- build mode/options relevant to numerical behavior;
- resulting WASM artifact version or checksum.

### WASM-REQ-011 — Licensing and source availability

Before public distribution, the project MUST re-verify the applicable upstream SFINCS license and all linked/runtime dependency licenses against the exact source revision and build composition.

The project MUST NOT redistribute a Deltares-provided precompiled SFINCS executable as part of this browser architecture.

If the distributed WASM build is derived from GPL-licensed SFINCS source, distribution MUST satisfy the applicable GPL source, notice, modification, and corresponding-source obligations.

All libraries linked into the distributed WASM artifact MUST be checked for license compatibility before release.

This specification is an engineering requirement and not legal advice.

### WASM-REQ-012 — Build location is not a user requirement

The WASM artifact MAY be compiled:

- on a developer machine;
- in GitHub Actions;
- in another controlled CI/build environment.

GitHub Actions is an automation/reproducibility option, not a runtime requirement.

The required user-facing property is that the browser receives a precompiled artifact.

### WASM-REQ-013 — Reproducible CI is preferred

When implementation begins, CI SHOULD build and validate the WASM artifact from pinned source/toolchain inputs where technically practical.

A future GitHub Actions workflow MAY own:

- toolchain setup;
- minimal solver build;
- WASM linking;
- deterministic tests;
- native-vs-WASM comparison;
- browser smoke/integration tests;
- artifact publication;
- release/deployment gates.

Exact workflow files and triggers are deferred to the detailed implementation specification.

### WASM-REQ-014 — No premature implementation

Until Adaptive is completed and validated:

- this specification remains planning-level;
- no detailed source-file manifest is authoritative;
- no compiler/toolchain is authoritative;
- no WASM ABI is authoritative;
- no build workflow is authoritative;
- implementation agents MUST NOT treat discussion notes as approval to begin the WASM migration.

## Affected Interfaces / Contracts

Potentially affected in the future:

- simulation execution boundary;
- run lifecycle and progress transport;
- cancellation path;
- simulation input representation;
- result transfer from solver to frontend;
- cache/persistence behavior;
- browser deployment headers;
- deterministic CI;
- release packaging;
- licensing/source-distribution documentation.

Current public APIs and validated native execution contracts remain unchanged until an implementation specification explicitly defines and validates a migration.

## Approved Tools / Implementation Constraints

Not fixed here.

The future implementation specification must evaluate and explicitly select:

- the Fortran/WASM compiler path;
- linker/runtime approach;
- handling of OpenMP or replacement threading;
- NetCDF/HDF5 retention, replacement, or elimination;
- JS/WASM memory interface;
- worker architecture;
- browser storage/cache strategy;
- cross-origin isolation deployment policy;
- CI/build/release workflow.

Candidate technologies may be investigated, but this product specification does not approve any specific candidate.

## Inputs and Outputs

At product level, the WASM path must consume the same accepted simulation concepts as the native path, including:

- analysis grid/domain;
- terrain;
- building mask/obstacles;
- roughness;
- rainfall forcing;
- boundary policy;
- run timing.

It must produce enough information to preserve accepted RESULT behavior, including:

- water-depth time series;
- maximum water depth;
- u/v velocity;
- simulation timing/progress;
- success/failure/cancellation state;
- provenance needed for result auditing.

Exact binary memory formats are deferred.

## State / Normal Flow

Target normal flow:

```text
1. User opens application
2. Frontend prepares simulation inputs
3. Browser obtains/caches the precompiled WASM artifact
4. Frontend creates a Web Worker
5. Worker initializes the solver
6. Input data is transferred/shared to the worker/WASM runtime
7. Solver runs on user CPU
8. Worker reports progress
9. User may request cancellation
10. Solver returns normalized result data
11. Frontend renders existing result views
12. Run provenance records the WASM build/source identity
```

## Errors / Fallbacks / Stop Conditions

The later implementation specification must define explicit behavior for at least:

- WASM load failure;
- unsupported browser capability;
- insufficient memory;
- worker startup failure;
- shared-memory/thread initialization failure;
- runtime solver failure;
- cancellation;
- corrupted/incompatible cached WASM;
- source/result version mismatch.

A fallback to server-side hydraulic computation MUST NOT be silent.

If a native/server fallback is ever offered, the UI must disclose the execution mode because it changes where CPU resources are consumed.

If numerical equivalence cannot be demonstrated within the later accepted tolerance, the WASM path MUST NOT replace the accepted native execution path.

If the selected compiler/runtime requires an incompatible license or cannot support required solver behavior, implementation must stop with `spec-change-required` rather than silently substituting physics or numerical semantics.

## Physical / Numerical Assumptions

This architecture specification does not change the product's hydraulic model.

All physical and numerical assumptions remain governed by the existing accepted SFINCS/product specifications until superseded by an explicit specification revision.

WASM is an execution/distribution target, not permission to simplify or approximate the physics.

## Acceptance Criteria

This planning specification is satisfied when all of the following are true:

- the repository contains this future browser-local execution contract;
- the target architecture explicitly uses precompiled WASM delivered to the browser;
- user CPU execution is the stated default objective;
- no native installation is required by the target UX;
- worker isolation is required for heavy computation;
- multi-core browser execution is preserved as a target capability;
- licensing/source traceability is explicitly required;
- exact compiler, ABI, source-file subset, and CI workflow remain deferred;
- the detailed implementation specification is explicitly gated on Adaptive completion/validation;
- current native/Full 1 m behavior is not modified by this document.

## Validation

No code validation is required for this planning-only document.

Before this specification can be promoted from Draft to implementation-ready, repository review must verify that:

1. Adaptive has completed its canonical implementation and acceptance gates.
2. The accepted native SFINCS path and reference cases are available for numerical comparison.
3. The exact upstream SFINCS source revision and license are identified.
4. Candidate WASM toolchains have been technically evaluated against the required source/dependency closure.
5. Browser memory and threading constraints have been measured against representative product workloads.

## Completion Criteria

This specification is complete as a product/architecture planning contract when:

- [x] target user experience is defined;
- [x] browser-local CPU execution is defined;
- [x] precompiled WASM distribution is defined;
- [x] worker isolation is defined;
- [x] multi-threading remains an explicit target;
- [x] minimal-solver intent is recorded;
- [x] numerical-equivalence requirement is recorded;
- [x] source/build traceability is recorded;
- [x] licensing constraints are recorded;
- [x] GitHub Actions is identified as optional build automation rather than a user/runtime dependency;
- [x] detailed implementation work is deferred;
- [ ] Adaptive implementation is completed and validated;
- [ ] repository/source dependency investigation is completed;
- [ ] detailed SFINCS-WASM implementation specification is authored and approved.

## Required Repository Tools

For the future implementation phase, required capabilities are expected to include:

```text
CodebaseMemory (when available)
git / rg
Fortran/source dependency inspection
selected compiler/linker toolchain
native reference SFINCS validation
language-native tests
browser integration tests
GitHub Actions or equivalent deterministic CI
```

Exact commands and wrappers are intentionally deferred.

## Risks / Rollback

Material risks include:

- unsupported or incomplete Fortran-to-WASM compiler behavior;
- NetCDF/HDF5 or other native dependency incompatibility;
- browser memory limits on large grids;
- performance loss relative to native SFINCS;
- browser threading/security-header constraints;
- numerical drift caused by compiler/runtime differences;
- dependency-license incompatibility;
- excessive WASM download size;
- inability to preserve required Adaptive behavior.

Rollback requirement:

The accepted native execution path must remain available during WASM development and validation until the WASM path independently passes its future acceptance gates.

## Open Questions

These questions are intentionally deferred until Adaptive is complete:

1. Which SFINCS source modules form the exact required dependency closure?
2. Can the required solver path remain in Fortran, or does a component require porting?
3. Which Fortran/LLVM/Emscripten-compatible toolchain is viable for production?
4. Can NetCDF/HDF5 be removed from the browser runtime completely?
5. What is the final JS/WASM ABI and memory layout?
6. How will OpenMP behavior map to browser WASM threads?
7. What representative grid sizes fit browser memory limits?
8. What numerical tolerance is acceptable for native-vs-WASM equivalence?
9. What artifact size and startup-time limits are acceptable?
10. Which deployment host will provide the required isolation headers?
11. What exact CI/release workflow should build and publish the WASM artifact?

These open questions do not authorize implementation-agent choices. They are inputs to the future detailed implementation specification after Adaptive completion.
