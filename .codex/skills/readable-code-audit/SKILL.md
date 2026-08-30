---
name: readable-code-audit
description: Audit and report refactoring opportunities in Python, JavaScript, TypeScript, PowerShell, shell, HTML, CSS, SQL, and configuration source using a practical Readable Code checklist. Use when reviewing a whole repository or a selected codebase for naming, structure, complexity, duplication, comments, control flow, and consistency issues before refactoring.
---

# Readable Code Audit

Audit first; do not refactor unless the user explicitly asks for implementation. Apply the checklist in `references/checklist.md` to every in-scope source file, while excluding generated, vendored, cache, build, and artifact files. Also verify module ownership, public contracts, and whether extra flexibility is justified by a current requirement. Preserve existing behavior and report uncertainty instead of guessing domain intent.

## Workflow

1. Read repository instructions and identify the source file set with `rg --files`.
2. Record language, module, and file boundaries before judging style. Do not treat tests, generated files, or deployment manifests as ordinary application code.
3. Inspect each file for checklist findings. Use AST or parser-based checks when available; use focused text searches for comments, long lines, nesting, duplicate blocks, and suspicious names.
4. Classify each finding as `must-fix`, `should-fix`, or `consider`. Do not report a rule violation when the code is intentionally constrained by an external contract, protocol, schema, or safety boundary; record that rationale as an exception and add a local skip comment when the exception is intentional.
5. Report every finding with file, line, rule ID, evidence, impact, and a small refactoring direction. Group repeated findings, but keep representative line references for every affected file.
6. Run focused tests or static checks relevant to the inspected files. A readability audit must not claim that behavior is safe without verification.

## Decision rules

- Prefer names that reveal the returned value, units, side effects, and allowed states; do not add redundant type suffixes where the language already makes the type obvious.
- Reject placeholder or unexplained abbreviated names when a domain term is available. Check boundary and range names, English part-of-speech, and whether `get...` conceals computation or mutation. Preserve external field names only at their contract boundary.
- Prefer early returns for exceptional paths and shallow nesting, but retain `else` when it expresses mutually exclusive normal alternatives or changing it would obscure the invariant.
- Extract a function when it has multiple responsibilities, a branch hides a substantial operation, or its name would need “and”; do not split cohesive, short code merely to reduce line count.
- Flag copy-paste logic only when behavior must stay synchronized. Similar code with deliberately different contracts is not automatically duplication.
- Flag one-off variables only when the name adds no meaning and inlining remains readable; keep a variable when it documents a domain concept, unit, expensive computation, or debugging boundary.
- Comments should explain intent, constraints, or non-obvious tradeoffs. The first line should state what the block does; follow with why/how only when needed. Remove stale, commented-out code rather than preserving it as history.
- Use blank lines and local grouping to expose the top-level steps of a function. Avoid cosmetic reformatting unrelated to a finding.
- Review conditional expressions and short-circuit expressions for hidden side effects. Use a conditional expression only for simple value selection; prefer a named branch when either arm is non-trivial.
- Check that shared mutable state represents an intentional cache, configuration, protocol, or lifecycle boundary. Prefer existing standard-library or project utilities over duplicate local implementations.
- Review tests as source: each test should reveal its scenario and expected behavior without opaque setup, and should test a domain rule rather than an incidental implementation detail unless that detail is an explicit contract.
- Prefer the narrowest abstraction that serves current callers. Do not propose generic frameworks, wrappers, or configuration layers without at least two real use cases.
- Review from the perspective of a new maintainer with no undocumented domain context. Verify requirements and domain constraints before judging a “clean” implementation.
- Prefer minimal inputs and explicit return shapes for helpers. Keep internal data and helper responsibilities local when that reduces accidental coupling.
- Treat YAGNI as a review rule: unused options, speculative branches, and future-proof parameters need a current caller or documented contract.
- Use a consistent, respectful tone in findings. Ask what constraint motivated surprising code before labeling it wrong.

## Output format

Start with a short scope and methodology statement. Then provide:

- summary counts by severity and rule;
- findings grouped by file or subsystem, with exact line references;
- intentional exceptions and why they are acceptable;
- prioritized refactoring sequence;
- checks run and remaining uncertainty.

Do not modify source during an audit unless the user separately requests refactoring.

## Skip comments

When a finding is reviewed and intentionally retained, add a nearby language-appropriate comment in this exact form:

`readable-code-audit: skip RULE-ID — reason`

Examples: `# readable-code-audit: skip STRUCT-04 — Firestore and SQL adapters must keep separate transaction code` or `// readable-code-audit: skip NAME-02 — provider payload is an external JSON contract`.

The reason is required and must describe the concrete contract, safety, performance, or domain constraint. A bare `skip` or a generic “intentional” is invalid. A skip applies only to the nearest matching finding in that file/block, not to the whole repository. During later audits, honor valid skip comments, report them under “intentional exceptions,” and re-check that the reason still matches the code.

