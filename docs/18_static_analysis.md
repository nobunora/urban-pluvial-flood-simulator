# Static Analysis Environment

Use this document to build a deterministic local static-analysis layer.

The goals are:

- parse the same C/C++ program the compiler builds;
- run clang-tidy in parallel;
- separate fast, normal, and deep scopes;
- normalize diagnostics into stable JSON;
- retain raw analyzer output for audit/debugging;
- distinguish current findings from an optional known baseline;
- provide explicit exit codes for automation.

## Architecture

```text
source tree
   |
   +--> compile_commands.json
   |        |
   |        +--> clang-tidy
   |        +--> clangd (see 17_repo_index_and_query.md)
   |
   +--> Git diff ---------------------> changed-file selection

scripts/analyze.py
   |
   +--> fast
   +--> normal
   +--> deep
   +--> file
   +--> baseline
   +--> doctor
   |
   v
artifacts/analysis/<profile>/
   +--> findings.json
   +--> summary.json
   +--> raw/*.log
```

For C/C++, `compile_commands.json` is the shared build truth for indexing and analysis. Do not maintain separate compile flags for clangd and clang-tidy.

## Required Packages

Install:

- the project's normal compiler/toolchain;
- Git;
- Python 3;
- `clang-tidy`.

On Debian/Ubuntu-family systems:

```bash
sudo apt update
sudo apt install clang clang-tidy clang-tools python3
```

Prefer the LLVM major version used by project CI when reproducibility matters.

Verify:

```bash
clang --version
clang-tidy --version
python3 --version
```

## Step 1 — Generate the Compilation Database

Static analysis must use the actual build flags.

For CMake:

```bash
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

Expected:

```text
build/compile_commands.json
```

Validate it:

```bash
python3 -c "import json; p='build/compile_commands.json'; d=json.load(open(p)); print(len(d)); print(d[0]['file'] if d else 'EMPTY')"
```

Regenerate the database when any of these change:

- target defines;
- include paths;
- generated headers;
- SDK/toolchain paths;
- language standard;
- compiler/toolchain file;
- target architecture.

A stale but syntactically valid database can produce misleading diagnostics.

## Step 2 — Define `.clang-tidy`

Do not enable every check by default. Start with correctness-oriented groups and tune them for the project.

A reasonable starting shape is:

```yaml
Checks: >
  -*,
  clang-analyzer-*,
  bugprone-*,
  performance-*,
  portability-*
WarningsAsErrors: ''
HeaderFilterRegex: '^(src|include|tests)/'
SystemHeaders: false
```

Common priorities:

- `clang-analyzer-*`;
- `bugprone-*`;
- selected `performance-*`;
- selected `portability-*`;
- selected `concurrency-*` when concurrency exists;
- project-required CERT or Core Guidelines checks where applicable.

Treat broad `modernize-*` and `readability-*` groups as opt-in unless the repository intentionally wants their warning volume and possible rewrite pressure.

Embedded, safety-critical, exception-free, RTTI-free, allocation-restricted, or target-specific projects must review generic check assumptions before adopting them.

Validate the configuration when supported by the installed version:

```bash
clang-tidy --verify-config
```

## Step 3 — Verify the CLI

Run:

```bash
python3 scripts/analyze.py doctor
```

The doctor command checks:

- Git;
- `clang-tidy`;
- `compile_commands.json`;
- presence of C/C++ translation units in the database;
- optional `.clang-tidy` presence;
- optional `.clang-tidy` configuration validation.

A missing required analyzer or compilation database returns exit code `2`.

## Step 4 — Analysis Profiles

### Fast

```bash
python3 scripts/analyze.py fast
```

Scope:

- changed C/C++ translation units only.

Use this after a focused source edit.

Changed headers are reported in selection metadata but do not automatically expand the fast profile. This keeps fast feedback bounded.

### Normal

```bash
python3 scripts/analyze.py normal
```

Scope:

- changed C/C++ translation units;
- if a tracked/untracked header changed, all translation units are analyzed conservatively.

The broad header behavior is intentional. Without a separate dependency graph, determining every affected translation unit from a header change cannot be done reliably by filename alone.

### Deep

```bash
python3 scripts/analyze.py deep
```

Scope:

- every C/C++ translation unit in `compile_commands.json`.

Use for:

- release/preflight checks;
- large refactors;
- toolchain/configuration changes;
- high-risk control-flow or ownership changes;
- periodic full-repository validation.

### File

```bash
python3 scripts/analyze.py file src/example.cpp
```

The file must be an actual translation unit in the compilation database.

Headers are not analyzed directly because clang-tidy requires a compile command context. Use `normal` or `deep` when a header change must be evaluated.

## Step 5 — Parallel Execution

`analyze.py` invokes clang-tidy per selected translation unit using a Python thread pool.

Default worker count:

```text
logical CPU count / 2
```

Therefore a 48-thread machine defaults to 24 concurrent clang-tidy processes.

Override explicitly:

```bash
python3 scripts/analyze.py --jobs 24 deep
```

If memory pressure or SDK/toolchain I/O becomes a bottleneck, reduce the job count. If analysis is CPU-bound and memory remains comfortable, benchmark higher values rather than assuming more processes are always faster.

## Step 6 — Normalized Findings

clang-tidy text diagnostics are normalized to JSON.

Example record:

```json
{
  "id": "clang-tidy:bugprone-use-after-move:src/control.cpp:417:0123456789ab",
  "tool": "clang-tidy",
  "check": "bugprone-use-after-move",
  "level": "warning",
  "severity": "medium",
  "path": "src/control.cpp",
  "line": 417,
  "column": 9,
  "message": "object used after it was moved",
  "baseline": false,
  "new_in_analysis": true
}
```

The stable finding ID is derived from:

```text
tool + check + path + line + column + message
```

The wrapper preserves the original check name and diagnostic level.

Default severity mapping is intentionally simple:

```text
clang-tidy error                      -> high
security analyzer / CERT warning     -> high
other warning                         -> medium
note                                  -> low
```

Project policy may later map severities differently, but it should not erase the original tool/check identity.

## Step 7 — Artifacts

Results are stored under:

```text
artifacts/analysis/fast/
artifacts/analysis/normal/
artifacts/analysis/deep/
artifacts/analysis/file/
```

Each profile contains:

```text
findings.json
summary.json
raw/
```

`findings.json` contains normalized findings.

`summary.json` contains:

- status;
- compilation database path;
- worker count;
- selected translation units;
- changed files/headers;
- severity counts;
- new/baseline counts;
- analyzer failures;
- raw artifact paths.

`raw/` preserves clang-tidy output per translation unit.

Generated analysis output is ignored by Git through the existing `artifacts/` rule.

## Step 8 — Failure Policy

Default behavior fails when any non-baseline finding exists:

```bash
python3 scripts/analyze.py normal
```

Equivalent to:

```bash
python3 scripts/analyze.py --fail-on any normal
```

Available policies:

```text
--fail-on any    fail on any new finding
--fail-on high   fail on new high/critical findings
--fail-on error  fail only on clang-tidy error diagnostics
--fail-on none   never fail because of findings
```

This controls the command exit status; findings are still written to artifacts.

## Step 9 — Baselines

For a repository that already contains known findings, create an explicit baseline rather than hiding them in parser logic.

First run an analysis without a baseline and retain its `findings.json`:

```bash
python3 scripts/analyze.py --fail-on none deep
```

Create a baseline file:

```bash
python3 scripts/analyze.py baseline \
  --from-findings artifacts/analysis/deep/findings.json \
  --output .analysis-baseline.json
```

Then run against it:

```bash
python3 scripts/analyze.py --baseline .analysis-baseline.json normal
```

Existing matching finding IDs are marked:

```json
{
  "baseline": true,
  "new_in_analysis": false
}
```

New findings remain visible and can fail the configured policy.

A baseline is not a statement that old findings are acceptable. It is noise control. Critical/high legacy findings should still have an explicit disposition in the project workflow.

Because finding IDs include line/column/message, large source movement can invalidate baseline matches. Regenerate deliberately; do not silently rewrite the baseline during normal analysis.

## Exit Codes

```text
0 = analysis completed and configured policy passed
1 = analysis completed and configured policy failed
2 = environment/configuration/input error
3 = analyzer process failure without parseable diagnostics
130 = interrupted
```

A missing analyzer must never produce exit code `0`.

## Temporary Check Override

Normally configure checks in `.clang-tidy`.

For diagnostics or experiments only:

```bash
python3 scripts/analyze.py --checks='-*,clang-analyzer-*,bugprone-*' file src/example.cpp
```

Do not use a command-line override as a hidden permanent project policy. Commit intentional policy to `.clang-tidy`.

## Changed-Line Filtering

The built-in CLI scopes by changed translation unit, not changed line.

This distinction matters: `clang-tidy-diff.py` analyzes the whole file and filters reported diagnostics to changed lines, so changed-line filtering alone is not a true analysis-cost reduction.

For performance, select fewer translation units. For correctness, expand the scope when headers, templates, shared state, generated code, or build configuration can affect multiple translation units.

## Language Scope

The included `scripts/analyze.py` implementation is intentionally C/C++ focused because it relies on `compile_commands.json` and clang-tidy.

For other languages, preserve the same deterministic principles but use the repository's native tooling, for example:

| Ecosystem | Typical deterministic checks |
| --- | --- |
| Python | Ruff, mypy/pyright |
| TypeScript | `tsc --noEmit`, ESLint |
| Rust | `cargo clippy`, compiler warnings |
| Go | `go vet`, configured linters |

Do not install every analyzer into every project template. Add adapters only when the project actually uses that ecosystem and has a defined policy.

## Validation

Run the helper unit tests:

```bash
python3 -m unittest discover -s tests -p 'test_local_analysis_tools.py' -v
```

Then validate the actual C/C++ environment:

```bash
python3 scripts/analyze.py doctor
python3 scripts/analyze.py --fail-on none fast
python3 scripts/analyze.py --fail-on none normal
```

Before using the deep profile as a gate, inspect its first complete result and tune `.clang-tidy`/baseline policy intentionally.

## Recommended Bring-Up Order

```text
1. install LLVM/clang-tidy
2. generate compile_commands.json
3. define/review .clang-tidy
4. python3 scripts/analyze.py doctor
5. run fast on a known changed TU
6. run normal
7. run deep with --fail-on none
8. inspect normalized and raw outputs
9. establish baseline only if required
10. choose the project fail policy
```

## Relationship to Repository Indexing

For C/C++:

```text
                     build/compile_commands.json
                           /            \
                          /              \
                         v                v
                      clangd          clang-tidy
                         |                |
                         v                v
                 repo_query.py       analyze.py
```

The two tools are independent at runtime but share the same authoritative compilation database.

`repo_query.py` answers where code is and how symbols are related.

`analyze.py` reports deterministic static-analysis diagnostics.

Neither requires the other to run, except that both benefit from an accurate build configuration.

## References

- clang-tidy documentation: <https://clang.llvm.org/extra/clang-tidy/>
- clangd/compilation database setup: <https://clangd.llvm.org/installation>
- See also `17_repo_index_and_query.md`.

