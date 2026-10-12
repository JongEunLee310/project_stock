# Agent Role Policy

## Claude Code

Claude Code is the orchestrator and reviewer. It analyzes issues, plans work, reviews design, creates Codex handoff tasks, triggers Codex implementation by invoking `codex exec` under the default sandbox (per `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md`), performs local PR review, and assesses documentation impact. Triggering implementation does not make Claude Code the implementer — Codex implements in its own session; Claude Code never escalates Codex's sandbox.

## Codex

Codex is the implementer. It implements from handoff tasks, updates tests, runs verification, fixes CI failures, and addresses blocking Claude Code review feedback.

## Standard Orchestration Combination

The default going-forward model lineup (effective 2026-10-12) is **Claude Opus 5.5 + Codex GPT-6.1 Sol**:

- **Claude Code — Opus 5.5 (`claude-opus-5-5`)** — orchestration, design, handoff writing, local review, external execution (codex trigger, commit, push, PR), and final verification. Design and review are no longer delegated to the Sonnet/VFF subagent by default.
- **Codex — GPT-6.1 Sol (`gpt-6.1-sol`), reasoning effort `medium`** — implementation.
- **Codex — GPT-6.1 Sol, reasoning effort `high`** — escalation only, when the work needs it: cross-module refactors, concurrency or transaction correctness, migrations with data backfill, or a `medium` run that failed the same verification twice. Record the reason for escalating in the handoff document.

Always pass the model and effort explicitly on every `codex exec` call (`-c model="gpt-6.1-sol" -c model_reasoning_effort="medium"`, or `"high"` when escalating), because the global Codex config can override project defaults. Do not swap to a different model without human confirmation.

The earlier Opus + Sonnet/VFF + Codex split and its cost measurements remain as history in `docs/experiments/`.

## CI

CI is the feedback sensor. It runs project-specific verification commands in the PR workflow and reports failures that Codex can fix.

## Human

Humans are the final owners. They approve risky decisions, approve PRs, and merge.

## Boundary Rule

Agents should not silently swap responsibilities. If a task requires a different role, document the reason and ask for human approval when risk is meaningful.
