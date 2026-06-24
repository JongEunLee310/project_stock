# Autonomy Levels

This document defines the autonomy levels available in the AI-assisted development workflow.

## Levels

### Level 0: Manual

All work is performed by a human. AI tools are not used.

### Level 1: AI-Assisted

Claude Code and Codex assist with planning, drafting, and implementation. Humans review and approve every step before it proceeds.

Use when: the team is learning the workflow, or the task is High or Critical risk.

### Level 2: Semi-Autonomous

Claude Code plans, Codex implements, and CI verifies. Humans review PRs before merge.

Use when: the task is Low or Medium risk, scope is clearly defined, and verification commands exist.

At this level Claude Code triggers Codex implementation automatically by invoking `codex exec` under the default sandbox (`read-only` / `workspace-write`), using its handoff document as the brief, then resumes with the local review. Humans review and merge the PR; they do not run a manual implementation step for Low/Medium risk work. Bypass/danger sandbox flags are never used — if the default sandbox cannot run a task, Claude Code falls back to manual execution or asks the human. See `docs/harness/handoff-policy.md` and `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md` (which supersedes ADR-004).

## Default Level

This template operates at Level 2 for Low and Medium risk tasks. High and Critical risk tasks require Level 1 (human gate before implementation begins).

## Related

- `task-classification-policy.md` — risk levels
- `human-gate-policy.md` — gate conditions
