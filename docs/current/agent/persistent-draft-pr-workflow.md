# Persistent Draft PR Workflow for Codex

Use one long-lived GitHub Draft Pull Request as the persistent workspace and communication channel between Web ChatGPT and Local Codex.

The purpose of this workflow is to minimize unnecessary Git operations, repeated repository analysis, duplicated pull requests, and token usage while keeping all implementation decisions and review history visible in GitHub.

## Role split and token-efficiency rule

Web ChatGPT is responsible for analysis, specification, review, acceptance decisions, and writing strict implementation instructions in the persistent Draft PR.

Local Codex is responsible for coding, source/test/generated-asset edits, implementation-time validation, commits, and pushes to the persistent working branch.

This split is deliberate: direct source-level editing through Web ChatGPT consumes substantially more conversation tokens than delegating implementation to Local Codex. Web ChatGPT should therefore normally avoid patching production source code itself and instead spend its token budget on high-value repository review and precise implementation contracts.

Every implementation request posted by Web ChatGPT should be written as an executable contract with minimal room for interpretation. Include, when applicable:

```text
Objective
Canonical spec references
Confirmed findings
Exact required behavior
Known target files/symbols
In-scope work
Explicit non-goals
Error and edge-case behavior
Acceptance criteria
Focused tests
Regression/static/frontend/live checks
Required report format
```

If a PR instruction conflicts with a canonical specification or requires a product/architecture decision that has not been made, Local Codex must not improvise. Report:

```text
spec-change-required
```

with evidence and stop for Web ChatGPT review.

## 1. Core Rule

Do **not** create a new pull request for every implementation iteration.

Instead:

```text
main
  │
  └── persistent working branch
          │
          └── one long-lived Draft PR
```

Local Codex continuously pushes implementation commits to the same working branch.

Web ChatGPT reviews those commits and posts the next instructions as comments on the same Draft PR.

The Draft PR remains open until the entire assigned task is complete and validated.

---

# 2. Persistent Workspace

The repository currently uses:

```text
Working branch:
codex/persistent-workspace

Persistent Draft PR:
PR #12
```

Do not create another implementation PR unless explicitly instructed to abandon or replace this workspace.

Do not merge PR #12 merely because one intermediate task or phase has completed.

---

# 3. Read These Files First

At the beginning of every iteration, read these files before inspecting unrelated repository code:

```text
.ai/HANDOFF.md
.ai/BUG_REPORT.md
.ai/DECISIONS.md
```

Their purposes are:

### `.ai/HANDOFF.md`

Contains the current implementation state.

It should tell you:

* what phases are already validated;
* what task is currently active;
* what remains unfinished;
* the latest important validation results;
* what phase may be started next.

Treat this as the primary repository handoff.

### `.ai/BUG_REPORT.md`

Contains confirmed defects and known risks.

Rules:

* confirmed defects belong under blocking bugs;
* hypotheses must not be presented as confirmed bugs;
* do not fix unrelated items unless the active task requires them.

### `.ai/DECISIONS.md`

Contains durable architectural and product decisions.

Do not reinterpret or silently override these decisions.

If implementation requires changing one of these decisions, stop and report:

```text
spec-change-required
```

unless the active task explicitly authorizes the change.

---

# 4. Read the Draft PR Conversation

After reading `.ai/*`, read the latest relevant conversation comments on the persistent Draft PR.

Web ChatGPT posts implementation instructions there.

The most recent applicable:

```text
## Codex Task
```

comment is the active task contract unless a later comment explicitly replaces or modifies it.

Do not require the task to exist as a committed `.codex/*.md` file.

PR comments are an authoritative communication channel for active implementation tasks.

---

# 5. Do Not Reanalyse the Entire Repository Every Time

Do not restart repository investigation from zero after every commit.

Use this review order:

```text
1. .ai/HANDOFF.md
2. .ai/BUG_REPORT.md
3. .ai/DECISIONS.md
4. latest applicable PR task comment
5. commits since the previous review point
6. changed files
7. directly related implementation/specification files
```

Only expand to broader repository analysis when the latest changes reveal a dependency or conflict that cannot be resolved locally.

Prefer targeted tools such as:

```text
git log
git diff
git show
git status
git grep
rg
pytest <focused tests>
ruff
mypy
```

Use CodebaseMemory when available and useful.

If repository-specific helper tools are unavailable, do not create replacement infrastructure unless the active task requires it.

---

# 6. Implementation Workflow

For each task:

```text
Read handoff
    ↓
Read active PR instruction
    ↓
Inspect latest relevant diff/source
    ↓
Implement only requested scope
    ↓
Run focused tests
    ↓
Run required regression checks
    ↓
Update .ai/HANDOFF.md
    ↓
Commit
    ↓
Push to codex/persistent-workspace
    ↓
Stop and wait for review
```

Do not open a new PR.

Do not merge the Draft PR yourself unless explicitly instructed.

---

# 7. Scope Discipline

Implement only what the current PR task requests.

Do not:

* begin the next phase early;
* refactor unrelated code;
* replace dependencies because you prefer another tool;
* change data semantics without approval;
* change hydraulic assumptions without approval;
* silently introduce fallback behavior;
* add speculative abstractions for future work;
* implement optional features merely because they are convenient.

Preserve previously validated behavior unless the active task explicitly requires a change.

---

# 8. When You Find a Problem

Separate findings into:

```text
Confirmed finding
Hypothesis
```

A confirmed finding must be supported by current code, tests, logs, or reproducible behavior.

Do not treat a hypothesis as a defect until verified.

If a confirmed implementation defect can be fixed inside the active contract, fix it and test it.

If fixing it would require changing the specification, architecture, product behavior, external provider, or phase boundary, stop and report:

```text
spec-change-required
```

Include:

```text
Affected files
Observed behavior
Expected behavior
Evidence
Why the current specification cannot be implemented safely
Recommended decision needed
```

Do not invent the decision yourself.

---

# 9. Testing Rules

Run focused tests before full regression tests.

Typical sequence:

```text
focused unit tests
↓
focused integration tests
↓
pytest -q
↓
ruff
↓
mypy
↓
frontend typecheck/lint/tests/build when relevant
↓
live/provider smoke tests only when required
```

Do not report a check as passing unless you actually ran it successfully.

Distinguish:

```text
PASS
FAIL
BLOCKED
NOT RUN
```

External-service outage must not be reported as PASS.

---

# 10. Update `.ai/HANDOFF.md`

Before pushing the final commit for an iteration, update `.ai/HANDOFF.md` if the implementation state materially changed.

Include:

```text
active phase/task
latest implementation commit
what was completed
what remains
focused test results
regression results
known blockers
next allowed task/phase
```

Keep it concise.

Do not turn `.ai/HANDOFF.md` into a complete development log.

Git history and PR discussion already provide the audit trail.

---

# 11. Update `.ai/BUG_REPORT.md`

Update this file only when appropriate.

Add:

* confirmed blocking defects;
* confirmed non-blocking technical risks relevant to future work.

Do not add:

* speculative concerns;
* ordinary implementation notes;
* resolved temporary failures;
* test output that belongs in the handoff/report.

When a blocking defect is fixed, update its status accordingly.

---

# 12. Update `.ai/DECISIONS.md`

Only add durable decisions.

Examples:

```text
chosen external provider
fixed API behavior
data semantics
phase boundaries
permanent architectural constraints
distribution decisions
```

Do not use this file as a progress log.

A normal implementation detail that follows an existing specification does not need a new decision entry.

---

# 13. Commit and Push Rules

Push implementation work to:

```text
codex/persistent-workspace
```

Use clear commits.

For example:

```text
Implement Phase 2B geocoder provider
Add packaged JMA rainfall catalog APIs
Fix Phase 2B catalog validation
Address PR review findings for Phase 2B
```

Multiple commits are acceptable.

Do not squash merely to make the Draft PR look clean during active development.

The persistent Draft PR is intentionally a working history.

---

# 14. After Pushing

After pushing, stop implementation unless the active task explicitly contains multiple independent stages that must all be completed before review.

Provide a concise report containing:

```text
Commit SHA
Files changed
What was implemented
Tests run
PASS/FAIL/BLOCKED results
Remaining issues
```

Then wait for Web ChatGPT to review the latest diff.

Do not independently start the next phase.

---

# 15. Review Iterations

When Web ChatGPT posts another PR comment:

Do not restart from the repository root.

Instead:

```text
read .ai files
↓
read the new PR comment
↓
identify commits since the previous review point
↓
inspect only affected files
↓
implement requested corrections
↓
test
↓
push
```

Previous PR discussion is part of the active context.

Do not repeat already-resolved investigations unless new evidence requires it.

---

# 16. Merge Rule

The persistent Draft PR must remain Draft while the assigned body of work is incomplete.

Do not recommend merge just because:

* one commit passes;
* one subtask passes;
* one phase implementation appears functional.

Recommend merge only when:

```text
all assigned work is complete
AND
all acceptance criteria pass
AND
required regression tests pass
AND
blocking review findings are resolved
AND
.ai/HANDOFF.md reflects the completed state
```

Web ChatGPT or the user will make the final merge decision.

---

# 17. Communication Format

When reporting back after a Codex iteration, use:

```text
## Codex Result

### Commit
<sha>

### Implemented
- ...

### Validation
- command — PASS
- command — PASS

### Remaining
- none

or

### Blocker
- ...

Disposition:
validated
```

Possible dispositions:

```text
validated
needs-fix
blocked
spec-change-required
```

Use `validated` only when the active task's acceptance criteria have actually been satisfied.

---

# 18. Permanent Workflow Rules

Always preserve these rules:

```text
One persistent Draft PR.
One persistent working branch.
Instructions are strict PR implementation contracts.
Local Codex performs coding and validation.
Implementation is pushed to the same branch.
Web ChatGPT reviews latest changes first.
Web ChatGPT normally does not patch production source directly.
Do not repeatedly reread the entire repository.
Do not create PRs merely to send instructions.
Do not merge intermediate iterations.
Do not start the next phase without review.
Keep .ai handoff state current.
Keep confirmed facts separate from hypotheses.
```

The goal is a low-overhead development loop:

```text
Web ChatGPT
   │
   │ strict PR implementation contract
   ▼
Persistent Draft PR
   ▲
   │ implementation commits + validation
   │
Local Codex
```

Use GitHub as the persistent shared memory and audit trail. Do not depend on chat history alone.
