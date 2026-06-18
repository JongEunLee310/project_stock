# Task Classification Policy

Each task must be classified by risk level before a Codex handoff is created. The risk level in the handoff task must match the classification here.

## Risk Levels

### Low

Examples: documentation changes, style fixes, minor UI text, adding fields to existing data structures, adding tests for existing behavior.

- Codex can implement without additional pre-implementation human review.
- Claude Code handoff is sufficient.
- Human reviews PR before merge as usual.

### Medium

Examples: adding an API endpoint following existing patterns, refactoring within existing module boundaries, adding a feature with clear requirements and test coverage.

- Claude Code designs and produces a handoff.
- Codex implements.
- Human reviews PR before merge.
- No human gate before implementation unless scope expands during implementation.

### High

Examples: authentication or authorization changes, database schema changes, significant data structure changes, new external dependencies, changes to CI or protected files.

- Human gate required before Claude Code produces a handoff. See `human-gate-policy.md`.
- Claude Code documents the gate condition in the handoff.
- Human approves scope and approach explicitly before implementation begins.

### Critical

Examples: payment processing, security controls, production data deletion, deployment automation.

- AI agents must not implement without explicit human-authored specification and step-by-step approval.
- Claude Code may plan and document options but must not produce a Codex handoff without human sign-off.

## Classification Rules

- When in doubt, classify higher.
- Scope expansion during implementation may raise the risk level. Stop, reassess, and apply the gate if needed.
- A task classified as High or Critical requires the human gate conditions in `human-gate-policy.md` to be met before proceeding.

## Related

- `human-gate-policy.md` — gate conditions triggered by High and Critical tasks.
- `handoff-policy.md` — stop conditions that overlap with High and Critical classification.
