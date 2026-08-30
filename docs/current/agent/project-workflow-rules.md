# Project Workflow Rules

## Evidence and Scope

- Verify the observed cause before editing.
- Inspect metadata and symbols before broad reads; exclude generated, vendor, cache, build, and artifact paths from ordinary review.
- Do not infer a compatibility, security, money, or external-service contract. Find evidence or ask.

## Source Organization

- Keep entry points thin and put policy in domain modules.
- Start a feature package when two or more modules share a domain model, lifecycle, or change cadence.
- Keep shared utilities dependency-light. Do not create a generic helper without at least two current callers or a stable external contract.
- Before moving a module, inventory imports, CLI entry points, public imports, serialized names, dynamic imports, tests, and monkey-patch targets. A compatibility shim needs an explicit removal condition.
- Retain a flat module when moving it would add shims or indirection without improving discovery or ownership.

## Change Cycle

1. Record the baseline focused test result.
2. Make one behavior-preserving or behavior-intentional patch.
3. Add or update the smallest relevant test when behavior changes.
4. Run focused tests and static checks.
5. Record the evidence and commit the logical unit when the repository workflow allows it.

## Comments and Exceptions

- Explain why a value, fallback, or constraint exists when its intent is not clear from names and types.
- Do not use comments as a substitute for a clear name or a small cohesive function.
- Use `readable-code-audit: skip RULE-ID — concrete reason` only after reviewing the exact finding. Recheck the reason on future audits.


