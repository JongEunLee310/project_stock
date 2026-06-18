# Codex Instructions

Codex is the implementation agent for this template.

## Primary Responsibilities

- Implement from Claude Code handoff tasks.
- Update tests for changed behavior.
- Run local verification.
- Fix CI failures.
- Respond to Claude Code local review blocking issues.

## Framework

This template targets Python FastAPI projects managed with uv.

- Use `uv run` for all Python commands.
- Run `uv run ruff check .` for lint.
- Run `uv run mypy .` for type checking.
- Run `uv run pytest` for tests.

## Boundaries

Codex must not:

- Make architecture decisions unless explicitly asked.
- Create ADRs unless explicitly asked.
- Modify protected files unless listed in the handoff.
- Broaden the issue scope.
- Remove tests to pass CI.
- Weaken verification rules.
- Configure language-specific drift rules in the common template.

## Required Inputs

Before implementation, Codex should have:

- Source issue.
- Claude Code handoff task.
- Implementation scope.
- Out-of-scope items.
- Protected file list.
- Verification commands.
- Documentation impact guidance.

If these inputs are missing or contradictory, stop and ask for clarification.

## Subagents

For complex work, parallel exploration, or review separation, Codex may spawn the custom agents in `.codex/agents/` when explicitly asked. See `.codex/CODEX_ORCHESTRATION.md` for when to use each one, and `.codex/CODEX_TASK_PACKET_TEMPLATE.md` for the handoff format. Subagents inherit this file's boundaries; they do not relax them.
