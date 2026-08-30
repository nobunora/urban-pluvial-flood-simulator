# Repository Review Contract

Review the repository against the supplied specification before implementation.

Specification: `<spec-path>`

## Required Procedure

1. Read `AGENTS.md` first.
2. Read the supplied specification.
3. Use targeted repository search and indexes; do not scan the repository indiscriminately.
4. Trace the affected interfaces, execution paths, tests, configuration, persistence/protocol boundaries, and build paths that materially affect the specification.
5. Compare repository reality with every material requirement and acceptance criterion.
6. Use deterministic evidence such as `repo_query` and `analyze` where applicable.
7. Do not modify production source, tests, configuration, or the specification during this review.

## Required Output

Report:

- disposition: `validated`, `spec-change-required`, or `blocked`;
- affected paths and why they matter;
- relevant existing contracts/invariants;
- specification conflicts or missing constraints;
- missing tests or validation evidence;
- proposed implementation boundary;
- exact repository evidence supporting each material finding;
- commands/checks run and their outcomes;
- unresolved questions.

Do not resolve a specification conflict by silently inventing implementation behavior. Return it for adjudication.

