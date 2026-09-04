# Bug Report

## Current confirmed blocking bugs

None recorded at workspace initialization.

## Current known risks / non-blocking issues

- External provider availability may change independently of the repository.
- OSM completeness varies by area and must remain disclosed as fallback data.
- SFINCS executable redistribution/bootstrap licensing remains unresolved for later packaging phases.
- CodebaseMemory has intermittently returned `Transport closed`; source code and deterministic repository tests remain authoritative.
- Phase 2B is awaiting validation of the exact Web ChatGPT implementation head; do not treat it as validated until the requested checks pass.

## Reporting rule

Only confirmed defects belong in the blocking-bug section. Hypotheses must be clearly labelled and must not be treated as confirmed until reproduced or supported by the current diff/source/tests.
