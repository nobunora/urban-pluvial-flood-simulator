# Code Review

## Post-Implementation Self-Review

- Does the change satisfy the request?
- Did any out-of-scope change slip in?
- Does the code match the existing design?
- Are the names specific?
- Are responsibilities mixed?
- Is there unnecessary abstraction?
- Is there unnecessary duplication?
- Is exception handling appropriate?
- Are there any security-risky changes?
- Does any debug code remain?
- Does any unused code remain?
- Do comments explain the reason where needed?
- Are the tests sufficient?
- Is the diff easy for a human to review?
- Can the change still be understood in six months?

## Pre-Implementation Review

- Is the change purpose clear?
- Is the change target clear?
- Is the scope that will not change clear?
- Can the change be explained in terms of the existing design?
- Are there any unknowns that should be confirmed first?

## Existing Behavior Review

If behavior changed, identify:

- what changed
- affected users, inputs, persisted data, APIs, integrations, and tests
- whether rollback is feasible
- what requires human confirmation

## Independent Review

For non-trivial or high-risk changes, do not rely only on the implementing agent's self-review.

Use `15_model_orchestration.md` when multiple review or implementation roles are involved.

Use `16_blind_review_protocol.md` when an independent review must not inherit the primary review's conclusions or hypotheses.

A review with no findings must still state what was inspected, which paths and invariants were checked, and what remains unverified.

## Review Convergence

Do not treat "no issues found" as sufficient evidence of convergence.

For non-trivial changes, verify that:

- no unresolved Critical or High finding remains;
- confirmed findings have explicit dispositions;
- specification and source agree;
- relevant checks pass;
- material validation gaps are resolved or explicitly accepted;
- a fresh review does not reveal a new material defect requiring redesign.

## Final Report Review

- Change summary
- Design intent
- Alignment with the existing design
- Alternatives and why they were not chosen
- Files changed
- Scope not changed
- Tests
- Points a human should confirm
- Remaining risks
- If behavior changed, explicitly name the affected inputs, users, or APIs.

