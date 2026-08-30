---
name: readable-code-project-starter
description: Create or upgrade a repository's durable Codex project conventions for readable code. Use when starting a new software project, adding a project template, standardizing AGENTS.md, or carrying forward code-review, refactoring, and Skill-authoring practices to a new repository.
---

# Readable Code Project Starter

Install the reusable conventions without overwriting a repository's existing domain or operational rules.

## Workflow

1. Inspect the target repository for `AGENTS.md`, `.codex/`, existing Skills, test commands, and language layout.
2. Copy [assets/AGENTS.md](assets/AGENTS.md) only when the repository has no root `AGENTS.md`. Otherwise merge only missing generic sections; preserve project-specific commands, contracts, and operations rules.
3. Copy [references/project-workflow-rules.md](references/project-workflow-rules.md) and [references/skill-governance.md](references/skill-governance.md) into `docs/current/agent/` when those files do not already exist. Merge rather than overwrite when they do.
4. Confirm that `readable-code-audit` is available from the project-local or global Skill directory. Use it for broad audits and refactoring; its checklist is the authoritative review rule set.
5. Before a folder move, inventory imports, entry points, tests, external contracts, and reflection or monkey-patch paths. Group new multi-module work by feature/domain, but do not move code merely to make a directory tree look uniform.
6. Validate the selected test command and static checks. Report copied, merged, and intentionally omitted files.

## Review and Refactoring Rules

- Audit before changing code. Fix only verified findings and keep one logical purpose per patch.
- Use `readable-code-audit: skip RULE-ID — concrete reason` next to a reviewed exception.
- Prefer a feature package when related modules evolve together. Preserve stable imports unless a migration plan and compatibility boundary are verified.
- Keep comments for why, constraints, and non-obvious values. Use plain English in source comments when encoding portability matters.
- Add the smallest focused regression test before a defect fix when deterministic reproduction is possible; run it before and after the change.

## Resources

- [assets/AGENTS.md](assets/AGENTS.md): portable root instructions for a new repository.
- [references/project-workflow-rules.md](references/project-workflow-rules.md): evidence, tests, source organization, and logging rules.
- [references/skill-governance.md](references/skill-governance.md): rules for selecting, creating, updating, and validating Skills.

