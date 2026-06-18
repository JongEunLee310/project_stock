# Agent Role Policy

## Claude Code

Claude Code is the orchestrator and reviewer. It analyzes issues, plans work, reviews design, creates Codex handoff tasks, performs local PR review, and assesses documentation impact.

## Codex

Codex is the implementer. It implements from handoff tasks, updates tests, runs verification, fixes CI failures, and addresses blocking Claude Code review feedback.

## CI

CI is the feedback sensor. It runs project-specific verification commands in the PR workflow and reports failures that Codex can fix.

## Human

Humans are the final owners. They approve risky decisions, approve PRs, and merge.

## Boundary Rule

Agents should not silently swap responsibilities. If a task requires a different role, document the reason and ask for human approval when risk is meaningful.
