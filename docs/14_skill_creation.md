# Skill Creation Rules

Use this guide when creating or changing a reusable Codex Skill. It adapts the public [Anthropic Skill Creator guide](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md); consult the source for its current examples and evaluation tooling.

## Define the contract

- Identify the job, realistic trigger phrases, inputs, outputs, safety limits, and success criteria before authoring.
- Ask only for missing choices that materially change the Skill. Do not turn an unclear one-off request into a broad reusable tool.
- Write a `description` that names both the capability and the context in which it should trigger.

## Structure for reuse

- Use `SKILL.md` with YAML `name` and `description` frontmatter.
- Keep instructions concise, imperative, and under 500 lines when practical. Explain important constraints so the Skill can generalize.
- Place deterministic repeated work in `scripts/`, detailed context in `references/`, and output assets in `assets/`.
- Link optional resources from `SKILL.md` and say when they are needed. Avoid auxiliary READMEs, changelogs, and duplicated guidance.
- Do not include credentials, hidden data collection, destructive actions, or behavior that would surprise the user.

## Validate and improve

1. Initialize with the available Skill scaffolder, then remove all placeholders.
2. Run the structural validator; if it cannot run, record the exact reason and manually validate required frontmatter and references.
3. Execute every added script with a safe representative input.
4. For non-trivial Skills, evaluate 2–3 realistic prompts against an appropriate baseline and inspect the outputs.
5. Simplify instructions that do not improve results, then iterate until the workflow is useful beyond the original request.

## Integration

- Keep project-specific scripts in the project repository and document the expected repository root.
- Store evaluation workspaces outside the Skill directory.
- Treat any production mutation as a separately authorized operation.

