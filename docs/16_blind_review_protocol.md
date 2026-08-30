# Independent Blind Review Protocol

Use this protocol when a review must provide evidence independent of the primary review's conclusions.

A blind review is not a confirmation pass. It is a separate attempt to reconstruct the relevant behavior, discover defects, and challenge assumptions from the specification and repository itself.

## Independence Rule

At the start of the blind phase, do not request, read, infer, or rely on:

- findings from the primary review;
- suspected defects;
- prior root-cause hypotheses;
- proposed fixes;
- prior severity classifications;
- summaries that reveal what another reviewer considered important.

When practical, start the blind review in a fresh agent context.

If prior findings are already present in context, explicitly disregard them and rebuild the review from source evidence.

The primary and blind reviews SHOULD remain isolated until both have produced final reports.

## Allowed Inputs

A blind reviewer MAY use:

- authoritative requirements and specifications;
- implementation specifications;
- repository-level instructions;
- architecture and interface documentation;
- the current source tree;
- the implementation diff;
- relevant historical code when necessary to understand behavior;
- compiler and build output;
- test results;
- static-analysis output;
- external interface, protocol, hardware, or platform documentation required to judge correctness.

Treat the governing specification as authoritative unless the project explicitly defines another source of truth.

## Review From First Principles

Do not begin from a presumed defect location.

Determine independently:

1. What behavior is required?
2. Which components implement that behavior?
3. Which state, data, control, timing, ownership, and error paths are involved?
4. Which callers, consumers, integrations, and persisted data depend on the behavior?
5. Which invariants must remain true?
6. Which boundary conditions and failure modes exist?
7. What evidence demonstrates that the implementation is correct?

Trace relevant behavior through the repository rather than limiting inspection to modified files.

Inspect callers, callees, shared state, configuration, initialization, cleanup, error handling, tests, and compatibility paths whenever they can materially affect correctness.

## Delegated Investigation

A lead blind reviewer MAY delegate broad repository investigation to cheaper or faster agents.

Appropriate tasks include:

- locating definitions and references;
- finding callers and callees;
- tracing configuration and initialization;
- identifying shared state and ownership;
- locating parallel or duplicated implementations;
- finding related tests;
- enumerating error and cleanup paths;
- checking feature flags or conditional-compilation branches;
- finding stale assumptions after the change.

Delegated prompts MUST remain neutral during the blind phase.

Prefer:

> Trace all code paths that read, write, configure, initialize, or depend on X. Report relevant files, relationships, invariants, and potential inconsistencies supported by source evidence.

Avoid:

> Check whether X has the defect reported by the primary reviewer.

The lead blind reviewer remains responsible for interpretation and severity.

## Required Review Dimensions

Inspect the following where applicable.

### Specification Compliance

- Is every applicable requirement implemented?
- Is any requirement only partially implemented?
- Are assumptions introduced that the specification does not permit?
- Are specified edge cases, limits, and failure modes handled?

### Repository Consistency

- Are all affected callers, consumers, interfaces, schemas, and configurations updated?
- Are parallel implementations left inconsistent?
- Are stale constants, enums, structures, comments, tests, or configuration values retained?

### Control and Data Flow

- Are state transitions valid?
- Are initialization and cleanup complete?
- Are error and recovery paths correct?
- Is data ownership clear?
- Can stale, partial, invalid, or uninitialized state escape?

### Concurrency and Ordering

Where relevant, inspect:

- races;
- lock ordering;
- atomicity;
- memory visibility;
- asynchronous completion;
- callbacks;
- interrupt or task interaction;
- device or resource ownership;
- cancellation and shutdown ordering;
- lifetime hazards.

### Boundary Conditions

Check:

- zero, empty, minimum, and maximum cases;
- overflow and underflow;
- wraparound;
- truncation and conversion;
- buffer boundaries;
- timeout paths;
- partial completion;
- retry exhaustion;
- malformed or unexpected external input.

### Regression Risk

Determine whether behavior outside the directly modified path can change.

Do not assume unchanged files are unaffected.

### Validation Quality

Determine whether existing tests and checks actually prove the required behavior.

Identify missing validation where a defect could survive a clean build or passing test suite.

## Adversarial Requirement

Actively attempt to falsify the implementation.

Do not search only for evidence that the change is correct.

For important assumptions, ask:

- What would make this assumption false?
- Which path violates it?
- Which caller can supply unexpected state?
- Which ordering or timing changes the result?
- Which boundary value breaks the implementation?
- Which requirement is not actually demonstrated by tests?

A clean build and passing tests are evidence, not proof.

## Finding Requirements

Report only findings supported by specification, source, or directly relevant execution evidence.

Do not invent theoretical defects without a plausible execution path.

For every actionable finding include:

1. **Severity**
2. **Location**
3. **Affected behavior**
4. **Evidence**
5. **Violated requirement or invariant**
6. **Concrete failure scenario**
7. **Recommended remediation direction**
8. **Confidence**

Suggested severity levels:

- **Critical** — catastrophic failure, unsafe behavior, unrecoverable corruption, or fundamental specification violation.
- **High** — likely functional failure, major regression, serious concurrency issue, data corruption, or substantial requirement violation.
- **Medium** — real correctness, robustness, maintainability, or validation issue with limited scope.
- **Low** — valid minor issue that does not materially threaten correct operation.

Do not inflate severity.

## Negative Result Requirement

If no actionable defect is found, do not merely state that the implementation looks correct.

Summarize:

- components inspected;
- execution paths traced;
- invariants checked;
- boundary and failure cases considered;
- validation evidence reviewed;
- residual uncertainty or unverified behavior.

A no-finding review must still demonstrate coverage.

## Blind-Phase Output

Produce a standalone report before seeing the primary review.

Use this structure:

### Blind Review Summary

Briefly describe the independently reconstructed behavior and overall assessment.

### Findings

List independently discovered findings in severity order.

### Verified Areas

State which important requirements and paths were checked and found consistent.

### Validation Gaps

List behaviors that cannot currently be proven by source inspection, tests, static analysis, or build evidence.

### Residual Risks

List remaining uncertainty that warrants investigation or explicit acceptance.

### Review Coverage

Identify significant files, components, call paths, state transitions, integrations, or subsystems examined.

## Post-Blind Reconciliation

Only after the blind report is complete may the primary review be introduced.

Classify findings as:

- **Convergent** — independently identified by both reviews.
- **Primary-only** — identified only by the primary review.
- **Blind-only** — identified only by the blind review.

Agreement is not proof. Disagreement is not automatically an error.

Resolve material disagreements by returning to the specification, source, and execution evidence.

For each finding, assign one disposition:

- confirmed;
- rejected;
- duplicate;
- superseded;
- accepted risk;
- requires further evidence.

Run targeted follow-up investigation when evidence remains insufficient.

## Re-Review After Fixes

After implementation changes:

1. verify every confirmed finding was actually resolved;
2. inspect whether the fix changed additional behavior or affected paths;
3. rerun relevant build, test, lint, type, and static-analysis checks;
4. repeat an independent review when the fix is material.

A new blind review is especially appropriate when:

- architecture or control flow changed materially;
- the previous root-cause hypothesis was wrong;
- repeated iterations produced new High or Critical findings;
- the affected surface expanded substantially;
- implementation was substantially rewritten.

## Convergence

Do not declare convergence merely because the latest reviewer reports no issues.

Convergence SHOULD require:

- no unresolved Critical or High findings;
- all confirmed findings have dispositions;
- specification inconsistencies are resolved;
- relevant source paths and external contracts were inspected;
- required verification passes;
- no new unexplained warnings are introduced;
- material validation gaps are closed or explicitly accepted;
- a fresh independent review produces no new material defect requiring redesign.

## Core Rule

**Discover first. Compare later.**

Never bias an independent reviewer with the answer another reviewer already reached.

