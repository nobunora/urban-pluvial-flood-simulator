# Chat -> GitHub -> Codex Workflow

Use this workflow when specification work can be separated from repository execution.

The purpose is to keep architecture and requirements explicit in GitHub while reserving repository-agent capacity for source inspection, implementation, and verification.

## Responsibility Split

### Specification / adjudication role

Responsible for:

- clarifying requirements;
- writing and revising specifications;
- defining invariants, scope, non-goals, and acceptance criteria;
- reviewing repository findings;
- deciding whether a specification must change;
- approving the implementation contract.

This role may operate through ChatGPT or another reasoning environment. It does not claim that a design is compatible with the real repository until repository review provides evidence.

### GitHub

GitHub is the shared state and contract layer.

Store:

- approved or proposed specifications under `docs/specs/`;
- repository-review and implementation task records under `docs/implementation/`;
- PR discussion and decisions;
- verification evidence and final disposition.

Do not rely on chat history as the only source of requirements.

### Repository agent / Codex role

Responsible for:

- inspecting the actual source tree;
- comparing repository reality with the specification;
- identifying conflicts, missing constraints, and affected paths;
- implementing only the approved contract;
- running build, tests, lint, type checks, static analysis, and project-specific checks;
- reporting evidence, risks, and unresolved questions.

Repository review must not silently redefine the specification.

## Default State Flow

```text
DRAFT_SPEC
    |
    v
SPEC_REVIEW
    |
    v
SPEC_READY
    |
    v
REPOSITORY_REVIEW
    |
    +---- conflict / missing evidence ----> SPEC_REVISION
    |                                      |
    |                                      +--> SPEC_READY
    v
SPEC_VALIDATED
    |
    v
IMPLEMENTATION
    |
    v
VERIFICATION
    |
    v
IMPLEMENTATION_REVIEW
    |
    +---- material finding ---------------> FIX / RE-VERIFY
    v
READY_TO_MERGE
```

For high-risk work, insert the blind-review protocol from `16_blind_review_protocol.md` before final convergence.

## Phase 1 - Specification PR

Create or update one specification in `docs/specs/`.

A specification must include at least:

- Goal;
- Scope;
- Non-goals;
- Requirements / invariants;
- Affected interfaces or contracts;
- Acceptance Criteria;
- Validation;
- Risks / rollback considerations where relevant.

The specification PR should contain specification work only. Do not mix implementation changes into the same PR unless the task is intentionally trivial.

Use `docs/specs/SPEC_TEMPLATE.md` as the starting point.

## Phase 2 - Mark the Contract Ready

When the specification is ready for repository validation, apply the PR label:

```text
codex-ready
```

`.github/workflows/spec-ready-gate.yml` checks that a `codex-ready` PR changes at least one specification and that the specification contains the required contract sections.

The gate intentionally does not invoke a model. Authentication, model choice, execution environment, and cost policy belong to deployment configuration rather than this language-neutral template.

A Codex, CLI, SDK, or other repository-agent job can be attached after this deterministic gate.

## Phase 3 - Repository Review Before Implementation

The first repository-agent pass is review-only.

Use `.codex/repository-review.md` as the prompt contract.

The agent must:

1. read `AGENTS.md` and the requested specification;
2. inspect the real repository with targeted queries;
3. identify affected files, interfaces, tests, and build paths;
4. compare implementation reality against every material requirement;
5. report conflicts and missing evidence;
6. not modify production code.

Record the result under `docs/implementation/` using `TASK_TEMPLATE.md` or in the specification PR discussion.

Possible dispositions:

- `validated` - implementation may proceed;
- `spec-change-required` - specification must return to adjudication;
- `blocked` - required evidence or environment is unavailable.

Do not start implementation while a material specification conflict is unresolved.

## Phase 4 - Implementation

After repository review validates the contract, use `.codex/implementation.md`.

Implementation rules:

- keep the diff bounded by the approved specification;
- preserve unrelated behavior;
- run focused checks first;
- run broader checks according to risk;
- use `repo_query` and `analyze` where applicable;
- record exact commands and outcomes;
- surface any requirement conflict rather than improvising a new requirement.

Implementation should normally use a separate branch and PR from the specification PR.

## Phase 5 - Review and Convergence

The implementation PR must contain evidence for:

- specification path and revision/commit used;
- affected execution paths;
- checks run;
- failures encountered and their resolution;
- unresolved risks or accepted gaps.

Passing tests are necessary evidence, not proof that the implementation matches the contract.

Review the diff and the affected execution paths. If review discovers a requirement defect rather than an implementation defect, return the issue to specification adjudication.

## Automation Boundary

Automate deterministic transitions first:

```text
spec file changed
    -> contract schema gate
    -> repository review job
    -> review artifact / PR comment
    -> human or adjudicator decision
    -> implementation job
    -> project checks
    -> implementation PR
```

Keep model invocation and write permissions explicit.

Recommended safeguards:

- no model execution on untrusted fork PRs with write-capable secrets;
- least-privilege GitHub permissions;
- review-only repository pass before write-enabled implementation;
- separate specification and implementation branches;
- require deterministic test/static-analysis gates before merge;
- never expose repository or API secrets in prompts or logs.

## Cost Discipline

Use reasoning capacity for decisions and repository-agent capacity for repository work.

Prefer:

- specification and acceptance criteria before repository traversal;
- deterministic `repo_query` for discovery where possible;
- deterministic `analyze` for static checks where possible;
- focused repository review before implementation;
- concise evidence summaries between phases;
- stronger reasoning only for conflicts, architecture decisions, and final adjudication.

See also:

- `10_development_playbook.md`;
- `15_model_orchestration.md`;
- `16_blind_review_protocol.md`;
- `17_repo_index_and_query.md`;
- `18_static_analysis.md`.

