# AGENTS.md

Keep context small and act from evidence.

## Core Rules

- Read this file first.
- Do not scan all docs or all source files.
- Start with metadata: `git status --short`, shallow directory listings, and `rg --files`.
- Use `rg` to find the target before opening files.
- Open only the relevant index, file, and line range.
- Full-file reads are allowed only for short files or when structure is required.
- If broader reading is needed, state why before doing it.
- Follow existing design, names, boundaries, and error handling.
- Do not guess specs, compatibility, security, or external contracts. Verify or ask.
- Do not rename public APIs, DB fields, env keys, or integration fields unless required.
- Keep one main responsibility per file or function.
- Keep diffs small and focused. Do not mix feature work, refactoring, and formatting in one change.
- Do not leave debug code, commented-out code, or temporary bypasses behind.
- Do not add new dependencies unless the need, maintenance cost, and risk are clear.
- Report briefly: changed files, reason, checks run, risks, and open questions.
- A repository-local helper described in docs is not automatically a prerequisite. If a documented wrapper such as `scripts/repo_query.py` or `scripts/analyze.py` is absent, record that fact and use the underlying deterministic tools (`git`, `rg`, CMake, clang/clang-tidy, language-native test tools) unless the approved task specification explicitly requires the wrapper itself to exist. Do not stop product work merely to build optional developer infrastructure.

## CodebaseMemory

- Before proposing or implementing a code change, query CodebaseMemory for the target symbol, callers, callees, tests, and dependency boundary. Confirm the index is ready; use targeted source reads and `rg` to verify its findings.
- Treat `in_degree = 0`, low-confidence `CALLS`, similarity, and semantic relations as investigation leads, never as sufficient evidence for deletion, refactoring, or consolidation.
- Before deleting a private helper or compatibility wrapper, check direct and dynamic references, imports, monkeypatches, current contracts, tests, and relevant history.
- Keep source readable: do not rename, wrap, or restructure production code solely to improve graph confidence. Classify resolver mistakes, SDK calls, builtins, test fakes, and intentional dynamic dispatch as graph evidence rather than source defects.
- When a shared `.codebase-memory/graph.db.zst` artifact is tracked, use it as the initial map. Refresh it once after a source-bearing change; commit the generated artifact last, and never refresh again merely because the artifact commit advanced `HEAD`.

## Quality Audit

- Before tests, run applicable independent checks for lint, architecture/import boundaries, types, dependency use, and JavaScript/TypeScript. Record tool versions, commands, exit status, and diagnostics.
- Triage every diagnostic against source and tests before editing. Preserve deliberate re-exports, compatibility seams, dynamic imports, SDK boundaries, and test fakes.
- Run type checkers with the project interpreter. For dependency checks, map distribution names to import names before treating a finding as real (for example `beautifulsoup4`/`bs4` and `scikit-learn`/`sklearn`).
- Keep confirmed project defects separate from missing-tool/configuration gaps and pre-existing advisory diagnostics. Do not add dependencies, suppress rules, or bulk auto-fix merely to make a tool clean.

## Read Next

- `docs/00_index.md`
- Then choose one category index only when needed.

## Persistent Draft PR Workflow

This repository uses the persistent Draft PR workflow described in
[`docs/current/agent/persistent-draft-pr-workflow.md`](docs/current/agent/persistent-draft-pr-workflow.md).
Read and follow that document for work communicated through the persistent
GitHub Draft PR. In particular:

- use one persistent working branch and one long-lived Draft PR;
- read `.ai/HANDOFF.md`, `.ai/BUG_REPORT.md`, and `.ai/DECISIONS.md` first;
- treat the latest applicable PR task comment as the active contract;
- inspect the latest relevant diff before broad repository analysis;
- keep confirmed findings separate from hypotheses;
- do not merge intermediate work.

### Implementation role split

The repository uses the following role split unless the user explicitly changes it later:

- **Web ChatGPT owns analysis, specification, review, and task definition.**
- **Local Codex owns coding, repository source/test/generated-asset edits, validation, commits, and pushes to `codex/persistent-workspace`.**
- Web ChatGPT should avoid directly editing production source code because source-level editing through Web ChatGPT consumes substantially more conversation tokens than delegating implementation to Local Codex.
- Web ChatGPT may still update workflow metadata or PR instructions when needed to maintain the communication protocol, but implementation work should normally be delegated to Local Codex.
- Web ChatGPT must make implementation requests concrete enough that Codex has minimal design freedom: objective, confirmed findings, exact required behavior, in-scope/out-of-scope boundaries, acceptance criteria, tests, constraints, and any known target files/symbols.
- If the active PR instruction conflicts with a canonical specification, Codex must not improvise; report `spec-change-required` with evidence.
- Codex may fix confirmed defects that are clearly within the active task contract, but must not expand scope or begin the next phase without a new Web ChatGPT instruction.
- After implementation, Codex runs the requested focused/regression checks, updates `.ai/HANDOFF.md` when state materially changes, commits, pushes to the persistent branch, reports the exact commit SHA and test results, then stops for Web ChatGPT review.
- Web ChatGPT reviews the latest relevant diff and validation evidence. If corrections are required, Web ChatGPT posts another precise PR comment rather than directly patching source code.

This implementation role split supersedes the former validation-only Local Codex override.

## Working Rules

- Prefer focused tests near the changed code first.
- Prefer `rg`, symbol search, and targeted ranges over full-file reads.
- If behavior might change, say so explicitly.
- If a change touches UI state, save flow, workflow orchestration, preview, progress, or entrypoint wiring, read the refactor and release rules before editing.
- Before creating or modifying a reusable Codex Skill, read `docs/14_skill_creation.md`.
- For multi-model, delegated-agent, iterative review, or blind-review work, read `docs/15_model_orchestration.md`; if blind independence is required, also read `docs/16_blind_review_protocol.md`.
- For local repository indexing/query or deterministic static analysis, read `docs/17_repo_index_and_query.md` and `docs/18_static_analysis.md`.
- For Chat/GitHub specification handoff, repository validation, or specification-to-Codex implementation flow, read `docs/19_chat_github_codex_workflow.md`.
- Do not parallelize checks that fight with the same watcher, browser, or dev server.
- If a test or command cannot run, give the exact reason and the command a human should run.
- Keep generated, cache, build, log, and artifact paths out of normal reads.
