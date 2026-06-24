# Agent Role Policy

## Claude Code

Claude Code is the orchestrator and reviewer. It analyzes issues, plans work, reviews design, creates Codex handoff tasks, triggers Codex implementation by invoking `codex exec` under the default sandbox (per `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md`), performs local PR review, and assesses documentation impact. Triggering implementation does not make Claude Code the implementer — Codex implements in its own session; Claude Code never escalates Codex's sandbox.

## Codex

Codex is the implementer. It implements from handoff tasks, updates tests, runs verification, fixes CI failures, and addresses blocking Claude Code review feedback.

## CI

CI is the feedback sensor. It runs project-specific verification commands in the PR workflow and reports failures that Codex can fix.

## Human

Humans are the final owners. They approve risky decisions, approve PRs, and merge.

## Boundary Rule

Agents should not silently swap responsibilities. If a task requires a different role, document the reason and ask for human approval when risk is meaningful.
