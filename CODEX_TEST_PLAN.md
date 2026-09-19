# Codex validation plan — current persistent PR mode

This file is a routing note for Local Codex. The earlier GSI/PLATEAU implementation-era plan has been retired because it assigned repository fixes to Codex and used a non-canonical pip environment.

## Active source of truth

For PR #12:

1. read `AGENTS.md`;
2. read `.ai/HANDOFF.md`, `.ai/BUG_REPORT.md`, and `.ai/DECISIONS.md`;
3. read the PR body;
4. execute **only** the newest top-level PR comment explicitly marked `AUTHORITATIVE`;
5. validate only the exact SHA named there.

Older PR task comments and older versions of this file are historical evidence only.

## Role boundary

- Web ChatGPT owns substantive repository implementation and repairs.
- Local Codex/Luna primarily performs host-local validation/execution.
- Codex may make one tiny isolated mechanical correction when it clearly avoids a needless round trip: formatting/import/typo/quoting/path/test-fixture/launcher-glue only, normally one file and at most two.
- No algorithms, hydraulic semantics, API contracts, dependencies, generated assets/contracts, specifications, architecture, multi-file behavioral changes, or Adaptive behavior may be changed under this allowance.
- Verify the remote persistent branch still equals the task SHA before pushing a tiny fix; then report exact diff/reason/resulting SHA and rerun the affected check.
- For anything substantive, report exact command/output and a minimal repro and return the repair to Web ChatGPT.

## Canonical local environment

Use `environment.yml`, not a new `.venv` built from `requirements-dev.txt`.

Supported helper:

```text
python -m scripts.bootstrap_local_review
python -m scripts.run_local_review --check-env
```

Deterministic checks that do not require the user's local SFINCS executable are owned by `.github/workflows/local-review-ci.yml`.

## Current Codex-only scope

Codex should be asked only for evidence unavailable to Web/GitHub CI, principally:

- restoration/activation of the canonical environment on the user's Windows host;
- exact local launcher behavior;
- live external-provider behavior;
- the already-present permitted SFINCS executable path and SHA-256;
- strongest safe tiny Full 1 m real-engine execution;
- local result/log/process evidence;
- local working-tree observations that could affect what the user sees.

Do not resume legacy Local-Inertial solver validation or deeper Adaptive work unless the newest authoritative PR comment explicitly asks for it.
