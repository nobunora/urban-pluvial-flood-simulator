# Implementation Contract

Implement the supplied validated specification against the actual repository.

Specification: `<spec-path>`
Implementation record: `<implementation-record-path>`

## Preconditions

- Read `AGENTS.md` first.
- The repository-review disposition is `validated`.
- Material specification conflicts are resolved.

If a precondition is false, stop implementation and report the blocker.

## Required Procedure

1. Confirm the current repository state still matches the repository-review assumptions.
2. Derive the smallest reviewable implementation plan from the approved specification.
3. Keep changes inside the approved scope.
4. Preserve unrelated behavior and public contracts unless the specification explicitly changes them.
5. Run focused tests/checks near the changed code first.
6. Run broader build, test, lint, type, and static-analysis gates according to project rules and risk.
7. Inspect the final diff and affected execution paths.
8. Update the implementation record with evidence.

## Stop Conditions

Stop and return to specification adjudication if:

- repository reality materially contradicts the validated specification;
- implementation requires an unapproved public/API/data-format change;
- a required external contract cannot be verified;
- the affected surface materially expands beyond the approved boundary.

## Required Final Report

Report briefly:

- changed files and reasons;
- checks run and outcomes;
- specification criteria satisfied;
- residual risks;
- unresolved questions;
- whether the implementation is ready for independent review.

