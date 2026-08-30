# <Specification Title>

> Status: Draft / Ready / Validated
>
> Canonical file/language:
>
> Parent/source-of-truth specification:
>
> Intended implementation-agent context/capability:

## Goal

Describe the user or system outcome.

## Scope

- Included behavior.
- Included interfaces.

## Non-goals

- Explicitly excluded behavior.
- Permanent non-goals where applicable.

## Requirements / Invariants

- Requirement 1.
- Requirement 2.

## Affected Interfaces / Contracts

List public APIs, persistent formats, configuration, hardware interfaces, protocol contracts, or other boundaries that may be affected.

## Approved Tools / Implementation Constraints

For implementation-independent specifications write `Not fixed here`.

For detailed implementation contracts, list exact approved architecture/tool/dependency choices and prohibited substitutions. If a required tool cannot be used, the implementer must stop for specification revision rather than silently replace it.

## Inputs and Outputs

Define units, coordinate systems, schemas, persistence, and consumer/producer boundaries when relevant.

## State / Normal Flow

Define state transitions and the normal processing sequence when stateful behavior exists.

## Errors / Fallbacks / Stop Conditions

State:

- expected failure conditions;
- allowed fallbacks;
- fallbacks that must be disclosed;
- conditions requiring `spec-change-required` rather than implementation improvisation.

## Physical / Numerical Assumptions

For scientific or numerical behavior, list explicit assumptions and omissions separately from software mechanics.

## Acceptance Criteria

Use observable, falsifiable criteria. Include quantitative tolerances when the behavior is numerical.

- Observable criterion 1.
- Observable criterion 2.

## Validation

List the evidence required before implementation can be accepted. Prefer repository-native commands or deterministic checks.

```text
<check command>
```

For low-context implementation work, specify focused tests, integration tests, failure tests, and release gates separately where useful.

## Completion Criteria

Provide a checklist defining exactly when this specification is complete. Passing a single test suite is not sufficient when other contract requirements exist.

## Required Repository Tools

Name project-native discovery/review tools when applicable, for example:

```text
CodebaseMemory
python3 scripts/repo_query.py ...
python3 scripts/analyze.py ...
rg
```

Indexes are evidence aids; source remains authoritative.

## Risks / Rollback

Describe material failure modes, migration concerns, rollback constraints, or state compatibility requirements. Write `None identified` only after considering them.

## Open Questions

- None, or list questions that block repository validation.

A `Ready`/`Validated` implementation contract should not contain an unresolved question that requires the implementer to choose product behavior.
