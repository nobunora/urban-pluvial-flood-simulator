# <Specification Title>

> Status: Draft / Ready / Validated
>
> Contract shape: standard / specialized-detailed / specialized-ui
>
> Canonical file/language: English
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

Distinguish **required capabilities** from optional repository-local wrappers. A wrapper documented elsewhere but absent from the repository is not a blocker unless this specification explicitly makes that wrapper a prerequisite or deliverable. In that case use the underlying deterministic tool directly and record the substitution.

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

Name required capabilities first. If project-native wrappers exist, name them as preferred interfaces, for example:

```text
CodebaseMemory (when available)
git / rg
CMake / compiler
clang-tidy or project wrapper
language-native test tools
optional: python3 scripts/repo_query.py ...
optional: python3 scripts/analyze.py ...
```

Indexes are evidence aids; source remains authoritative. Do not create unrelated helper infrastructure inside a product feature PR unless the specification explicitly requires it.

## Risks / Rollback

Describe material failure modes, migration concerns, rollback constraints, or state compatibility requirements. Write `None identified` only after considering them.

## Open Questions

- None, or list questions that block repository validation.

A `Ready`/`Validated` implementation contract should not contain an unresolved question that requires the implementer to choose product behavior.

---

## Specialized contract note

A specialized detailed/UI contract may use a numbered structure instead of the standard headings above. For `codex-ready`, it must still explicitly state:

- English canonical/source-of-truth status;
- observable completion criteria;
- explicit non-goals / not-implemented scope;
- validation, tests, acceptance flows, or clear-condition evidence.

Japanese `*.ja.md` reference translations are not required to reproduce English heading names and are excluded from the structural CI gate.
