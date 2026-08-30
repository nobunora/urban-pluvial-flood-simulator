# Development Playbook

## Work Intake

- Metadata first.
- Search first.
- Read only needed docs.
- Risky area? Read the matching safety/release doc.

## Scope Control

- One task, one purpose.
- Split big work into phases.
- Smallest reviewable cut.

## Refactor Flow

- Freeze behavior first.
- Add tests before moving stateful code.
- Refactor ≠ feature.
- No unrelated cleanup.

## Implementation Flow

- Thin entrypoint.
- Policy in the right layer.
- Use domain names.
- Simple over abstract.

For complex work that uses multiple AI roles, delegated agents, or repeated review/implementation cycles, use `15_model_orchestration.md` rather than improvising agent responsibilities in each session.

## Verification Flow

- Nearest tests first.
- Release gate for wide/risky changes.
- Serial if watchers conflict.
- Record the commands.

For non-trivial changes, verification evidence should feed the review loop. Passing checks are evidence, not proof of correctness.

## Collaboration Flow

- Subagents only if cheaper or if independence materially improves quality.
- Clear role, scope, evidence requirement, and stop condition.
- No duplicate search unless independence is intentional.
- Short, specific summaries.
- Keep final architecture and risk decisions with the lead reasoning role.
- When independent discovery is required, isolate the blind reviewer and follow `16_blind_review_protocol.md`.

