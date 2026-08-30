# Project Workflow Rules

- Verify the observed cause before editing and do not infer external contracts.
- Exclude generated, vendor, cache, build, and artifact paths from ordinary review.
- Start a feature package when multiple modules share a domain model, lifecycle, or change cadence.
- Before moving a module, inventory imports, entry points, public imports, serialized names, dynamic imports, tests, and monkey-patch targets.
- Keep a flat module when a move would add compatibility shims without improving discovery or ownership.
- Record baseline tests, make one logical patch, run focused tests and static checks, then record results.

