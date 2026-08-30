# Repository Index and Query Environment

Use this document to build a deterministic local repository discovery layer.

The goals are:

- cheap lexical file/text search;
- language-neutral symbol-definition lookup;
- semantic C/C++ reference and call-hierarchy queries;
- concise JSON output;
- explicit distinction between lexical and semantic evidence.

The source tree remains authoritative. Indexes are acceleration data and may be rebuilt at any time.

## Architecture

```text
source tree
   |
   +--> Git / ripgrep --------------------> files and lexical text matches
   |
   +--> Universal Ctags -----------------> language-neutral definitions
   |
   +--> compile_commands.json
             |
             +--> clangd background index -> C/C++ semantic references/call hierarchy
             +--> clang-tidy               -> static analysis (see 18_static_analysis.md)

scripts/repo_query.py = stable deterministic CLI facade
```

For C/C++, `compile_commands.json` is the shared build truth used by both clangd and clang-tidy. Do not maintain a second set of include paths, defines, target flags, or language settings for indexing.

## Required Packages

On the machine that holds the working tree, install:

- Git;
- ripgrep (`rg`);
- Python 3;
- Universal Ctags with JSON support.

For semantic C/C++ queries also install:

- a recent LLVM/Clang toolchain;
- `clangd`.

For static analysis also install `clang-tidy`; see `18_static_analysis.md`.

On Debian/Ubuntu-family systems a typical starting point is:

```bash
sudo apt update
sudo apt install git ripgrep python3 jq universal-ctags clangd clang-tidy
```

Package names vary by distribution. Prefer the LLVM major version used by project CI when reproducibility matters.

Verify the binaries:

```bash
git --version
rg --version
ctags --version
ctags --list-features | grep json
clangd --version
python3 --version
```

`repo_query.py index` requires Universal Ctags with the `json` feature.

## Generated Data

Project-owned generated data is stored under:

```text
.cache/repo-index/
artifacts/repo-query/
```

The template ignores `.cache/`, `build/`, and `artifacts/`.

clangd manages its own background-index shards. Their exact location depends on where clangd discovers `compile_commands.json`; do not copy clangd's internal index into source-controlled paths.

## Step 1 — Verify the CLI

From the repository root:

```bash
python3 scripts/repo_query.py doctor
```

The doctor command checks:

- Git;
- ripgrep;
- Universal Ctags;
- Ctags JSON support;
- index directory writability;
- optional clangd availability;
- optional `compile_commands.json` availability.

A missing clangd or compile database does not prevent lexical/Ctags queries. It only disables semantic C/C++ operations.

## Step 2 — Establish Lexical Search

The cheapest operations use ripgrep and Git directly.

Examples:

```bash
python3 scripts/repo_query.py files
python3 scripts/repo_query.py files adc
python3 scripts/repo_query.py text ADC_TIMEOUT
python3 scripts/repo_query.py tests process_adc
python3 scripts/repo_query.py changed
```

`files` and `text` are lexical operations. Their JSON output reports:

```json
{
  "backend": "ripgrep",
  "semantic": false
}
```

Use lexical search for:

- filenames;
- literals;
- configuration keys;
- error messages;
- comments;
- exact symbol-name discovery;
- test-name discovery.

Generated/cache/build paths are excluded from normal text search.

## Step 3 — Build the Ctags Definition Index

Build or refresh the language-neutral definition index:

```bash
python3 scripts/repo_query.py index
```

By default the command indexes existing paths among:

```text
src/
include/
tests/
```

To specify paths explicitly:

```bash
python3 scripts/repo_query.py index src include platform tests
```

Output is stored at:

```text
.cache/repo-index/ctags.json
```

Query an exact symbol name:

```bash
python3 scripts/repo_query.py symbol process_adc
```

Ctags output is deterministic symbol-definition metadata, but it is not a semantic caller/reference engine. The result therefore remains labeled:

```json
{
  "backend": "universal-ctags",
  "semantic": false
}
```

Refresh the Ctags index after material source changes, branch changes, or large refactors.

## Step 4 — Generate `compile_commands.json` for C/C++

Semantic C/C++ queries require the actual compile flags.

For CMake:

```bash
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

Expected result:

```text
build/compile_commands.json
```

Validate it:

```bash
python3 -c "import json; p='build/compile_commands.json'; d=json.load(open(p)); print(len(d)); print(d[0]['file'] if d else 'EMPTY')"
```

The compilation database must match the real build configuration, including:

- include paths;
- preprocessor definitions;
- generated headers;
- language standard;
- target architecture;
- compiler/toolchain settings.

For non-CMake projects, use the build system's native compilation-database support or an appropriate capture tool such as Bear.

Do not keep a stale copied `compile_commands.json` at repository root. `repo_query.py` searches common build locations and accepts an explicit location when necessary:

```bash
python3 scripts/repo_query.py --compile-db build-alt refs process_adc
```

## Step 5 — Warm the clangd Index

clangd builds its background index from the compilation database.

Normal setup:

1. generate a current `compile_commands.json`;
2. run a semantic query or start clangd through the normal editor/tooling;
3. allow background indexing to complete;
4. reuse clangd's cached shards on later runs.

For large repositories, first measure whether normal background indexing is actually a bottleneck. Only then consider `clangd-indexer` or a dedicated remote index server.

## Step 6 — Run Semantic C/C++ Queries

`refs`, `callers`, and `callees` use clangd's LSP interface.

Examples:

```bash
python3 scripts/repo_query.py refs process_adc
python3 scripts/repo_query.py callers process_adc
python3 scripts/repo_query.py callees control_loop
```

A target may also be an explicit source location:

```bash
python3 scripts/repo_query.py refs src/adc.cpp:214:5
```

For a symbol-name target, the CLI uses the Ctags index to locate the definition and then asks clangd for semantic information. Therefore run `index` before symbol-name semantic queries.

Successful semantic output is explicitly labeled:

```json
{
  "backend": "clangd",
  "semantic": true
}
```

The CLI does not silently fall back from a failed semantic operation to lexical text matching.

Call-hierarchy support depends on the installed clangd version. If an operation is unsupported, the command fails explicitly rather than fabricating a lexical equivalent.

## CLI Contract

Implemented commands:

```text
python3 scripts/repo_query.py doctor
python3 scripts/repo_query.py index [paths...]
python3 scripts/repo_query.py files [pattern]
python3 scripts/repo_query.py text <pattern>
python3 scripts/repo_query.py symbol <name>
python3 scripts/repo_query.py refs <symbol|path:line[:column]>
python3 scripts/repo_query.py callers <symbol|path:line[:column]>
python3 scripts/repo_query.py callees <symbol|path:line[:column]>
python3 scripts/repo_query.py tests <pattern>
python3 scripts/repo_query.py changed
```

Common options:

```text
--compile-db <path-or-directory>
--index <ctags-json-path>
--compact
```

## Output Rules

The default output is JSON.

Every discovery result identifies the backend and whether the result is semantic.

Example lexical result:

```json
{
  "mode": "text",
  "query": "ADC_TIMEOUT",
  "backend": "ripgrep",
  "semantic": false,
  "matches": [
    {"path": "src/adc.cpp", "line": 40, "column": 9, "text": "..."}
  ]
}
```

Example semantic result:

```json
{
  "mode": "refs",
  "query": "process_adc",
  "backend": "clangd",
  "semantic": true,
  "origin": {"path": "src/adc.cpp", "line": 214, "column": 5},
  "references": [
    {"path": "src/main.cpp", "line": 393, "column": 9}
  ]
}
```

The query layer returns locations and short matching lines, not whole-file contents.

## Freshness Rules

Refresh or revalidate when:

- the active branch changes materially;
- source files are added/removed/renamed;
- large refactors move symbols;
- build flags or toolchain settings change;
- `compile_commands.json` changes;
- generated headers change;
- results point to files/lines that no longer exist.

Recommended sequence after a material change:

```bash
python3 scripts/repo_query.py index
python3 scripts/repo_query.py doctor
```

clangd incrementally maintains its own background index when running.

## Dedicated Analysis Machine

A many-core machine with large RAM and fast SSD is suitable for hosting the working tree, build directory, Ctags data, and clangd cache.

Keep all index internals on that host and expose only the CLI output to other development tooling.

For a 24-core/48-thread class machine, clangd background indexing and Ctags generation can run locally without GPU resources.

## Validation

Run the deterministic helper tests:

```bash
python3 -m unittest discover -s tests -p 'test_local_analysis_tools.py' -v
```

Then validate the actual project environment:

```bash
python3 scripts/repo_query.py doctor
python3 scripts/repo_query.py index
python3 scripts/repo_query.py symbol <known-symbol>
```

For C/C++ with a compilation database:

```bash
python3 scripts/repo_query.py refs <known-symbol>
python3 scripts/repo_query.py callers <known-symbol>
```

## References

- clangd index design: <https://clangd.llvm.org/design/indexing>
- clangd installation and compilation database setup: <https://clangd.llvm.org/installation>
- clangd configuration: <https://clangd.llvm.org/config>
- Universal Ctags documentation: <https://docs.ctags.io/en/latest/man/ctags.1.html>
- See also `18_static_analysis.md`.

