# Repository Conventions

Keep work evidence-based, small, and reviewable.

## Default Workflow

- Start with `git status --short`, a shallow file listing, and `rg`.
- Read only the files and line ranges needed for the task.
- Preserve public APIs, external fields, environment keys, and operational contracts unless the request requires a migration.
- Run the nearest focused test after each logical change.
- Keep one logical reason per patch.

## Readable Code Review

- Use `readable-code-audit` for whole-repository reviews and refactoring work.
- Group related new modules by feature or domain when they evolve together.
- Explain non-obvious constants, tradeoffs, and fallback behavior with concise comments.
- Retain a reviewed exception only with `readable-code-audit: skip RULE-ID — concrete reason`.

## Skills

- Use an available Skill whenever the task matches its description. Read its `SKILL.md` before task actions.
- Define the trigger, inputs, outputs, limits, and validation before creating or updating a reusable Skill.
- Do not place credentials, private data, destructive defaults, or unverified operational commands in a Skill.

