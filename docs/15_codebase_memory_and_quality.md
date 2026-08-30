# CodebaseMemory and Quality Audit

## Graph-Guided Investigation

Use CodebaseMemory to narrow code exploration before a design or implementation decision. Check index health, then inspect the target symbol, callers, callees, tests, and boundary. Verify graph results with focused source reads and `rg`.

Graph signals are not proof. An unused-node candidate, low-confidence call, similarity score, or semantic relation must be checked against direct and dynamic references, compatibility seams, tests, current contracts, and history before changing code.

Do not change readable production code solely to improve graph resolution. Record or report graph false positives separately, especially for builtins, external SDKs, test fakes, and intentional dynamic dispatch.

If the repository tracks a shared graph artifact, treat it as a derived snapshot of the latest source-bearing commit. Regenerate it once after source or active-rule changes, add it as the final generated commit, and do not create an artifact-only refresh loop.

## Quality-Audit Decision Rules

Run independent applicable checks before tests: lint, import/architecture boundaries, type checks, dependency-use checks, and JS/TS checks. A failed tool is a diagnostic, not automatic permission to rewrite code.

For each finding, classify it as a verified defect, safe cleanup, compatibility boundary, tool/configuration gap, or insufficient evidence. Fix only verified defects and safe cleanups; then rerun the reporting tool and focused tests.

Use the project interpreter for type checks. Map package distributions to actual import names before judging dependency findings. Report existing advisory debt separately from diagnostics caused by the current change.

