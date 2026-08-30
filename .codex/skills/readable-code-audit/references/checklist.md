# Readable Code Audit Checklist

Use these IDs in findings. The checklist synthesizes the four supplied articles and practical Readable Code review habits.

## Naming and contracts

- `NAME-01`: Function names describe the real action and side effects. `get`, `check`, `is`, and `has` must not hide writes or return non-boolean objects.
- `NAME-02`: Variables and parameters reveal meaning, units, collection shape, and state cardinality where the type alone is insufficient. Avoid misleading `flag` names for three-state values.
- `NAME-03`: Comments and names agree with current behavior; stale comments are findings.
- `NAME-04`: Plural names, boolean prefixes, and action verbs reveal the returned shape and operation (`get...Names`, `is...`, `create...`).
- `NAME-05`: Do not use generic placeholders such as `tmp`, `retval`, or `result` when a domain name can reveal the value's role. Do not abbreviate a name when the expansion materially improves comprehension.
- `NAME-06`: Boundary variables use `min_`/`max_`; ordered range endpoints use `first_`/`last_` when those distinctions matter. Do not use a `get...` name for a method that writes, computes, or returns a non-accessor result.
- `NAME-07`: Name types, models, and value objects with nouns; name commands with a verb and, where useful, a noun object; name state predicates with a state adjective or participle (`is_ready`, `password_required`). Apply normal English number forms when they clarify collection cardinality.
- `NAME-08`: Prefer the domain's established vocabulary over implementation or transport vocabulary when naming behavior and values. Preserve externally versioned field names at integration boundaries.
- `NAME-09`: Avoid vague responsibility words such as `Manager`, `Controller`, `Data`, `Info`, `Item`, and `Type` when removing the word or naming the concrete responsibility makes the role clearer. Retain established framework roles and externally defined terms.

## Function and module structure

- `STRUCT-01`: A function or module has one coherent responsibility and can be summarized without “and”. Split mixed validation, transformation, I/O, and persistence when they can evolve independently.
- `STRUCT-02`: High-level orchestration is visible before implementation detail. Long branches should call named helpers so the main flow can be read without scrolling.
- `STRUCT-03`: Related behavior is kept together by feature or domain, not scattered by operation type. Flag difficult-to-find file or code organization.
- `STRUCT-04`: Functions are not vertically or horizontally excessive. Use complexity and comprehension effort, not a rigid line limit.
- `STRUCT-05`: Internal helpers keep their data and responsibility local when sharing broad mutable state would make impact analysis difficult.
- `STRUCT-06`: A public function or class exposes a concise contract (docstring/JSDoc or equivalent) when its behavior is not obvious from types and naming. State caller-handled failure conditions and invalid inputs when they are part of that contract; do not silently convert an error into apparent success.
- `STRUCT-07`: Prefer composition and explicit dependencies to inheritance used only for code reuse. Use inheritance only when the subtype can safely be treated as the base type and the shared contract is intentional.

## Control flow and complexity

- `FLOW-01`: Exceptional paths are handled early; avoid avoidable nesting and `else` after `return`, `break`, or `continue`.
- `FLOW-02`: Nested conditions and loops remain shallow enough to track. Extract a branch when its conditions or body require remembering several outer states.
- `FLOW-03`: Conditions communicate the intended polarity and ordering. Avoid ambiguous booleans, inverted names, and inconsistent comparison direction within the same subsystem.
- `FLOW-04`: Defensive checks exist at the boundary that owns the invariant, not copied at every caller. Preserve checks needed for public or reusable boundaries.
- `FLOW-05`: Prefer early returns for simple ordered classifications when `else` would hide the normal path; keep a branch table when it better preserves the domain rule.
- `FLOW-06`: Use a ternary or conditional expression to select one value only. Do not use chained conditional expressions or short-circuit side effects for control flow; a compact expression is acceptable only when both alternatives are immediately understandable.

## Duplication and abstraction

- `DUP-01`: Do not copy substantial logic that must evolve together. Prefer a shared helper with explicit variation points.
- `DUP-02`: Do not over-generalize one use case. A generic helper is justified by multiple current callers or a stable external contract.
- `DUP-03`: Do not introduce a temporary variable used once unless it names a concept, unit, expensive result, or debugging point; do not inline a value when that would make a chain opaque.
- `DUP-04`: Remove speculative options, unused cases, and future-proof parameters (YAGNI) unless a current requirement or stable external contract needs them.
- `DUP-05`: Prefer a standard-library or established project utility over a local reimplementation when the existing function has the required semantics and does not add an unjustified dependency.
- `DUP-06`: Keep one authoritative expression of a rule or fact across code, comments, documentation, generated artifacts, and operational steps. Keep a duplicate only when it is an explicitly maintained external contract.

## Comments and layout

- `COMMENT-01`: Comments act as a table of contents for non-trivial blocks; separate major steps with meaningful blank lines.
- `COMMENT-02`: The first comment line states What. Additional lines may state Why and How when code cannot express them clearly.
- `COMMENT-03`: Remove commented-out obsolete code and TODOs without an owner or condition. Use version control for history.
- `COMMENT-04`: Explain a non-obvious constant, module-level usage contract, or class usage contract when its meaning cannot be made clear by a name and type alone. Do not add comments that merely restate code.
- `LAYOUT-01`: Avoid long horizontal expressions and dense blocks. Wrap queries, chains, and argument lists at meaningful boundaries.
- `LAYOUT-02`: Keep formatting and control-flow conventions consistent within a module; flag local inconsistency that increases scan effort.
- `SCOPE-01`: Keep mutable state at the narrowest practical scope. Module or class state must represent a deliberate shared cache, configuration, protocol, or lifecycle boundary; do not use it as incidental scratch state.
- `TEST-01`: Test names, setup, assertions, and helpers communicate the behavior under test. Avoid opaque fixture data and assertions that require reading unrelated setup to understand the expectation.
- `TEST-02`: Tests assert an intended domain rule or public contract, not an incidental implementation detail, unless the detail itself is a safety, ordering, or compatibility contract.
- `TEST-03`: Each test is independent and repeatable: it creates or resets the state it needs, does not rely on execution order, current time, network data, or another test unless that dependency is explicitly controlled as part of the test contract.
- `TEST-04`: Keep test flow linear and focused on one behavior. Avoid branches and duplicated production logic in tests; use named test data or a short comment when a non-obvious literal expresses a boundary or domain rule.
- `TEST-05`: When fixing a reported defect, first add the smallest automated test that reproduces the defect and confirm it fails; then fix the code, confirm the new test passes, and run the relevant existing tests. Skip only when a deterministic automated reproduction is impossible, and document the concrete reason and alternative verification.

## Tool feedback

- `TOOL-01`: Treat compiler, linter, type-checker, and test warnings as actionable feedback. Fix the underlying issue or suppress it only with a narrow, reviewed rationale; do not allow repetitive warning noise to hide new problems.

## Review discipline

- `REVIEW-01`: Distinguish readability issues from correctness, performance, security, and style preferences. State the tradeoff.
- `REVIEW-02`: Check external contracts and tests before recommending a rename, extraction, or control-flow change.
- `REVIEW-03`: Report intentional exceptions explicitly instead of forcing a rule mechanically.
- `REVIEW-04`: Check requirements, business/domain rules, and module ownership before recommending a local style change.
- `REVIEW-05`: Phrase findings with humility and respect: state evidence, ask about intent, and separate a suggestion from a correctness defect.
- `REVIEW-06`: Honor a nearby valid `readable-code-audit: skip RULE-ID — reason` comment only after checking that the stated constraint still applies; report the skip and its reason.

## Source

- https://developers.play.jp/entry/2023/12/07/160958
- https://comcent.co.jp/blog/archives/3698/
- https://future-architect.github.io/articles/20190610/
- https://zenn.dev/fuka225/articles/410c9958d18262
- https://qiita.com/kenichi_cc/items/c3ecca7b7d5fc5c6bf2e
- https://qiita.com/AKB428/items/574f94695de51fa1fa19

