# Specifications

This directory contains specification contracts shared through GitHub before repository implementation begins.

A specification may be one of three kinds:

1. **Product / behavior contract** — defines user-visible or system outcomes without fixing code structure.
2. **Detailed implementation contract** — may intentionally pin architecture, tools, data contracts, state machines, algorithms, test thresholds, and completion gates when ambiguity would otherwise create implementation drift.
3. **UI behavior / UI implementation contract** — separates what the user must experience from how the frontend must implement it.

Use one file per cohesive responsibility or contract level. Prefer stable names such as:

```text
docs/specs/<feature-or-change>.md
docs/specs/<feature-or-change>-implementation-spec.md
docs/specs/<feature-or-change>-ui-spec.md
```

Start from `SPEC_TEMPLATE.md` when a more specialized contract does not already exist.

## Source-of-truth rule

Every specification must state its precedence/source-of-truth relationship when companion specifications exist.

If translations are provided:

- the canonical file must be identified explicitly;
- translations must preserve requirement IDs and scope categories;
- a translation must not silently introduce a new requirement;
- `*.ja.md` files are reference translations and are not required to duplicate English heading names.

## `codex-ready` gate rule

The GitHub `Spec ready gate` validates **canonical specification files only**. It ignores `README.md`, `SPEC_TEMPLATE.md`, and `*.ja.md` reference translations.

Two contract shapes are accepted:

- **standard contracts** using the template headings (`Goal`, `Scope`, `Non-goals`, `Requirements / Invariants`, `Acceptance Criteria`, `Validation`);
- **specialized detailed/UI contracts** using their own numbered structure, provided they explicitly define completion criteria, excluded/not-implemented scope, and validation/acceptance evidence.

Every canonical specification checked by the gate must explicitly identify English as the canonical file/language. Do not change translations merely to satisfy an English-heading CI rule.

## Repository-validation rule

A specification states what must be true. Even a detailed implementation contract must not claim compatibility with the real repository until the repository-review phase validates it against the current source tree and external contracts.

If a fixed implementation choice cannot be satisfied, the repository agent must report `spec-change-required`; it must not silently substitute another architecture or dependency.

## Low-context implementation rule

When a specification is intended for a bounded/low-context implementation agent, it should define enough of the following to prevent guessing:

- inputs and outputs;
- approved tools/dependencies;
- state transitions;
- error/fallback behavior;
- physical/numerical assumptions;
- prohibited substitutions;
- tests and numerical tolerances;
- observable completion criteria;
- explicit stop conditions.

Do not use chat history as an implementation contract.

Repository-local helper wrappers are optional unless the approved specification explicitly makes the wrapper itself a deliverable or prerequisite. If a documented wrapper is absent, use its underlying deterministic tool directly and record the substitution. Do not create unrelated tooling infrastructure inside a product feature PR just to satisfy aspirational documentation.

When a specification is ready for repository review, its PR may be labeled `codex-ready`.
