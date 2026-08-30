# Model Orchestration

Use this document when work is large enough to benefit from multiple AI roles, repeated review, or delegated repository investigation.

The goal is not to maximize the number of agents. The goal is to separate responsibilities, reduce correlated mistakes, and spend stronger-model capacity only where judgment is required.

## Core Roles

Treat roles as capabilities, not product names.

### Architect / Adjudicator

Responsible for:

- converting requirements into an implementation-ready specification;
- resolving ambiguity and conflicting evidence;
- deciding architecture, invariants, and acceptance criteria;
- evaluating review findings;
- deciding whether work has converged.

Use the strongest reasoning model available for this role when the task is complex or high-risk.

### Lead Repository Agent

Responsible for:

- operating against the actual repository;
- planning source inspection;
- delegating bounded investigation tasks;
- implementing approved changes;
- running build, test, lint, type, static-analysis, and repository-specific checks;
- producing evidence-backed review results.

### Delegated Investigator / Implementer

Use a cheaper or faster model for bounded work such as:

- symbol and reference discovery;
- caller/callee tracing;
- configuration and initialization tracing;
- test discovery;
- repetitive consistency checks;
- mechanical edits with clear acceptance criteria;
- localized implementation work.

The lead agent remains responsible for judging delegated results.

### Blind Reviewer

Performs an independent review without access to previous review conclusions, suspected defects, or proposed fixes.

See `16_blind_review_protocol.md`.

## Default Workflow

For non-trivial work, prefer this flow:

1. **Specify** — turn the request into explicit requirements, invariants, non-goals, affected interfaces, validation criteria, and rollback considerations.
2. **Repository review** — inspect the real source tree and compare implementation reality against the specification.
3. **Adjudicate** — summarize repository findings outside the repository-review context and resolve them against the specification.
4. **Repeat review** — return the revised specification or decisions to the repository agent and repeat until material disagreements are resolved.
5. **Implement** — execute the approved plan in small, reviewable changes.
6. **Verify** — run focused checks first, then broader checks required by risk.
7. **Review the implementation** — inspect the diff and affected execution paths, not only modified lines.
8. **Re-adjudicate** — evaluate findings outside the implementation context when useful.
9. **Repeat until convergence** — do not stop merely because one reviewer reports no issues.

For important work, insert an independent blind review before final convergence.

## Context Separation

Context separation is a deliberate quality control mechanism.

When possible, separate:

- specification authoring context;
- repository-review context;
- implementation context;
- blind-review context;
- final adjudication context.

Do not automatically forward every prior conclusion into the next stage.

Forward facts, requirements, accepted decisions, and evidence that are necessary for the next stage. Withhold prior hypotheses when independence is the purpose of the next stage.

## Delegation Rules

Delegate only when the task can be bounded clearly.

Every delegated task SHOULD specify:

- objective;
- scope;
- evidence to collect;
- output format;
- stop condition.

Prefer neutral investigative prompts.

Good:

> Trace every definition, read, write, configuration path, caller, and consumer of X. Report relevant files, relationships, invariants, and inconsistencies supported by source evidence.

Avoid:

> Confirm that X contains the bug already identified by the reviewer.

Do not delegate final architecture judgment merely to reduce cost.

## Model Selection

Use capability tiers rather than hard-coded model names in project policy.

Suggested mapping:

- **Tier A — deep reasoning:** architecture, adjudication, difficult debugging, final review.
- **Tier B — general engineering:** normal implementation, refactoring, tests, medium-complexity review.
- **Tier C — high-volume investigation:** broad search, cross-reference checks, repetitive validation, mechanical changes.

A concrete toolchain MAY map these roles to specific models. For example, an OpenAI-based workflow may use a high-reasoning model as Tier A and a lower-cost model for Tier C repository exploration. The project rules MUST remain valid if those model names change.

## Review Loop

The repository-review loop SHOULD produce explicit findings with evidence.

For each material finding record:

- severity;
- location;
- affected behavior;
- evidence;
- violated requirement or invariant;
- concrete failure scenario;
- remediation direction;
- confidence.

The adjudication step SHOULD classify every finding as one of:

- confirmed;
- rejected;
- duplicate;
- superseded;
- accepted risk;
- requires further evidence.

If a finding changes the specification or architecture, rerun the relevant repository review instead of assuming the previous review remains valid.

## Implementation Loop

Implementation SHOULD follow the same separation principle:

1. lead agent derives a bounded implementation plan from the approved specification;
2. delegated agents may perform localized work or investigation;
3. lead agent integrates and verifies the result;
4. an independent review checks the resulting diff and affected behavior;
5. material findings return to adjudication;
6. fixes are re-reviewed until convergence.

Do not allow a delegated agent to silently redefine requirements while implementing them.

## Convergence Criteria

A task is not converged merely because an agent says "no issues found".

For non-trivial work, convergence SHOULD require:

- no unresolved Critical or High findings;
- every confirmed finding has a disposition;
- specification inconsistencies are resolved;
- affected source paths and external contracts have been inspected where relevant;
- required build, test, lint, type, and static-analysis checks pass;
- no new unexplained warnings are introduced;
- material validation gaps are closed or explicitly accepted;
- fixes have been checked for secondary regressions;
- a fresh review produces no new material defect requiring redesign.

Repeated restatement of an existing finding is not a new finding.

## Cost Discipline

Use the expensive model for judgment, not for every token of repository traversal.

Prefer:

- targeted search before large reads;
- delegated high-volume discovery;
- focused tests before full suites;
- concise evidence summaries between stages;
- stronger models only for decisions that materially affect correctness.

Do not create extra agents when one focused agent can complete the task with equal confidence.

## Escalation

Add a blind review when any of the following apply:

- architecture or control flow changes materially;
- concurrency, security, persistence, timing, hardware, or irreversible state is involved;
- review iterations repeatedly reveal new High or Critical findings;
- the root-cause hypothesis changed during investigation;
- the affected surface expands beyond the original plan;
- the implementation is substantially rewritten;
- failure would be expensive or difficult to detect.

For exceptionally high-risk work, a reviewer from a different model family or toolchain MAY be used as an additional adversarial check after the normal blind review. Treat that as extra evidence, not automatic authority.

