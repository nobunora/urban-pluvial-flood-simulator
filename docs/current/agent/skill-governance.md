# Skill Governance

## Select and Use

- Use the smallest available Skill that matches the request. Read the complete `SKILL.md` before task actions.
- Apply every directly linked required reference, but do not load unrelated resources.
- State when a Skill changes the workflow or blocks progress.

## Create or Update

- Define the user goal, trigger phrases, inputs, outputs, limits, safety boundaries, and success criteria first.
- Keep the frontmatter description specific enough for discovery. Keep procedural instructions concise and put detailed material in directly linked references.
- Prefer bundled scripts for repeated deterministic work; test each safe script invocation.
- Do not duplicate a general workflow in several Skills. Link to the authoritative Skill or reference.

## Validate

- Use the Skill initializer when it is appropriate for a new Skill.
- Run the Skill validator after every creation or update.
- For a non-trivial Skill, test it with realistic requests that do not reveal the intended answer, then simplify unclear instructions.
- Keep reusable Skills free of credentials, destructive defaults, generated artifacts, and project-specific secrets.


