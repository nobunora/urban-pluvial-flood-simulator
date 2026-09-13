# Persistent Draft PR Workflow for Codex

Use one long-lived GitHub Draft Pull Request as the persistent workspace and communication channel between Web ChatGPT and Local Codex.

## 1. Core rule

Repository workspace:

```text
branch: codex/persistent-workspace
Draft PR: #12
```

Do not create a new PR for every iteration. Keep PR #12 open and Draft until the user explicitly requests merge or the workspace is intentionally retired.

## 2. Current role split

### Web ChatGPT

Web ChatGPT owns:

- repository analysis;
- specification interpretation;
- source-code implementation;
- test/document/generated-asset changes;
- commits and pushes to `codex/persistent-workspace`;
- review and acceptance decisions;
- follow-up fixes after validation failures.

### Local Codex

Local Codex owns only:

- validation/test execution;
- static-analysis execution;
- frontend/build checks;
- live/provider checks when explicitly requested;
- diagnostics and reporting.

Local Codex must not:

- edit source code;
- edit tests;
- edit specifications or documentation;
- regenerate committed assets in place unless the validation instruction explicitly permits a temporary uncommitted output outside tracked paths;
- edit `.ai/*`;
- commit;
- push;
- create branches or PRs;
- merge PR #12.

This validation-only role supersedes the earlier `Workflow Override — Codex Owns Implementation` instruction.

The previous delegation of coding to Codex was based on a mistaken diagnosis of high token consumption. The user identified the actual cause as Local Codex running the Sol model. Local Codex has now been switched to Luna, so Web ChatGPT source editing is restored as the normal implementation path.

## 3. Read first

At the start of a validation iteration, read:

```text
AGENTS.md
.ai/HANDOFF.md
.ai/BUG_REPORT.md
.ai/DECISIONS.md
latest applicable PR validation comment
```

Do not restart repository analysis from zero.

Use this order:

```text
1. current handoff/decisions
2. exact validation request
3. exact named commit
4. diff since previous validated/reviewed point
5. files directly related to requested checks
```

Only broaden investigation when a confirmed failure requires it.

## 4. Exact-commit validation

Web ChatGPT will name the exact commit to validate.

Local Codex must verify:

```text
git rev-parse HEAD
```

matches the requested SHA before reporting results.

Use a clean/disposable worktree when requested or when prior checks may have changed tracked/generated files.

## 5. Testing rules

Run only the checks requested by Web ChatGPT. Typical checks may include:

```text
focused pytest
full pytest
ruff
mypy
OpenAPI/generated-contract drift checks
frontend typecheck/lint/Vitest/build
repository cleanliness checks
live/provider smokes
```

Distinguish exactly:

```text
PASS
FAIL
BLOCKED
NOT RUN
```

Do not report a check as PASS unless it was actually run successfully.

External-service outages are `BLOCKED` or `FAIL` as appropriate, never PASS.

## 6. Failure reporting

Separate:

```text
Confirmed failure
Hypothesis
```

A confirmed failure must be supported by command output, logs, current source, or reproducible behavior.

When a check fails, report:

```text
command
exit status
relevant diagnostic/log excerpt
affected file/function if known
expected behavior
observed behavior
whether failure is deterministic
```

Do not fix the failure. Web ChatGPT owns corrections.

If a problem appears to require changing canonical product/spec behavior, report:

```text
spec-change-required
```

with evidence rather than improvising.

## 7. Repository immutability during Codex validation

Validation should leave tracked repository state unchanged.

When relevant, finish with:

```text
git diff --exit-code
git diff --cached --exit-code
git status --short
```

If a normal requested validation command changes tracked files, report that as a failure or diagnostic. Do not restore/rewrite/commit the files unless Web ChatGPT explicitly asks for a separate investigation action.

## 8. Report format

Use:

```text
## Codex Validation Result

### Commit
<exact sha>

### Checks
- <command/check> — PASS/FAIL/BLOCKED/NOT RUN — details

### Repository cleanliness
- tracked diff — CLEAN/NOT CLEAN
- Codex repository changes — none

### Confirmed failures
- none / exact failures

### Hypotheses
- none / clearly labelled hypotheses

Disposition recommendation: validated | needs-fix | blocked | spec-change-required
```

Codex's disposition is a recommendation. Web ChatGPT makes the final acceptance decision.

## 9. Phase progression

Local Codex must not independently begin the next phase.

Flow:

```text
Web ChatGPT implements
        ↓
Web ChatGPT pushes exact commit
        ↓
PR validation comment names SHA/checks
        ↓
Local Codex validates only
        ↓
Local Codex reports
        ↓
Web ChatGPT accepts or fixes
```

## 10. Permanent workspace rules

Always preserve:

```text
One persistent Draft PR.
One persistent branch.
Web ChatGPT owns implementation and repository writes.
Local Codex is validation/reporting only.
Validate exact named commits.
Review latest relevant state first.
Do not repeatedly reread the whole repository.
Do not create new PRs merely for iterations.
Do not merge without explicit user direction.
Keep confirmed facts separate from hypotheses.
```

Use GitHub as the persistent shared memory and audit trail. Do not depend on chat history alone.
